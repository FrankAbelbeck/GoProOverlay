#!/usr/bin/env python3
"""Frank Abelbeck GoPro Telemetry Overlay Toolset: generate speed up/down ffmpeg complex filter expression
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

import argparse
import sys
import codecs
import subprocess
import json

def processFloatFromList(lstChange,fltDefaultMissing,strMissing,strNonNumeric,strNegative):
	try:
		fltValue = lstChange.pop(0)
	except IndexError:
		if strMissing is None:
			fltValue = fltDefaultMissing
		else:
			raise ValueError(strMissing)
	if fltValue == "":
		fltValue = fltDefaultMissing
	else:
		try:
			fltValue = float(fltValue)
		except (TypeError,ValueError):
			raise ValueError(strNonNumeric)
	if fltValue < 0:
		raise ValueError(strNegative)
	return fltValue


if __name__ == "__main__":
	parser = argparse.ArgumentParser(description="Create the filter expression to speed up and/or slow down a video file.")
	parser.add_argument("--version", action="version", version="20230421")
	parser.add_argument("--change",metavar="TS:TE:SP",
		help="Change the video speed between start time TS and end time TE to a given speed factor SP (default 1 if empty, i.e. normal speed)",
		action="append",
		default=[]
	)
	parser.add_argument("FILE",
		help="Input video file for this filter expression",
	)
	parser.add_argument("--in",
		help="Input channel identifier (default: '0')",
		default="0",
		dest="input_channel"
	)
	parser.add_argument("--out",
		help="Output channel identifier (default: none)",
		default="",
		dest="output_channel"
	)
	parser.add_argument("--separator",
		help="Separator string between filter expressions (default: ' ')",
		default=" ",
	)
	parser.add_argument("--fps",
		help="Output framerate (default: use video framerate)",
	)
	parser.add_argument("--force",
		help="Don't trim overlapping video parts, print a warning instead.",
		action="store_true"
	)
	args = parser.parse_args()
	
	# get video properties
	try:
		intError,strOutput = subprocess.getstatusoutput(f"ffprobe -v error -select_streams v  -print_format json -show_entries stream {args.FILE}")
		if intError == 0:
			dctVideo = json.loads(strOutput)
			try:
				if args.fps is None:
					args.fps = dctVideo["streams"][0]["r_frame_rate"]
				fltDuration = float(dctVideo["streams"][0]["duration"])
			except (KeyError,IndexError):
				raise ValueError("probing video returned unexpected JSON data")
		else:
			raise ValueError("probing video exited with non-zero status")
	except Exception as e:
		print(f"error probing video {args.FILE}: {e}",file=sys.stderr)
		sys.exit(1)
	
	lstChange = []
	for strParams in args.change:
		# split change argument along colons and process values
		lstParams = strParams.split(":")
		try:
			fltStart = processFloatFromList(lstParams,0.0,"start time missing","non-numeric start time","negative start time")
			fltEnd   = processFloatFromList(lstParams,float("infinity"),"end time missing","non-numeric end time","negative end time")
			fltSpeed = processFloatFromList(lstParams,1.0,"speed factor missing","non-numeric speed factor","negative speed factor")
			if fltEnd <= fltStart:
				raise ValueError("end time smaller or equal start time")
		except ValueError as e:
			print(f"ignoring invalid argument '--change {strParams}' ({e})",file=sys.stderr)
			continue
		else:
			boolIgnore = False
			for intIdx,(fltS,fltE,fltSp) in enumerate(lstChange):
				# cases:
				#  1) fltStart...fltEnd...fltS...fltE --> insert before, unchanged
				#  2) fltStart...fltS...fltEnd...fltE --> insert before, fltEnd=fltS
				#  3) fltStart...fltS...fltE...fltEnd --> overwrite, i.e. discard fltS-fltE
				#  4) fltS...fltStart...fltE...fltEnd --> insert after, fltStart=fltE
				#  5) fltS...fltStart...fltEnd...fltE --> discard fltStart-fltEnd
				if fltStart < fltS:
					if fltEnd <= fltS:
						# case 1
						break
					elif fltEnd <= fltE:
						# case 2
						if args.force:
							print(f"Warning: partly overlapping video parts {fltS}-{fltE} and {fltStart}-{fltEnd}",file=sys.stderr)
						else:
							print(f"trimming partly overlapping video part {fltStart}-{fltEnd} to {fltStart}-{fltS}",file=sys.stderr)
							fltEnd = fltS
						break
					else:
						# case 3
						if args.force:
							print(f"Warning: video part {fltS}-{fltE} fully enclosed by {fltStart}-{fltEnd}",file=sys.stderr)
						else:
							print(f"discarding fully enclosed video part {fltS}-{fltE}, keeping {fltStart}-{fltEnd}",file=sys.stderr)
							lstChange[intIdx] = (fltStart,fltEnd,fltSpeed)
							boolIgnore = True
						break
				elif fltStart < fltE:
					if fltE < fltEnd:
						# case 4
						if args.force:
							print(f"Warning: partly overlapping video parts {fltS}-{fltE} and {fltStart}-{fltEnd}",file=sys.stderr)
						else:
							print(f"trimming partly overlapping video part {fltStart}-{fltEnd} to {fltE}-{fltEnd}",file=sys.stderr)
							fltStart = fltE
						break
					else:
						# case 5
						if args.force:
							print(f"Warning: video part {fltStart}-{fltEnd} fully enclosed by {fltS}-{fltE}",file=sys.stderr)
						else:
							print(f"Discarding fully enclosed video part {fltStart}-{fltEnd}, keeping {fltS}-{fltE}",file=sys.stderr)
							boolIgnore = True
						break
				elif fltEnd > fltDuration:
					if args.force:
						print(f"Warning: video part {fltStart}-{fltEnd} outside video timeframe",file=sys.stderr)
					else:
						print(f"trimming video part {fltStart}-{fltEnd} to {fltStart}-end to keep it inside video timeframe",file=sys.stderr)
						fltEnd = float("infinity")
					break
				elif fltStart > fltDuration:
					if args.force:
						print(f"Warning: video part {fltStart}-{fltEnd} outside video timeframe ",file=sys.stderr)
					else:
						print(f"discarding video part {fltStart}-{fltEnd} for being outside video timeframe",file=sys.stderr)
						boolIgnore = True
					break
					
			if not boolIgnore:
				lstChange.append((fltStart,fltEnd,fltSpeed))
	
	# sort change list and check that entire video timeframe is covered
	# if not (and force is not set), add speed=1 parts
	lstChange.sort()
	fltT = 0.0
	for intIdx,(fltStart,fltEnd,fltSpeed) in enumerate(lstChange):
		if fltT < fltStart:
			if args.force:
				print(f"Warning: video part {fltT}-{fltStart} is not processed",file=sys.stderr)
			else:
				# missing part fltT-fltStart, add speed=1 part
				print(f"Adding part with speed 1 at {fltT}-{fltStart}",file=sys.stderr)
				lstChange.insert(intIdx,(fltT,fltStart,1.0))
		fltT = fltEnd
	if fltT != float("infinity") and fltT < fltDuration:
		if args.force:
			print(f"Warning: video part {fltT}-end is not processed",file=sys.stderr)
		else:
			# doesn't end at video end (=duration), append speed=1 part
			print(f"Adding part with speed 1 at {fltT}-end",file=sys.stderr)
			lstChange.append((fltT,float("infinity"),1))
	
	# process lstChange and create filter strings for each entry
	lstFilter = []
	lstOutputs = []
	intIdx = 0
	for fltStart,fltEnd,fltSpeed in lstChange:
		strTrim = f"trim=start={fltStart}"
		if fltEnd != float("infinity"):
			strTrim = strTrim + f":end={fltEnd}"
		
		lstATempo = []
		fltASpeed = fltSpeed
		if fltASpeed > 1:
			while fltASpeed > 2:
				lstATempo.append(2)
				fltASpeed = fltASpeed / 2
			if fltASpeed != 1:
				lstATempo.append(fltASpeed)
		elif fltASpeed < 1:
			while fltASpeed < 1:
				lstATempo.append(0.5)
				fltASpeed = fltASpeed * 2
			if fltASpeed != 1:
				lstATempo.append(fltASpeed)
		else:
			lstATempo.append(1)
		
		lstOutputs.append(f"[v{intIdx}]")
		lstFilter.append(
			f"[{args.input_channel}:v] {strTrim}, " + 
			f"setpts=(PTS-STARTPTS)/{fltSpeed} " + 
			f" {lstOutputs[-1]};"
		)
		lstOutputs.append(f"[a{intIdx}]")
		lstFilter.append(
			f"[{args.input_channel}:a] a{strTrim}, " + 
			f"asetpts=(PTS-STARTPTS)/{fltSpeed}, " + 
			", ".join([ f"atempo={v}" for v in lstATempo ]) +
			f" {lstOutputs[-1]};"
		)
		intIdx = intIdx + 1
	
	if lstFilter:
		# finally, concatenate filter strings, add concat filter, add output channel if defined and print to stdout
		strFiler = "".join(lstOutputs) + f" concat=n={len(lstFilter)//2}:v=1:a=1 [tmpOut]; [tmpOut] framerate=fps={args.fps}"
		if args.output_channel:
			strFilter = strFilter + " [{args.output_channel}]"
		lstFilter.append(strFiler)
		print(codecs.decode(args.separator,"unicode_escape").join(lstFilter))
	else:
		print("warning: empty filter expression",file=sys.stderr)
