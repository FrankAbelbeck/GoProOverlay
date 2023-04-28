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

import argparse
import json
import sys
import csv
import datetime

if __name__ == "__main__":
	parser = argparse.ArgumentParser(description="Read telemetry JSON data (from convertTelemetry.py), and write GPS data as unicsv to stdout (suitable as stdin for gpsbabel).")
	parser.add_argument("--version", action="version", version="20230416")
	parser.add_argument("FILE",
		help="Telemetry JSON file",
		type=argparse.FileType('r')
	)
	args = parser.parse_args()
	
	# read JSON data from stdin
	dctIn = json.load(args.FILE)
	try:
		dctHdg = {strKey:intIdx for intIdx,strKey in enumerate(dctIn["headings"])}
	except KeyError:
		print("invalid telemetry JSON file (no headings)",file=sys.stderr)
	else:
		writer = csv.writer(sys.stdout)
		writer.writerow((
			"date",
			"time",
			"lat",
			"lon",
			"alt",
			"head",
			"speed",
			"hdop"
		))
		for lstRow in dctIn["rows"]:
			dt = datetime.datetime.utcfromtimestamp(lstRow[dctHdg["TimeGPS"]])
			try:
				writer.writerow((
					dt.strftime("%Y/%m/%d"),
					dt.strftime("%H:%M:%S.%f"),
					float(lstRow[dctHdg["Latitude"]]),
					float(lstRow[dctHdg["Longitude"]]),
					float(lstRow[dctHdg["Altitude"]]),
					float(lstRow[dctHdg["TrueCourse"]]),
					float(lstRow[dctHdg["GPSSpeed2D"]]),
					float(lstRow[dctHdg["HorizontalError"]]),
				))
			except (TypeError,ValueError):
				pass # ignore bad GPS data
