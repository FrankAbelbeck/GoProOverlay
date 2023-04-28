#!/usr/bin/env python3
"""Frank Abelbeck GoPro Telemetry Overlay Toolset: convert telemetry
Copyright (C) 2023 Frank Abelbeck <frank@abelbeck.info>

This program is free software: you can redistribute it and/or modify
it under the terms of the GNU General Public License as published by
the Free Software Foundation, either version 3 of the License, or
(at your option) any later version.

This program is distributed in the hope that it will be useful,
but WITHOUT ANY WARRANTY; without even the implied warranty of
MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
GNU General Public License for more details.

You should have received a copy of the GNU General Public License
along with this program.  If not, see <http://www.gnu.org/licenses/>.
"""

import argparse   # argument parsing
import json       # JSON data structures
import itertools  # see batched: rearranging accelerometer/gyroscope vectors
import datetime   # timestamping
import math       # true course calculation; subset calculation rounding
import sys        # stdin/stdout

#
# initial telemetry data definitions: headings
#
HEADINGS = (
	"Timestamp",
	"Duration",
	"TimeGPS",
	"AccelerationX",
	"AccelerationY",
	"AccelerationZ",
	"GyroscopeX",
	"GyroscopeY",
	"GyroscopeZ",
	"Latitude",
	"Longitude",
	"Altitude",
	"HorizontalError",
	"Vario",
	"TrueCourse",
	"GPSSpeed2D",
	"GPSSpeed3D",
	"Temperature",
	"Distance",
)
MAP_HEADINGS_IDX = {key:i for i,key in enumerate(HEADINGS)}

def batched(iterable,n):
	"""Generator: take n items from iterable and yield them as n-tuple.

Args:
   iterable: an iterable, a sequence of items.
   n: an integer, number of items to take and yield

Yields:
   An n-tuple.
"""
	it = iter(iterable)
	while (batch := tuple(itertools.islice(it,n))):
		yield batch


def interpolateTypedList(strList,funConv,intLenVector,intNumSamples):
	"""Take a string of space-separated substrings, apply given conversion function to
each substring, group given number of consequtive items in a tuple and return an
evenly distributed subset of the resulting vector sequence.

Expected input:
   "1 1 1 2 2 2 3 3 3 4 4 4 5 5 5"

Intended row sequence with funConv=int and intLenVector=3:
   [(1,1,1),(2,2,2),(3,3,3),(4,4,4),(5,5,5)]

Intended row sequence with intNumSamples=3:
   [ (1,1,1), (3,3,3), (5,5,5) ]

Args:
   strList: a string, space-separated sequence of substrings.
   funConv: a function accepting one argument and returning a converted value.
   intLenVector: an integer; number of items to group.
   intNumSamples: an integer; number of samples to pick from the raw sequence.

Returns:
   A list of tuples.
"""
	lstRaw = [funConv(i) for i in strList.split()]
	if intLenVector > 1 and intNumSamples > 1:
		lstRaw = list(batched(lstRaw,intLenVector))
		if len(lstRaw[-1]) < intLenVector:
			del lstRaw[-1]
		intNumRaw = len(lstRaw)
		return [lstRaw[math.ceil(intIdx*intNumRaw/intNumSamples)] for intIdx in range(intNumSamples)]
	else:
		return []


if __name__ == "__main__":
	# initialise argument parser and parse arguments
	parser = argparse.ArgumentParser(
		description="Read GoPro telemetry JSON data (as extracted by exiftool) from stdin, and write revised JSON data to stdout.",
		epilog="Column headings: " + ", ".join(HEADINGS)
	)
	parser.add_argument("--version", action="version", version="20230416")
	parser.add_argument("--samples",
		help="Set number of sampling points per entry for any multi-valued data (e.g. Accelerometer; default: number of frames per second)",
		type=int
	)
	parser.add_argument("--init",
		help="JSON string describing a dictionary of initial values (in case any values accumulate over time, e.g. distance)",
		default=None
	)
	parser.add_argument("FILE",
		help="Output JSON telemetry file",
		type=argparse.FileType('w')
	)
	parser.add_argument("--lastrow",
		help="After converting, print a JSON dictionary of values of the keys given in LASTROW. "
			"LASTROW is parsed as a comma-separated key string list. The special key 'all' will select all values. "
			"Unknown fields will be silently ignored."
	)
	parser.add_argument("--hdop",
		help="Set the maximum horizontal dilution of precision (HDOP) value for which GPS data is accepted. Default: 10. "
			"Excellent: 1-2; good: 2-5; moderate: 5-10; fair: 10-20; poor: 20+",
		type=float,
		default=10.0
	)
	parser.add_argument("--minspeed",
		help="Set the minimum GPS speed (3D, metres/second) that has to be reached to do calculations on true course and rate of descend. Default: 1. ",
		type=float,
		default=1.0
	)
	args = parser.parse_args()
	
	# read JSON data from stdin
	dctIn = json.load(sys.stdin)[0]
	
	# prepare output dictionary
	dctOut = {
		"headings": list(HEADINGS),
	}
	
	# parse initial value vector, extract distance initial value
	lstRowInit = [None]*len(HEADINGS)
	try:
		for key,value in json.loads(args.init).items():
			lstRowInit[MAP_HEADINGS_IDX[key]] = value
	except (json.decoder.JSONDecodeError,AttributeError) as e:
		# ignore errors of init JSON structure; might be whitespace due to missing INIT data
		print(f"ignoring invalid init data {args.init} ({e})",file=sys.stderr)
	except TypeError:
		# most likely: args.init is None; nevermind
		pass
	try:
		fltDistance = float(lstRowInit[MAP_HEADINGS_IDX["Distance"]])
	except (TypeError,ValueError):
		fltDistance = 0.0
	
	# prepare sample interpolation: get argument, set to framerate if unset
	if args.samples is None:
		args.samples = round(dctIn["Main:VideoFrameRate"])
	
	# main processing loop:
	# - create a new document name string
	#   (-G3 option of exiftool puts out family 3 name types of the form 'docx-name" with x in 1...N)
	# - end of data: no sample time found or no next doc entry found
	# - extract/convert data
	# - derive values (rate of climb, true course, distance accumulation)
	# - append new "rows" entry 
	# - update "min"/"max" entries
	intIdx = 1
	while True:
		strDoc = "Doc{}:".format(intIdx)
		if strDoc+"SampleTime" not in dctIn:
			# Docxx:SampleTime not found: end of Doc sequence reached
			break
		# read values from Doc field
		lstRow = [None]*len(HEADINGS)
		try:
			# convert accelerometer and gyroscope data into 3-tuples (x,y,z)
			# of floats, mapped to requested sample number
			lstRow[MAP_HEADINGS_IDX["Duration"]] = float(dctIn[strDoc+"SampleDuration"])
			
			lstFltAccel = interpolateTypedList(dctIn[strDoc+"Accelerometer"],float,3,args.samples)
			lstRow[MAP_HEADINGS_IDX["AccelerationX"]] = [v[0] for v in lstFltAccel]
			lstRow[MAP_HEADINGS_IDX["AccelerationY"]] = [v[1] for v in lstFltAccel]
			lstRow[MAP_HEADINGS_IDX["AccelerationZ"]] = [v[2] for v in lstFltAccel]
			
			lstFltGyro = interpolateTypedList(dctIn[strDoc+"Gyroscope"],float,3,args.samples)
			lstRow[MAP_HEADINGS_IDX["GyroscopeX"]] = [v[0] for v in lstFltGyro]
			lstRow[MAP_HEADINGS_IDX["GyroscopeY"]] = [v[1] for v in lstFltGyro]
			lstRow[MAP_HEADINGS_IDX["GyroscopeZ"]] = [v[2] for v in lstFltGyro]
			
			fltHDOP = float(dctIn[strDoc+"GPSHPositioningError"])
			lstRow[MAP_HEADINGS_IDX["HorizontalError"]] = fltHDOP
			if fltHDOP <= args.hdop:
				lstRow[MAP_HEADINGS_IDX["Latitude"]] = float(dctIn[strDoc+"GPSLatitude"])
				lstRow[MAP_HEADINGS_IDX["Longitude"]] = float(dctIn[strDoc+"GPSLongitude"])
				lstRow[MAP_HEADINGS_IDX["Altitude"]] = float(dctIn[strDoc+"GPSAltitude"])
				lstRow[MAP_HEADINGS_IDX["GPSSpeed2D"]] = float(dctIn[strDoc+"GPSSpeed"])
				lstRow[MAP_HEADINGS_IDX["GPSSpeed3D"]] = float(dctIn[strDoc+"GPSSpeed3D"])
			
			# get camera temperature [°C]
			lstRow[MAP_HEADINGS_IDX["Temperature"]] = float(dctIn[strDoc+"CameraTemperature"])
			
			# get timestamp; assume GPS time is zulu time: parse date and replace timezone
			lstRow[MAP_HEADINGS_IDX["Timestamp"]] = float(dctIn[strDoc+"TimeStamp"])
			# TimeGPS is given in UTC: append a "Z" to mark it
			# and let strptime %z sort it out
			lstRow[MAP_HEADINGS_IDX["TimeGPS"]] = datetime.datetime.strptime(dctIn[strDoc+"GPSDateTime"]+"Z","%Y:%m:%d %H:%M:%S.%f%z",).timestamp()
			
			lstRow[MAP_HEADINGS_IDX["Distance"]] = fltDistance
		except KeyError as e:
			pass # invalid input (incomplete last entry?)
		else:
			try:
				lstRowPrev = dctOut["rows"][-1]
				dctOut["rows"].append(lstRow)
			except:
				# first row
				dctOut["rows"] = [lstRow]
				lstRowPrev = lstRowInit
			
			# calculate values from previous row
			#  - distance: previous speed * previous duration = current distance
			#  - true course: current coords - previous coords -> previous and current TC
			#  - variometer: current coords - previous coords ->  previous and current Vario
			#
			# since GPS coords are used for these calculations, only do this
			# if horizontal dilution of precision is good enough (see --hdop arg)
			# and the speed is greater than the set threshold
			if fltHDOP <= args.hdop and lstRow[MAP_HEADINGS_IDX["GPSSpeed3D"]] >= args.minspeed:
				try:
					fltDistance = fltDistance + lstRowPrev[MAP_HEADINGS_IDX["GPSSpeed2D"]] * lstRowPrev[MAP_HEADINGS_IDX["Duration"]]
				except (TypeError,ValueError):
					pass
				
				# see https://edwilliams.org/avform147.htm
				# (local, flat earth approximation)
				try:
					Lat0 = lstRowPrev[MAP_HEADINGS_IDX["Latitude"]]
					dLat = lstRow[MAP_HEADINGS_IDX["Latitude"]] - Lat0
					dLon = lstRow[MAP_HEADINGS_IDX["Longitude"]] - lstRowPrev[MAP_HEADINGS_IDX["Longitude"]]
					dN = math.radians(dLat)
					dE = math.cos(math.radians(Lat0))*math.radians(dLon)
					TC = int(math.degrees(math.atan2(dE,dN) % (2*math.pi)))
					lstRowPrev[MAP_HEADINGS_IDX["TrueCourse"]] = TC
					lstRow[MAP_HEADINGS_IDX["TrueCourse"]] = TC
				except (TypeError,ValueError):
					pass
				
				try:
					dAlt = lstRow[MAP_HEADINGS_IDX["Altitude"]] - lstRowPrev[MAP_HEADINGS_IDX["Altitude"]]
					lstRowPrev[MAP_HEADINGS_IDX["Vario"]] = dAlt / lstRow[MAP_HEADINGS_IDX["Duration"]]
					lstRow[MAP_HEADINGS_IDX["Vario"]] = dAlt / lstRow[MAP_HEADINGS_IDX["Duration"]]
				except (TypeError,ValueError):
					pass
			
			# determine mins/max; special case accel/gyro: get min/max of vector
			try:
				lstMin = dctOut["min"]
				lstMax = dctOut["max"]
			except KeyError:
				lstMin = [None]*len(HEADINGS)
				lstMax = [None]*len(HEADINGS)
				
			for i in range(len(HEADINGS)):
				valMin = lstMin[i]
				valMax = lstMax[i]
				if type(lstRow[i]) == list:
					valCurrMin = min(lstRow[i])
					valCurrMax = max(lstRow[i])
				else:
					valCurrMin = lstRow[i]
					valCurrMax = valCurrMin
				if valMin is None:
					lstMin[i] = valCurrMin
				elif valCurrMin is not None:
					lstMin[i] = min(valMin,valCurrMin)
				if valMax is None:
					lstMax[i] = valCurrMax
				elif valCurrMax is not None:
					lstMax[i] = max(valMax,valCurrMax)
			dctOut["min"] = lstMin
			dctOut["max"] = lstMax
			
		# move on
		intIdx = intIdx + 1
	
	# write JSON data to file
	json.dump(dctOut,args.FILE)
	
	# write last row as JSON dictionary to stdout
	# only print the keys passed via lastrow
	lstKeys = []
	for strKey in str(args.lastrow).split(","):
		if strKey == "all":
			lstKeys = HEADINGS
			break
		elif strKey in HEADINGS:
			lstKeys.append(strKey)
	if lstKeys:
		print( json.dumps( { strKey:dctOut["row"][-1][MAP_HEADINGS_IDX[strKey]] for strKey in lstKeys } ) )
