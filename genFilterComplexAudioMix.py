#!/usr/bin/env python3
"""Frank Abelbeck GoPro Telemetry Overlay Toolset: generate audio mix ffmpeg complex filter expression
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

import sys
import argparse

if __name__ == "__main__":
	parser = argparse.ArgumentParser(description="Generate a complex FFmpeg filter expression, mixing two audio tracks with defined volume adjusts, offsets, and tempo.")
	parser.add_argument("--version", action="version", version=STR_VERSION)
	parser.add_argument("--volcockpit",
		help="Cockpit audio stream volume adjustment",
		type=float,
		default=1.0
	)
	parser.add_argument("--volintercom",
		help="Intercom audio stream volume adjustment",
		type=float,
		default=1.0
	)
	parser.add_argument("--offset",
		help="Intercom audio stream offset value",
		type=float,
		default=0.0
	)
	parser.add_argument("--tempo",
		help="Intercom audio stream tempo adjustment",
		type=float,
		default=1.0
	)
	parser.add_argument("--dojoin",
		help="Join both tracks in 3.0 audio instead of mixing it to 2.0 stereo; output format should support 3.0",
		action="store_true"
	)
	args = parser.parse_args()
	
	strOutput = f"[0:a] volume={args.volcockpit} [cockpit]; [1:a] volume={args.volintercom} "
	
	if args.offset > 0:
		strOutput = strOutput + f", adelay={args.offset} "
	elif args.offset < 0:
		strOutput = strOutput + f", aselect=gt(t\,{-args.offset}) "
		
	if args.tempo != 1:
		strOutput = strOutput + f", atempo={args.tempo} "
	
	if args.dojoin:
		strOutput = strOutput + ", apad [intercom]; [cockpit][intercom] join=inputs=2:channel_layout=3.0:map=0.0-FL|0.1-FR|1.0-FC  [audio_muxed]"
	else:
		strOutput = strOutput + "[intercom]; [cockpit][intercom] amix=inputs=2:duration=first [audio_muxed]"
	
	print(strOutput,end="")
