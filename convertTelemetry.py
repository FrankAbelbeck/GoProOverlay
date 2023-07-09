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

STR_VERSION = "20230709"

import argparse   # argument parsing
import json       # JSON data structures
import itertools  # see batched: rearranging accelerometer/gyroscope vectors
import datetime   # timestamping
import math       # true course calculation; subset calculation rounding
import sys        # stdin/stdout
import math       # coordinate transformation
import re         # parse --offset and --calibrate
import numpy      # array handling, calculate central values
import scipy.interpolate # interpolate data rows
import scipy.spatial.transform # deal with quaternions
import scipy.stats # calculate central values


MAP_STATISTICS_METHOD = {
	"median": numpy.median,
	"mean": numpy.mean,
	"meanGeometric": scipy.stats.gmean,
	"meanHarmonic": scipy.stats.hmean,
	"meanPower": scipy.stats.pmean,
	None: numpy.median
}

STR_RE_FLT = "[0-9]+(?:\.[0-9]+)?"
STR_RE_FLT_SIGNED = f"[+-]?{STR_RE_FLT}"
STR_RE_TRANGE = f"(?:{STR_RE_FLT})?(?:-{STR_RE_FLT}|-)?"
RE_OFFSET = re.compile(fr'''(.+?)=(.+?):({STR_RE_FLT})?-({STR_RE_FLT})?(?::(.+?))?''')


DEFAULT_ARG_HDOP      = 10.0   # mediocre horizontal dilution of precision
DEFAULT_ARG_MINSPEED  = 1.0    # min speed 1 m/s
DEFAULT_ARG_GRAV      = "XZY"  # gravity vector component mapping
DEFAULT_ARG_QUAT      = "RXZY" # quaternion mapping
DEFAULT_ARG_EULER_SEQ = "ZXY"  # quaternion -> euler mapping sequence 
DEFAULT_COORD_ACCL    = "XYZ"  # acceleration/gyroscope component mapping
DEFAULT_ARG_CALGRAV   = "-1"   # timeframe for gravity calibration
DEFAULT_ARG_ORIOUT    = "yxz"  # mapping of roll/pitch/yaw angles to the output axes (invert all, swap x and y)


def statisticsMethods():
	return [k for k in MAP_STATISTICS_METHOD.keys() if k is not None]


def processCalGravArgs(strCalGrav,fltFramerate):
	"""Process a gravity vector calibration argument string.

Args:
   strCalGrav: a string.
   fltFramerate: a float; number of frames/second, used for index calculations.

Returns:
   A frame index slice.

"""
	strT0,strSep,strT1 = strCalGrav.partition("-")
	if not strSep:
		print(f"ignoring invalid argument '--calGrav {strCalGrav}'",file=sys.stderr)
		return slice(0,0)
	try:
		intIdxT0 = int(float(strT0)*fltFramerate)
	except:
		intIdxT0 = 0
	try:
		intIdxT1 = int(float(strT1)*fltFramerate)+1
	except:
		intIdxT1 = None
	return slice(intIdxT0,intIdxT1)


def processOffsetArgs(lstStrOffsets,fltFramerate):
	"""Process given list of offset argument strings.

Args:
   lstStrOffsets: a list of strings.
   fltFramerate: a float; number of frames/second, used for index calculations.

Returns:
   A dictionary, mapping telemetry key strings to a list of 3-tuples
   (expected value, frame index slice, central value calculation function).
"""
	dctOffsets = {}
	for strOffset in lstStrOffsets:
		try:
			strKey,strValue,strT0,strT1,strMethod = RE_OFFSET.fullmatch(strOffset).groups()
			varValue = json.loads(strValue)
			if strT0:
				intIdxT0 = int(float(strT0)*fltFramerate)
			else:
				intIdxT0 = 0
			if strT1:
				intIdxT1 = int(float(strT1)*fltFramerate)+1
			else:
				intIdxT1 = None
			if intIdxT0 == intIdxT1:
				intIdxT1 = intIdxT1 + 1
		except (AttributeError,re.error) as e:
			print(f"ignoring invalid argument '--offset {strOffset}' (parsing failed: {e})",file=sys.stderr)
		except KeyError:
			print(f"ignoring invalid argument '--offset {strOffset}' (unknown column name {strKey})",file=sys.stderr)
		except (TypeError,ValueError) as e:
			print(f"ignoring invalid argument '--offset {strOffset}' (invalid value: {e})",file=sys.stderr)
		else:
			try: # if no method is specified, strMethod is matched as None, and None is defined in MAP_STATISTICS_METHOD
				funMethod = MAP_STATISTICS_METHOD[strMethod]
			except KeyError:
				print(f"ignoring invalid argument '--offset {strOffset}' (invalid method {strMethod})",file=sys.stderr)
			else:
				dctOffsets.setdefault(strKey,[]).append([varValue,slice(intIdxT0,intIdxT1),funMethod])
	return dctOffsets


class Orientation:
	"""Class for definition of an orientation.
"""
	def __init__(self,strIn,strAxes,strDefault,boolParseSign=True):
		"""Constructor: initialise an Orientation instance.

Args:
   strIn: a string; a sequence of axis identifiers.
   strAxes: a string; definition of axis identifiers (usually x,y,z) and their
            order; 'xyz' means 'x' = axis 0, 'y' = axis 1, and 'z' = axis 2.
   strDefault: a string; default sequence if something goes wrong.
   boolParseSign: a boolean; if True, interpret lower case as axis inversion.
"""
		self._strAxes = str(strAxes)
		self._dctAxes = {strChar.lower():intIdx for intIdx,strChar in enumerate(self._strAxes)}
		self._strDefault = str(strDefault)
		if len(self._strDefault) != len(self._strAxes) or not all([i in strAxes.lower() for i in strIn.lower()]):
			self._strDefault = self._strAxes
		
		self._strOrientation = self._strDefault
		try:
			if len(strIn) == len(self._strAxes) and all([i in strAxes.lower() for i in strIn.lower()]):
				self._strOrientation = strIn
		except:
			pass
		
		self._dctMap = {self._dctAxes[strChar.lower()]:intIdx for intIdx,strChar in enumerate(self._strOrientation)}
		if boolParseSign == True:
			self._dctSign = {self._dctAxes[strChar.lower()]:-1 if strChar.islower() else +1 for i,strChar in enumerate(self._strOrientation)}
		else:
			self._dctSign = None
	
	def mangle(self,lstVector):
		"""Re-order the components of given vector.

Args:
   lstVector: a list or tuple.

Returns:
   A list of same length.

Raises:
   IndexError: lstVector is smaller than the defined sequence.
"""
		if self._dctSign is None:
			return [lstVector[self._dctMap[i]] for i in range(len(self._dctMap))]
		else:
			return [self._dctSign[i]*lstVector[self._dctMap[i]] for i in range(len(self._dctMap))]
	
	def mangleSeries(self,arrSeries):
		"""Re-order the components of all vectors in given list/array.

Args:
   arrSeries: a list/array of lists/tuples (vectors).

Returns:
   A numpy.array of same dimensions.

Raises:
   IndexError: vectors are smaller than the defined sequence.
"""
		return numpy.array([self.mangle(varVector) for varVector in arrSeries])
	
	def __str__(self):
		"""Return the axis sequence string.
"""
		return self._strOrientation


def appendTypedListFromString(strIn,funConversion,intDim,oriOrientation,fltTimestamp,fltDuration,dctOut,strKeyOut):
	"""Split given string along spaces, apply given conversion function to each item,
group intDim items as vectors, multiply with the sign vector derived from
lstOrientation, and append the vector to the list at dctOut[strKeyOut].

If applying the conversion function fails, the function returns, with a length 0.

If applying the sign vector fails (either being not defined, or items being
non-numeric, this is silently ignored. In that case the items are appended
unaltered.

If fltTimestamp or fltDuration are non-numeric, bail out early, without error.

Args:
   strIn: a string.
   funConversion: a function, accepting one argument.
   intDim: an integer, number of the group members (i.e. vector dimension).
   oriOrientation: an Orientation or subclass instance.
   fltTimestamp: a float, timestamp of the first value.
   fltDuration: a float, overall duration of the samples.
   dctOut: an output dictionary.
   strKeyOut: a string addressing an entry in dctOut.
"""
	try:
		lstInputRaw = list(map(funConversion,str(strIn).split()))
		t = fltTimestamp
		dt = fltDuration*intDim/len(lstInputRaw)
	except:
		return 0
	
	for intIdx in range(0,len(lstInputRaw),intDim):
		lstVector = oriOrientation.mangle(lstInputRaw[intIdx:intIdx+intDim])
		dctOut.setdefault(strKeyOut,[]).append((t,lstVector))
		t = t + dt


def appendValueFromDict(dctIn,strKeyIn,funConversion,fltTimestamp,dctOut,strKeyOut):
	"""Read a value from given dict, apply the given conversion function, and write the
result with timestamp back to the output dictionary.

Args:
   dctIn: a dictionary.
   strKeyIn: a string.
   funConversion: a function, accepting one argument.
   fltTimestamp: a float, timestamp of the first value.
   dctOut: an output dictionary.
   strKeyOut: a string addressing an entry in dctOut.
"""
	try:
		varValue = funConversion( dctIn[strKeyIn] )
	except:
		pass
	else:
		dctOut.setdefault(strKeyOut,[]).append((fltTimestamp,varValue))


def funConvertGPSTime(varIn):
	"""Interpret given value as string and convert it to a UNIX timestamp.

Assumes the string being given in following format:

   %Y:%m:%d %H:%M%S.%f

(see strptime for details)

A "Z" will be added, so that the date string is interpreted as UTC.

Args:
   varIn: a value; will be cast to string.

Returns:
   A float, seconds since the Epoch.
"""
	# GPSTime is given in UTC: append a "Z" to mark it
	# and let strptime %z sort it out
	return datetime.datetime.strptime(str(varIn)+"Z","%Y:%m:%d %H:%M:%S.%f%z",).timestamp()


class NumpyArrayEncoder(json.JSONEncoder):
	"""JSON numpy value encoder.

Converts numpy types to JSON-encodable types, i.e.

   numpy.ndarray -> list
   numpy.floating -> float
   numpy.integer -> int
"""
	def default(self, varObj):
		if isinstance(varObj,numpy.ndarray):
			return varObj.tolist()
		# elif isinstance(varObj,numpy.ma.MaskedArray):
		# 	return varObj.filled(None)
		elif isinstance(varObj,numpy.floating):
			return float(varObj)
		elif isinstance(varObj,numpy.integer):
			return int(varObj)
		else:
			return super().default(varObj)


if __name__ == "__main__":
	# initialise argument parser and parse arguments
	parser = argparse.ArgumentParser(
		description="Read GoPro telemetry JSON data (as extracted by exiftool) from stdin, and write revised JSON data to stdout."
	)
	parser.add_argument("--version", action="version", version=STR_VERSION)
	parser.add_argument("FILE",
		help="Output JSON telemetry file",
		type=argparse.FileType('w')
	)
	parser.add_argument("--hdop",
		help="Set the maximum horizontal dilution of precision (HDOP) value for which GPS data is accepted. "
			"Excellent: 1-2; good: 2-5; moderate: 5-10; fair: 10-20; poor: 20+ "
			f"Default: {DEFAULT_ARG_HDOP}",
		type=float,
		default=DEFAULT_ARG_HDOP
	)
	parser.add_argument("--minspeed",
		help="Set the minimum GPS speed (3D, metres/second) that has to be reached to do calculations on true course and rate of descend. "
		f"Default: {DEFAULT_ARG_MINSPEED}",
		type=float,
		default=DEFAULT_ARG_MINSPEED
	)
	parser.add_argument("--offset",
		metavar="K=V:T0-T1:M",
		help="Calculate offset of all values of column named K in given timeframe T0 to T1 (given in seconds) from expected value V. "
			"Use the method M (default: median) to get obtain the central tendency of all measured values. "
			"If T0 is empty, the minimal timestamp is used. "
			"If T1 is empty, the maximal timestamp is used. "
			"Multiple offsets are reduced to one offset value, weighted by timeframe lengths. "
			"Valid statistics methods: " + ", ".join(statisticsMethods()),
		action="append",
		default=[]
	)
	parser.add_argument("--grav",
		help="Define the coordinate mapping of components of the gravity vector. "
			"Expects a 3-letter string consisting of the characters X, Y, and Z. "
			"If a letter is lower-case, the axis is inverted. "
			f"Default (GoPro HERO9): '{DEFAULT_ARG_GRAV}'",
		default=DEFAULT_ARG_GRAV
	)
	parser.add_argument("--quat",
		help="Define the coordinate mapping of components of quaternions (camera and image orientation). "
			"Expects a 4-letter string consisting of the characters R (real component), X, Y, and Z. "
			"If a letter is lower-case, the axis is inverted. "
			f"Default (GoPro HERO 9): '{DEFAULT_ARG_QUAT}'",
		default=DEFAULT_ARG_QUAT
	)
	parser.add_argument("--euler",
		help="Define the axis sequence used for quaternion-to-euler-angle calculation. "
			"Expects a 3-letter string consisting of the characters X, Y, Z. "
			"If all letters are lower-case, an extrinsic rotation about the axes of the original coordinate system is applied. "
			"Otherweise an intrinsic rotation about the axes of the rotating coordinate system is applied. "
			f"Default (GoPro HERO9): '{DEFAULT_ARG_EULER_SEQ}'",
		default=DEFAULT_ARG_EULER_SEQ
	)
	parser.add_argument("--oriOut",
		help="Define the axis mapping of roll, pitch, and yaw. "
			"This is applied after getting the Euler angles from the quaternions. "
			"Expects a 3-letter string consisting of the characters X, Y, and Z. "
			"If a letter is lower-case, the axis is inverted. "
			f"Default (GoPro HERO9): '{DEFAULT_ARG_ORIOUT}'",
		default=DEFAULT_ARG_ORIOUT
	)
	parser.add_argument("--calGrav",
		metavar="T0-T1",
		help="Determine the camera's orientation by aligning the gravity vector with the ideal gravity vector (0,0,1)^t. "
			"Calculates the median of all gravity vector samples between timestamp T0 and T1, given in seconds. "
			"If T0 is empty, the minimal timestamp is used. "
			"If T1 is empty, the maximal timestamp is used. "
			"If T1 equals T2, gravity calibration is disabled. "
			f"Default: '{DEFAULT_ARG_CALGRAV}'",
		default=DEFAULT_ARG_CALGRAV
	)
	parser.add_argument("--noTCmatch",
		help="Per default, the program tries to match yaw angle and true course if valid information is available. "
			"This can be disabled with this option. ",
		action="store_true"
	)
	parser.add_argument("--noRPYZero",
		help="Per default, the program tries to zero both roll and pitch. Yaw is zeroed if no TC match is possible. "
			"This can be disabled with this option. ",
		action="store_true"
	)
	args = parser.parse_args()
	
	# read JSON data from stdin
	dctIn = json.load(sys.stdin)[0]
	
	# prepare sample interpolation: get argument, set to framerate if unset
	try:
		fltFramerate = float(dctIn["Main"]["VideoFrameRate"])
		fltDurationOverall = float(dctIn["Main"]["Duration"])
	except (TypeError,ValueError,KeyError) as e:
		print(f"error parsing the JSON stream ({e})",file=sys.stderr)
		sys.exit(1)
	if fltFramerate == 0:
		print(f"error, video reports framerate = 0",file=sys.stderr)
		sys.exit(1)
	elif fltDurationOverall == 0:
		print(f"error, video reports duration = 0",file=sys.stderr)
		sys.exit(1)
	
	# collect all offset arguments, prepare data structure
	# so that main loop collects the right values; avoids another loop afterwards
	dctOffsets = processOffsetArgs(args.offset,fltFramerate)
	slcCalGrav = processCalGravArgs(args.calGrav,fltFramerate)
	
	# get definitions for gravity vector and quaternion orientations
	# catch invalid input, create sign vectors and finally convert to uppercase (if mapping to dictionary keys like GravityX)
	oriGrav  = Orientation(args.grav,  "xyz", DEFAULT_ARG_GRAV)
	oriQuat  = Orientation(args.quat,  "xyzr",DEFAULT_ARG_QUAT)
	oriEuler = Orientation(args.euler, "xyz", DEFAULT_ARG_EULER_SEQ,False)
	oriOut   = Orientation(args.oriOut,"xyz", DEFAULT_ARG_ORIOUT)
	
	# main processing loop:
	# - create a new document name string
	#   (-g3 option of exiftool creates "DOC*" dicts)
	# - incomplete data: reading any required var failed -> break loop
	# - incomplete data: duration is zero -> break loop
	# - derive values (rate of climb, true course, distance accumulation)
	# - extract Euler angles, see https://en.wikipedia.org/wiki/Conversion_between_quaternions_and_Euler_angles
	#
	# 20230608: removed "min"/"max"
	# 20230623: changed JSON layout to simple dict; simplified vector conversion
	# 20230709: cleaned up quaternion/Euler battlefield
	intIdx = 0
	dctOut = {}
	rotCalGrav = scipy.spatial.transform.Rotation.identity()
	while True:
		intIdx = intIdx + 1
		try:
			dctEntry = dctIn["Doc{}".format(intIdx)]
			fltDuration  = dctEntry["SampleDuration"]
			fltTimestamp = dctEntry["SampleTime"]
		except (TypeError,ValueError,KeyError):
			break
		else:
			pass
		
		if fltDuration <= 0:
			break
		
		# get vector data
		oriInput = Orientation(dctEntry.get("InputOrientation",""),"xyz",DEFAULT_COORD_ACCL)
		appendTypedListFromString(
			dctEntry.get("Accelerometer",""), float, 3,
			oriInput,
			fltTimestamp, fltDuration,
			dctOut, "Acceleration"
		)
		appendTypedListFromString(
			dctEntry.get("Gyroscope",""), float, 3,
			oriInput,
			fltTimestamp, fltDuration,
			dctOut, "Gyroscope"
		)
		appendTypedListFromString(
			dctEntry.get("GoPro_GRAV",""), float, 3,
			oriGrav,
			fltTimestamp, fltDuration,
			dctOut, "Gravity"
		)
		appendTypedListFromString(
			dctEntry.get("GoPro_CORI",""), float, 4,
			oriQuat,
			fltTimestamp, fltDuration,
			dctOut, "CameraAngle"
		)
		appendTypedListFromString(
			dctEntry.get("GoPro_IORI",""), float, 4,
			oriQuat,
			fltTimestamp, fltDuration,
			dctOut, "ImageAngle"
		)
		
		# get GPS data
		appendValueFromDict(dctEntry,"GPSLatitude",float,fltTimestamp,dctOut,"Latitude")
		appendValueFromDict(dctEntry,"GPSLongitude",float,fltTimestamp,dctOut,"Longitude")
		appendValueFromDict(dctEntry,"GPSAltitude",float,fltTimestamp,dctOut,"Altitude")
		appendValueFromDict(dctEntry,"GPSSpeed",float,fltTimestamp,dctOut,"GPSSpeed2D")
		appendValueFromDict(dctEntry,"GPSSpeed3D",float,fltTimestamp,dctOut,"GPSSpeed3D")
		appendValueFromDict(dctEntry,"GPSHPositioningError",float,fltTimestamp,dctOut,"GPSHorizontalError")
		appendValueFromDict(dctEntry,"GPSDateTime",funConvertGPSTime,fltTimestamp,dctOut,"GPSTime")
		
		# get misc data
		appendValueFromDict(dctEntry,"CameraTemperature",float,fltTimestamp,dctOut,"Temperature")
	
	# values are sampled at different rates (GPS, Temp etc: 1 Hz, CORI at framerate, Accl/Gyro > 100 Hz)
	# so upsample/downsample all values to the framerate (since in the end we want to process frames)
	# afterwards, apply any defined offsets
	intLenTNew = round(fltDurationOverall*fltFramerate)
	arrTNew = numpy.linspace(0,fltDurationOverall,intLenTNew) #[i/fltFramerate for i in range(intLenTNew)]
	
	# freeze key list and put "Gravity" first (so that camera angle gets gravity calibration data)
	lstStrKeys = list(dctOut.keys())
	try:
		lstStrKeys.remove("Gravity")
	except:
		pass
	else:
		lstStrKeys.insert(0,"Gravity")
	
	for strKey in lstStrKeys:
		try:
			lstT,lstY  = zip(*dctOut[strKey])
		except ValueError:
			pass
		else:
			if strKey == "ImageAngle" or strKey == "CameraAngle":
				# transform quaternions to rotations
				# apply output axis transformation (depending on mount direction)
				# finally, get euler angles and unwrap
				lstY = scipy.spatial.transform.Rotation.from_quat(lstY)
				if strKey == "CameraAngle":
					lstY = rotCalGrav * lstY
				lstY = numpy.unwrap(oriOut.mangleSeries(oriEuler.mangleSeries(lstY.as_euler(str(oriEuler)))),axis=0)
			
			cs = scipy.interpolate.CubicSpline(lstT,lstY)
			dctOut[strKey] = cs(arrTNew)
			# get derivatives needed later on
			match strKey:
				case "Latitude":
					dLatitudeDt = cs.derivative()(arrTNew)
				case "Longitude":
					dLongitudeDt = cs.derivative()(arrTNew)
				case "Altitude":
					dAltitudeDt = cs.derivative()(arrTNew)
					dctOut["Vario"] = dAltitudeDt
				case "GPSSpeed2D":
					dctOut["GPSAcceleration2D"] = cs.derivative()(arrTNew)
				case "GPSSpeed3D":
					dctOut["GPSAcceleration3D"] = cs.derivative()(arrTNew)
				case "Gravity":
					# get median of gravity vector at defined timeframe
					# assuming the system being at rest, use it to calibrate the camera's mount angles
					#
					# ideal gravity vector    = g_i = [0,0,1] (roughly measured with camera's z axis pointing up)
					# measured gravity vector = g_m = [gx,gy,gz]
					#
					# angle around x axis (gx=0): use dot product
					#       g_i dot g_m = (0*gx + 0*gy + 1*gz) = abs(g_i) * abs(g_m) * cos(angleX)
					#   <=> gz = sqrt(gx**2+gy**2+gz**2) * cos(angleX)
					#   <=> angleX = arccos( gz / sqrt(gy**2 + gz**2) )
					#
					# 1) determine angle around x
					# 2) rotate around x
					# 3) determine angle around y, in fixed coord sys, looking at rotated g_m
					# 4) rotate around y
					# 5) determine angle around z, in fixed coord sys, looking at rotated g_m
					# 6) create rotation instance with sequence "xyz"
					try:
						arrGrav = dctOut["Gravity"][slcCalGrav]
					except:
						pass
					else:
						if len(arrGrav) > 0:
							gx,gy,gz = g_m = numpy.median(arrGrav,axis=0)
							angleX = numpy.arccos(gz / numpy.sqrt(gy**2 + gz**2))
							gx,gy,gz = scipy.spatial.transform.Rotation.from_euler("x",[angleX]).apply(g_m)[0]
							angleY = numpy.arccos(gz  / numpy.sqrt(gx**2 + gz**2))
							gx,gy,gz = scipy.spatial.transform.Rotation.from_euler("xy",[angleX,angleY]).apply(g_m)
							angleZ = numpy.arccos(gy  / numpy.sqrt(gx**2 + gy**2))
							rotCalGrav = scipy.spatial.transform.Rotation.from_euler("xyz",[angleX,angleY,angleZ])
							print(f"Rotation 'xyz' based on measured gravity vector: {rotCalGrav.as_euler('xyz',degrees=True)}",file=sys.stderr)
					
	dctOut["Timestamp"] = arrTNew
	
	# calculate offset values
	for strKey,lstOffset in dctOffsets.items():
		if strKey not in dctOut:
			print(f"skipping offset calculation due to requested column '{strKey}' doesn't exist")
			continue
		varOffset = None
		intLenSum = 0
		for varValue,slcIdx,funMethod in lstOffset:
			try:
				varValue = numpy.array(varValue)
			except:
				print(f"ignoring invalid value '{varValue}' for column '{strKey}'",file=sys.stderr)
				continue
			if varOffset is None:
				try:
					varOffset = numpy.zeros(len(varValue))
				except:
					varOffset = 0.0
			
			# calculate offset = expected_value - central_value
			# since more than one timeframe might be specified, sum all offsets, weighted by the length of each timeframe
			try:
				arrVal = dctOut[strKey][slcIdx]
				intLen = len(arrVal)
				if intLen > 0:
					varOffset = varOffset + intLen*(varValue - (funMethod(arrVal,axis=0)))
					intLenSum = intLenSum + intLen
			except Exception as e:
				print(f"error calculating offset in timeframe {arrTNew[slcIdx][0]-arrTNew[slcIdx][-1]} for column '{strKey}' ({e})",file=sys.stderr)
		
		if varOffset is not None:
			try:
				varOffset = varOffset / intLenSum
			except:
				pass
			else:
				print(f"calculated offset {varOffset} for column '{strKey}'",file=sys.stderr)
				dctOut[strKey] = varOffset + dctOut[strKey]
	
	# calculate true course, vario and GPS pitch
	# since GPS coords are used for these calculations, only do this
	# if horizontal dilution of precision is good enough (see --hdop arg),
	# and the speed needs to be greater than the set threshold
	#
	# create a mask for the values where precision > hdop OR speed < minspeed
	# (True = mask value, False = use value)
	arrMaskNotPrecise = numpy.logical_or(
		numpy.greater( dctOut["GPSHorizontalError"], args.hdop     ),
		numpy.less(    dctOut["GPSSpeed2D"],         args.minspeed ),
	)
	# mask latitude and derivatives of latitude/longitude/altitude
	arrMaskedLat    = numpy.ma.masked_array(dctOut["Latitude"], mask=arrMaskNotPrecise)
	arrMaskedDLatDt = numpy.ma.masked_array(dLatitudeDt,        mask=arrMaskNotPrecise)
	arrMaskedDLonDt = numpy.ma.masked_array(dLongitudeDt,       mask=arrMaskNotPrecise)
	arrMaskedDAltDt = numpy.ma.masked_array(dAltitudeDt,        mask=arrMaskNotPrecise)
	
	# calculate true course, variometer and GPS pitch
	# see https://edwilliams.org/avform147.htm
	# (local, flat earth approximation)
	dLat = arrMaskedDLatDt / fltFramerate
	dLon = arrMaskedDLonDt / fltFramerate
	dNorth = numpy.radians(dLat)
	dEast  = numpy.cos(numpy.radians(arrMaskedLat))*numpy.radians(dLon)
	# dNorth and dEast are given in radians
	# nautical miles: x * 60 * 180 / pi
	# metres: x * 60 * 180 / pi * 1852 = x * 20001600 / pi
	dNorth_m = 20001600 * dNorth / numpy.pi
	dEast_m  = 20001600 * dEast / numpy.pi
	dDist_m  = numpy.sqrt( dNorth_m**2 + dEast_m**2 )
	
	dctOut["TrueCourse"] = numpy.ma.masked_array( numpy.unwrap( numpy.arctan2(dEast,dNorth) ), mask=arrMaskNotPrecise )
	dctOut["TurnRate"] = scipy.interpolate.CubicSpline(arrTNew,dctOut["TrueCourse"]).derivative()(arrTNew)
	dctOut["DistanceStep"] = dDist_m
	# pitch angle derived from GPS data
	#
	#        - 
	#       /| dAlt
	#      / |
	#     /  |
	#    +---'
	#     distance travelled (in TC direction)
	#     = math.sqrt( dN**2 + dE**2 )
	#
	#  => pitch angle = atan2(dAlt,distance travelled)
	dctOut["GPSPitch"] = numpy.arctan2( dAltitudeDt/fltFramerate, dDist_m )
	
	# amplitude-shift yaw angle to match true course
	# since at least yaw seems to drift, apply linear regression on differences
	if not args.noTCmatch or not args.noRPYZero:
		arrCamAngle = dctOut["CameraAngle"].transpose()
		arrZero = numpy.array([0.0,0.0,0.0]).reshape((3,1))
		if dctOut["TrueCourse"].count() > 0:
			try:
				resLinReg = scipy.stats.mstats.linregress(arrTNew,dctOut["TrueCourse"] - arrCamAngle[2])
				arrCamAngle[2] = arrCamAngle[2] + resLinReg.intercept + resLinReg.slope * arrTNew
			except:
				pass
			else:
				print(f"Matched yaw angle to true course: drift={resLinReg.slope} offset={resLinReg.intercept}",file=sys.stderr)
		else:
			print("Zeroing yaw angle",file=sys.stderr)
			arrZero[2] = arrCamAngle[2][0]
		
		if not args.noRPYZero:
			for i in range(2):
			# 	try:
			# 		resLinReg = scipy.stats.mstats.linregress(arrTNew[intIdxCalGrav0:intIdxCalGrav1],-arrCamAngle[i][intIdxCalGrav0:intIdxCalGrav1])
			# 		arrCamAngle[i] = arrCamAngle[i] + resLinReg.intercept + resLinReg.slope * arrTNew
			# 	except Exception as e:
			# 		print(e)
			# 	else:
			# 		print(f"Matched {'roll' if i == 0 else 'pitch'} angle to zero: drift={resLinReg.slope} offset={resLinReg.intercept}",file=sys.stderr)
				arrZero[i] = arrCamAngle[i][0]
			print(f"Zeroed roll and pitch angle",file=sys.stderr)
		
		arrCamAngle = arrCamAngle - arrZero
		dctOut["CameraAngle"] = arrCamAngle.transpose()
	
	# wrap TrueCourse and Yaw to 0..2pi
	# wrap Roll and Pitch to -pi..pi
	dctOut["CameraAngle"] = numpy.mod( dctOut["CameraAngle"] + numpy.array([numpy.pi,numpy.pi,0.0]) , 2*numpy.pi) - numpy.array([numpy.pi,numpy.pi,0.0])
	dctOut["TrueCourse"] = numpy.mod( dctOut["TrueCourse"], 2*numpy.pi)
	
	# write JSON data to file
	try:
		json.dump(dctOut,args.FILE,cls=NumpyArrayEncoder)
	except Exception as e:
		print(f"error writing JSON file ({e})",file=sys.stderr)
	
