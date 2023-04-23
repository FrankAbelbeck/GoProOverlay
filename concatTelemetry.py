#!/usr/bin/env python3
"""Frank Abelbeck GoPro Telemetry Overlay Toolset: concatenate JSON telemetry files
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
import json
import sys

if __name__ == "__main__":
	parser = argparse.ArgumentParser(description="Concat telemetry JSON data (from convertTelemetry.py), and write the result to a new file.")
	parser.add_argument("--version", action="version", version="20230419")
	parser.add_argument("OUT",
		help="Telemetry JSON file; concatenated output ",
		type=argparse.FileType('w')
	)
	parser.add_argument("IN",
		help="Telemetry JSON file; input for concatenation",
		type=argparse.FileType('r'),
		nargs="+"
	)
	parser.add_argument("--sortkey",
		help="Identifier of the column used for final row sorting (default: 'TimeGPS')",
		default="TimeGPS"
	)
	args = parser.parse_args()
	
	dctOut = {}
	intIdxSort = 0
	for fFileIn in args.IN:
		print(f"appending file {fFileIn.name}")
		try:
			dctIn = json.load(fFileIn)
			if not (len(dctIn["headings"]) == len(dctIn["rows"][0]) == len(dctIn["min"]) == len(dctIn["max"])):
				raise ValueError("length mismatch")
		except Exception as e:
			print(f"Invalid file '{fFileIn.name}'; ignoring file ({e}).",file=sys.stderr)
			continue
		try:
			if dctOut["headings"] != dctIn["headings"]:
				print(f"Headings in {fFileIn.name} don't match; ignoring file.",file=sys.stderr)
			else:
				dctOut["rows"].extend(dctIn["rows"])
				dctOut["min"] = [ min(dctOut["min"][intIdx],value) for intIdx,value in enumerate(dctIn["min"]) ]
				dctOut["max"] = [ max(dctOut["max"][intIdx],value) for intIdx,value in enumerate(dctIn["max"]) ]
		except KeyError:
			# only reason: dctOut is empty, thus initialise with dctIn
			try:
				intIdxSort = dctIn["headings"].index(args.sortkey)
			except ValueError:
				print(f"Requested sort key '{args.sortkey}' not found in file '{fFileIn.name}'; ignoring file.",file=sys.stderr)
			else:
				dctOut = dctIn
	
	if dctOut:
		# sort rows and dump to file
		dctOut["rows"].sort(key=lambda x: x[intIdxSort])
		print(f"Writing concatenated file '{args.OUT.name}'.")
		json.dump(dctOut,args.OUT)
	else:
		print(f"Nothing to write.")

