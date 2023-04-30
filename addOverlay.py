#!/usr/bin/env python3
"""Frank Abelbeck GoPro Telemetry Overlay Toolset: add an overlay to a video
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

# external module documentation:
#  https://github.com/imageio/imageio-ffmpeg
#  https://pillow.readthedocs.io/en/stable/reference/Image.html

# standard library modules
import sys
import os.path
import time
import importlib
import argparse
import json
import shlex
import math
import re
import statistics
import functools

# external dependencies
try:
	import imageio_ffmpeg
	import PIL.Image
	import PIL.ImageDraw
	import PIL.ImageFont
except ModuleNotFoundError as e:
	print(e)
	sys.exit(1)

class Overlay:
	"""Class for overlay-based video frame processing.

Overlay Definition:

An overlay is a sequence of commands, applied to a video frame. It is defined
as a JSON list of command lists. Each command list consists of a command
identifier, followed by a variable number of arguments.

The commands are applied in the same sequence as specified in the JSON file,
starting with the frame as base canvas.

Commands:

   ["mod", mod0, mod1, ...]
      request that given modules are loaded into the overlay's runtime scope;
      mod0..mod1 specify module name strings.
   
   ["img", path ]
      request that the image at given path is alpha-composited onto the frame.

   ["txt", x, y, anchor, align, format, font, size, colour]
      request that text is drawn onto the frame with...
      ...x,y    = origin
      ...anchor = alignment (cf text-anchors in https://pillow.readthedocs.io/)
      ...align  = text line alignment ("left", "center", "right")
      ...format = a string to be drawn; accepts also f-string constructs and
                  supports expression evaluation, making dynamic (telemetry)
                  content possible
      ...font   = name or path string of the truetype font to use
      ...size   = font size in pixels
      ...colour = hexadecimal colour specifier (#rgb, #rgba, #rrggbb, #rrggbbaa)

"""
	
	CMD_UNKNOWN = 0 # unknown command
	CMD_IMAGE = 1   # command: alpha-composite an image
	CMD_TEXT  = 2   # command: draw text
	
	def __init__(self,fJSON):
		"""Constructor: initialise an instance.

Args:
   fJSON: a file-like object; JSON source of overlay commands.

Raises:
   json.JSONDecodeError: invalid JSON input.
"""
		self._lstSteps = []
		self._dctFonts = {}
		self._dctGlobals = {}
		self._cwd = os.path.dirname(os.path.realpath(os.path.expanduser(fJSON.name)))
		self.load(fJSON)
	
	def clear(self):
		"""Clear all internal variables. Also closes any pre-loaded objects like images.
"""
		for step in self._lstSteps:
			try:
				step.close()
			except:
				pass
		self._lstSteps = []
		self._dctFonts = {}
		self._dctGlobals = {}
	
	def processFilename(self,strFilename):
		"""Process a filename string.

Expands ~ to current user's home directory;
joins to current working directory if relative;
generates canonical path.

Args:
   strFilename: a string.

Returns:
   A string.
"""
		strFilename = os.path.expanduser(strFilename) # expand ~ to /home/...
		if not os.path.isabs(strFilename):
			strFilename = os.path.join(self._cwd,strFilename) # join CWD and relative path
		return os.path.realpath(strFilename) # return canonical path, resolving symlinks
	
	def load(self,fJSON):
		"""Load a given JSON overlay command file.

Args:
   fJSON: a file-like object.

Raises:
   json.JSONDecodeError: invalid JSON input.
"""
		self.clear()
		for strCmd,*lstArgs in json.load(fJSON):
			match strCmd:
				case "mod":
					# command: announce python module to use
					# todo: load all modules given in args
					# modules are stored in separate dictionary that is passed
					# to exec when it comes to string format evaluation
					for strMod in lstArgs:
						if strMod in sys.stdlib_module_names:
							try:
								self._dctGlobals[strMod] = importlib.import_module(strMod)
							except ModuleNotFoundError:
								print(f"failed to load module '{strMod}' requested by overlay",file=sys.stderr)
						else:
							print(f"overlay requested module '{strMod}' which is not in the standard library",file=sys.stderr)
				case "img":
					# command: apply image
					# todo: pre-load said image
					lstArgs[0] = self.processFilename(lstArgs[0])
					# append CMD_IMAGE step, pre-load image in PIL as alpha-RGB
					try:
						self._lstSteps.append((
							self.CMD_IMAGE,
							PIL.Image.open(lstArgs[0]).convert("RGBA")
						))
					except KeyError:
						print(f"incomplete img command (no path given)",file=sys.stderr)
					except FileNotFoundError:
						print(f"failed to load image '{lstArgs[0]}' requested by overlay",file=sys.stderr)
				case "txt":
					try:
						intX = int(lstArgs[0])
						intY = int(lstArgs[1])
						strAnchor = str(lstArgs[2])
						strAlign = str(lstArgs[3])
						strFormat = str(lstArgs[4])
						strTTF = str(lstArgs[5])
						intSizePx = int(lstArgs[6])
						strColor = str(lstArgs[7])
					except (IndexError,TypeError,ValueError):
						print(f"failed to load text command",file=sys.stderr)
					else:
						try:
							fnt = self._dctFonts[(strTTF,intSizePx)]
						except KeyError:
							strTTF = self.processFilename(strTTF)
							try:
								fnt = PIL.ImageFont.truetype(strTTF,intSizePx)
								self._dctFonts[(strTTF,intSizePx)] = fnt
							except OSError:
								print(f"failed to load font '{strTTF}' requested by overlay",file=sys.stderr)
								continue
						try:
							codeFormat = compile(f'strText=f"{strFormat}"',"<string>","single")
						except SyntaxError as e:
							print(f"failed to compile format string '{strFormat}' requested by overlay: {e}",file=sys.stderr)
						else:
							self._lstSteps.append((
								self.CMD_TEXT,
								intX,intY,
								strAnchor,strAlign,
								codeFormat,
								fnt,
								strColor
							))
	
	def apply(self,frame,tplSize,dctTelemetry):
		"""Apply all Overlay commands to a given frame of given size.

Overlay commands can access the variables passed by dctTelemetry.

Args:
   frame: a bytes instance; interpreted as PIL.Image (mode RGB, size tplSize).
   tplSize: a 2-tuple of integers (width, height) defining the frame size.
	dctTelemetry: a dictionary defining variables for the given frame.
"""
		imgNew = PIL.Image.frombytes("RGB",tplSize,frame).convert("RGBA")
		drwNew = PIL.ImageDraw.Draw(imgNew)
		for intCmd,*tplArgs in self._lstSteps:
			match intCmd:
				case self.CMD_IMAGE:
					imgNew.alpha_composite(tplArgs[0])
				case self.CMD_TEXT:
					# pre-compiled string format code is executed in a safe environment
					# globals is defined by modules requested by the Overlay plus __builtins__,
					# locals is defined by the current telemetry info;
					# the result strText is stored in the locals dictionary, i.e. dctTelemetry
					try:
						exec(tplArgs[4],self._dctGlobals,dctTelemetry)
					except Exception as e:
						print(f"apply.text: string formatting failed ({e}",file=sys.stderr)
					else:
						drwNew.text(
							(tplArgs[0],tplArgs[1]),
							dctTelemetry["strText"],
							tplArgs[6],
							tplArgs[5],
							anchor=tplArgs[2],align=tplArgs[3]
						)
		return imgNew.convert("RGB").tobytes()


class Telemetry:
	"""Class granting access to JSON telemetry data.

Telemetry data is expected to be of the following form:

{
	"headings": ["heading0", ..., "headingN"],
	"rows" : [
		[field0, ..., fieldN]
		...
	],
	"min": [field0, ..., fieldN],
	"max": [field0, ..., fieldN]
}
"""
	
	MAP_STATISTICS_METHOD = {
		"median": statistics.median,
		"mean": statistics.mean,
		"gmean": statistics.geometric_mean,
		"hmean": statistics.harmonic_mean,
		"mode": statistics.mode,
		"multimodemax": lambda x: max(statistics.multimode(x)),
		"multimodemin": lambda x: min(statistics.multimode(x)),
		"multimodemean": lambda x: statistic.mean(statistics.multimode(x)),
		"multimodemedian": lambda x: statistics.median(statistics.multimode(x)),
		None: statistics.median
	}
	
	RE_OFFSET = re.compile(r'''(.+?)=(.+?):([0-9]*)-([0-9]*)(:(.+?))?''')
	
	def __init__(self, fJSON, fltFps, intNumFrames):
		"""Constructor: initialise instance.

Args:
   fJSON: a file-like object; telemetry data in JSON format.
   fltFps: a float, number of frames per seconds.
   intNumFrames: an integer, total number of expected frames.

Raises:
   TypeError, ValueError: invalid framerate.
   json.JSONDecodeError: invalid JSON input.
"""
		self._dctTele = {}
		self._dctHeadings = {}
		self._lstIdxFrameRow = []
		self.load(fJSON,fltFps,intNumFrames)
	
	@classmethod
	def statisticsMethods(cls):
		return [k for k in cls.MAP_STATISTICS_METHOD.keys() if k is not None]
	
	def load(self, fJSON, fltFps, intNumFrames):
		"""Load telemetry data from given JSON file.

Args:
   fJSON: a file-like object.
   fltFps: a float, expected framerate.
   intNumFrames: an integer, total number of expected frames.

Raises:
   json.JSONDecodeError: invalid JSON input.
"""
		self._lstOffsets = {}
		
		# load JSON data structure and create a mapping heading -> column index
		self._dctTele = json.load(fJSON)
		self._dctHeadings = {strKey:intIdx for intIdx,strKey in enumerate(self._dctTele["headings"])}
		
		intIdxTimestamp = self._dctHeadings["Timestamp"]
		intIdxDuration = self._dctHeadings["Duration"]
		
		intIdxRow = 0
		fltTimestampRow = self._dctTele["rows"][0][intIdxTimestamp]
		fltDurationRow = self._dctTele["rows"][0][intIdxDuration]
		# create a mapping structure, mapping frame number to row and row fraction
		self._lstIdxFrameRow = []
		for intIdxFrame in range(intNumFrames):
			fltTimestamp = intIdxFrame / fltFps
			while fltTimestamp > fltTimestampRow + fltDurationRow:
				intIdxRow = intIdxRow + 1
				fltTimestampRow = self._dctTele["rows"][intIdxRow][intIdxTimestamp]
				fltDurationRow = self._dctTele["rows"][intIdxRow][intIdxDuration]
			self._lstIdxFrameRow.append( (intIdxRow, (fltTimestamp - fltTimestampRow) / fltDurationRow) )
		# create timestamp vector for quick offset look-up
		self._lstTimestamps = [(lstRow[intIdxTimestamp],lstRow[intIdxDuration]) for lstRow in self._dctTele["rows"]]
	
	def get(self,intIdxFrame):
		"""Get telemetry data of the current frame and advance the internal pointers.

Returns:
   A dictionary, mapping all field names (as given in 'headings' to values).
"""
		# get row index that is minimal distant to the given fltTimestamp
		# pre-compiled in load(), so this is just a look-up of the frame index in _lstIdxFrameRow
		intIdx,fltSub = self._lstIdxFrameRow[intIdxFrame]
		dctReturn = {}
		for intIdxCol,value in enumerate(self._dctTele["rows"][intIdx]):
			try:
				# assume value is a sequence; interpolate using the pre-compiled index fraction
				dctReturn[self._dctTele["headings"][intIdxCol]] = value[int(len(value) * fltSub)]
			except TypeError:
				# value is not a sequence (e.g. gyro), so don't interpolate and just use the raw value
				dctReturn[self._dctTele["headings"][intIdxCol]] = value
		return dctReturn
	
	def addOffset(self,strOffset):
		#
		# parse strValue K=V:T0-T1:M
		#
		try:
			strKey,strValue,strT0,strT1,strMethodAll,strMethod = self.RE_OFFSET.fullmatch(strOffset).groups()
		except re.error as e:
			raise ValueError(f"argument parsing failed: {e}")
		
		try:
			intIdxKey = self._dctHeadings[strKey]
		except KeyError:
			raise ValueError("unknonw column name")
		
		try:
			fltValue = float(strValue)
		except (TypeError,ValueError) as e:
			raise ValueError(f"converting value failed: {e}")
		
		if strT0:
			try:
				fltT0 = float(strT0)
			except (TypeError,ValueError) as e:
				raise ValueError(f"converting timestamp 0 failed: {e}")
		else:
			fltT0 = float("-infinity")
		
		if strT1:
			try:
				fltT1 = float(strT1)
			except (TypeError,ValueError) as e:
				raise ValueError(f"converting timestamp 1 failed: {e}")
		else:
			fltT1 = float("+infinity")
		
		if fltT0 > fltT1:
			fltT0,fltT1 = fltT1,FltT0
		
		try:
			funMethod = self.MAP_STATISTICS_METHOD[strMethod]
		except KeyError:
			raise ValueError("invalid method")
		
		# iterate over rows, collect values for given timeframe,
		# determine central tendency, calculate offset, apply offset to all values
		lstValues = []
		for intIdx,(fltT,fltD) in enumerate(self._lstTimestamps):
			if fltT >= fltT0 and fltT < fltT1 + fltD:
				try:
					# assume vector value...
					lstValues.extend([v for v in self._dctTele["rows"][intIdx][intIdxKey] if v is not None])
				except TypeError:
					# just append if not iterable
					if self._dctTele["rows"][intIdx][intIdxKey] is not None:
						lstValues.append(self._dctTele["rows"][intIdx][intIdxKey])
		
		fltOffset = fltValue - funMethod(lstValues)
		print(f"applying offset {fltOffset} to column '{strKey}'")
		
		# apply offset to all values
		for lstRow in self._dctTele["rows"]:
			try:
				# assume vector value...
				for intIdxVal,fltVal in enumerate(lstRow[intIdxKey]):
					try:
						lstRow[intIdxKey][intIdxVal] = lstRow[intIdxKey][intIdxVal] + fltOffset
					except TypeError:
						pass # ignore None
			except TypeError:
				# ...just add offset
				try:
					lstRow[intIdxKey] = lstRow[intIdxKey] + fltOffset
				except TypeError:
					pass # ignore None


if __name__ == "__main__":
	parser = argparse.ArgumentParser(description="Add an Overlay to every frame of a given MP4 file.")
	parser.add_argument("--version", action="version", version="20230416")
	parser.add_argument("VIDEO",
		help="Video input file",
	)
	parser.add_argument("AUDIO",
		help="Audio input file",
	)
	parser.add_argument("OVERLAY",
		help="Overlay JSON file",
		type=argparse.FileType('r')
	)
	parser.add_argument("TELEMETRY",
		help="Telemetry JSON file",
		type=argparse.FileType('r')
	)
	parser.add_argument("OUTPUT",
		help="MP4 output file"
	)
	parser.add_argument("--vcodec",
		help="Video codec; default: libx264",
		default="libx264"
	)
	parser.add_argument("--acodec",
		help="Audio codec; default: copy",
		default="copy"
	)
	parser.add_argument("--params",
		help='Additional ffmpeg parameters, e.g. for the video and/or audio codec or to invoke a filter; specified as a command line string fragment; default: "-preset slow -crf 28 -tune film"',
		default="-preset slow -crf 28 -tune film"
	)
	parser.add_argument("--tqs",
		help="thread_queue_size for reading frames (default: 1024)",
		type=int,
		default=1024
	)
	parser.add_argument("--tprint",
		help="Number of seconds between updating the progress output (default: 5)",
		type=int,
		default=5
	)
	parser.add_argument("--offset",
		metavar="K=V:T0-T1:M",
		help="Calculate offset of all values of column named K in given timeframe T0 to T1 (given in seconds) from expected value V. "
			"Use the method M (default: median) to get obtain the central tendency of all measured values. "
			"If T0 is empty, the minimal timestamp is used. "
			"If T1 is empty, the maximal timestamp is used. "
			"Valid statistics methods: " + ", ".join(Telemetry.statisticsMethods()),
		action="append",
		default=[]
	)
	args = parser.parse_args()
	
	print(f"""Setting up video/audio reader for file {args.VIDEO}...""")
	# open MP4 reader
	readerMp4 = imageio_ffmpeg.read_frames(
		args.VIDEO
	)
	# read first frame = metadata
	# fields:
	#    'ffmpeg_version'   string
	#    'codec'            string
	#    'pix_fmt'          string
	#    'audio_codec'      string
	#    'fps'              float
	#    'source_size'      (int,int)
	#    'size'             (int,int)
	#    'rotate'           int
	#    'duration'         float
	meta = readerMp4.__next__()
	tplSize = meta["size"]
	fltFps = meta["fps"]
	intNumFrames = math.ceil(meta["duration"] * fltFps)
	
	print(f"""
   size:   {'⨯'.join([str(i) for i in tplSize])}
   fps:    {fltFps}
   frames: {intNumFrames}

Parsing overlay file {args.OVERLAY.name} and telemetry file {args.TELEMETRY.name}...""")
	
	# parse overlay definition JSON file
	ovr = Overlay(args.OVERLAY)
	
	# parse telemetry file and process offset arguments
	tele = Telemetry(args.TELEMETRY,fltFps,intNumFrames)
	for strOffset in args.offset:
		try:
			tele.addOffset(strOffset)
		except ValueError as e:
			print(f"ignoring invalid argument '--offset {strOffset}' ({e})",file=sys.stderr)
	
	print(f"""
Setting up video/audio writer for file {args.OUTPUT}...""")
	writerMp4 = imageio_ffmpeg.write_frames(
		args.OUTPUT,
		tplSize,
		macro_block_size=math.gcd(*tplSize), # set macro_block_size to the greatest common divisor of width and height
		fps=fltFps,
		codec=args.vcodec,
		audio_path=args.AUDIO,
		audio_codec=args.acodec,
		input_params=["-thread_queue_size",str(args.tqs)],
		output_params=shlex.split(args.params)
	)
	# seed the writer generator
	writerMp4.send(None)
	
	print(f"""
   audio codec: {args.acodec}
   video codec: {args.vcodec}
   parameters:  {args.params}
	""")
	
	intFrame = 0
	intFramesRemaining = intNumFrames
	t0 = time.time()
	intNumAvg = int(args.tprint*fltFps)
	for frame in readerMp4:
		# get telemetry and cast string values
		# apply overlay to frame and write to output
		try:
			writerMp4.send(
				ovr.apply(
					frame,
					tplSize,
					tele.get(intFrame)
				)
			)
		except KeyboardInterrupt:
			# longest part in loop; make interruptible
			break
		# calculate processing frame rate and remaining time
		intFrame = intFrame + 1
		intFramesRemaining = intFramesRemaining - 1
		if intFrame % intNumAvg == 0:
			t1 = time.time()
			dt = t1 - t0
			t0 = t1
			try:
				fltTimeRemaining = intFramesRemaining*dt/intNumAvg
				strFps = f"{intNumAvg/dt:.2f}"
			except ZeroDivisionError:
				pass
			else:
				if fltTimeRemaining > 3600:
					strRemaining = f"{int(fltTimeRemaining//3600)}:{int(fltTimeRemaining%3600//60):02d} h"
				elif fltTimeRemaining > 60:
					strRemaining = f"{int(fltTimeRemaining//60)}:{int(fltTimeRemaining%60):02d} min"
				else:
					strRemaining = f"{fltTimeRemaining:.2f} sec"
				print(f"processed frame {intFrame}/{intNumFrames} ({strFps} fps, {strRemaining} remaining)                ",end="\r")
	
	print("\nDone")
	writerMp4.close()
