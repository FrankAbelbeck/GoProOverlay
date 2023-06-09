#!/usr/bin/env python3
"""Frank Abelbeck GoPro Telemetry Overlay Toolset: extract GPS from telemetry
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

STR_VERSION = "20230524"

import argparse
import json
import sys
import csv
import datetime
import math

PI2 = math.pi * 2

if __name__ == "__main__":
	parser = argparse.ArgumentParser(description="Read telemetry JSON data (from convertTelemetry.py), and write GPS data as unicsv to stdout (suitable as stdin for gpsbabel).")
	parser.add_argument("--version", action="version", version=STR_VERSION)
	parser.add_argument("FILE",
		help="Telemetry JSON file",
		type=argparse.FileType('r')
	)
	args = parser.parse_args()
	
	# read JSON data from stdin
	try:
		dctIn = json.load(args.FILE)
	except json.JSONDecodeError as e:
		print(f"error loading telemetry JSON file ({e})",file=sys.stderr)
	else:
		writer = csv.writer(sys.stdout)
		writer.writerow((
			"date",
			"time",
			"lat",
			"lon",
			"alt",
			"speed",
			"hdop"
		))
		for intIdx,fltTime in enumerate(dctIn["Timestamp"]):
			dt = datetime.datetime.utcfromtimestamp(fltTime)
			writer.writerow((
				dt.strftime("%Y/%m/%d"),
				dt.strftime("%H:%M:%S.%f"),
				dctIn["Latitude"][intIdx],
				dctIn["Longitude"][intIdx],
				dctIn["Altitude"][intIdx],
				dctIn["GPSSpeed2D"][intIdx],
				dctIn["GPSHorizontalError"][intIdx]
			))
