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

STR_VERSION="20230529"

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
import types

# external dependencies
try:
	import imageio_ffmpeg
	import PIL.Image
	import PIL.ImageDraw
	import PIL.ImageFont
except ModuleNotFoundError as e:
	print(e)
	sys.exit(1)


class OverlayCommand:
	"""Base class for all overlay commands.
"""
	DCT_GLOBALS = {}
	STR_CWD = ""
	
	def __init__(self,strCmd,lstArgsAccepted=[]):
		"""Constructor: initialise an OverlayCommand instance.

Args:
   strCmd: a string, the command identifier.
   lstArgsAccepted: an iterable of strings, defining accepted argument names.
"""
		self._strCmd = str(strCmd)
		self._lstArgsAccepted = list(lstArgsAccepted)
		self._dctArgs = { key:None for key in self._lstArgsAccepted }
		self._dctArgsRuntime = { }
	
	def __hash__(self):
		return hash((self._strCmd,tuple(self._dctArgs)))
	
	@classmethod
	def clearGlobals(cls):
		"""Clear the globals class variable, used to define the evaluation environment.
"""
		cls.DCT_GLOBALS = { }
	
	@classmethod
	def setCWD(cls,strFilename):
		"""Set the current working directory to the directory of given filename.

Args:
   strFilename: a string.
"""
		cls.STR_CWD = os.path.dirname(os.path.realpath(os.path.expanduser(strFilename)))
	
	@classmethod
	def addModule(cls,strMod):
		"""Import a module into the command's environment.

Args:
   strMod: a string, the module name

Raises:
   ModuleNotFoundError: given module is not found (batteries not included?).
   ImportError: give module is not a standard module.
"""
		if strMod in sys.stdlib_module_names:
			cls.DCT_GLOBALS[strMod] = importlib.import_module(strMod)
		else:
			raise ImportError("non-standard module '{strMod}'")
	
	@classmethod
	def processFilename(cls,strFilename):
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
			strFilename = os.path.join(cls.STR_CWD,strFilename) # join CWD and relative path
		return os.path.realpath(strFilename) # return canonical path, resolving symlinks
	
	def evaluateArguments(self,dctTelemetry=None):
		"""Evaluate all arguments of this command.

Args:
   dctTelemetry: a dictionary, mapping variable names to values;
                 if not set, NameErrors will silently ignored;

Raises:
   NameError: could not resolve a variable during evaluation.
   Any exception that might occur during expression evaluation.
"""
		for strArg,codeExpression in self._dctArgs.items():
			# iterate over all code expressions and evaluate them
			varExpression = codeExpression
			if isinstance(codeExpression,types.CodeType):
				try:
					varExpression = eval(codeExpression,self.DCT_GLOBALS,dctTelemetry)
				except NameError:
					# only raise NameError if dctTelemetry defined
					# (otherwise it might be due to undefined telemetry setup)
					if dctTelemetry:
						raise
				except Exception as e:
					print(self._strCmd,strArg,self.DCT_GLOBALS,dctTelemetry)
					raise
			if not dctTelemetry:
				# if telemetry data is not present, update argument dictionary 
				self._dctArgs[strArg] = varExpression
			else:
				# if telemetry data is present, update runtime dictionary
				self._dctArgsRuntime[strArg] = varExpression
	
	def setArgument(self,strArg,strExpression):
		"""Compile an expression and set it as argument value.

Args:
   strArg: a string, the argument identifier.
   strExpression: a string, interpreted as Python statement.

Raises:
   TypeError: invalid strExpression type.
   SyntaxError: invalid expression string.
   NameError: argument identifier is not in list of accepted arguments.
"""
		if strArg in self._lstArgsAccepted:
			self._dctArgs[strArg] = compile(strExpression,"<string>","eval")
		else:
			raise NameError
	
	def copyArguments(self,other):
		"""Copy all arguments from another OverlayCommand instance.

Args:
   other: an OverlayCommand or subclass instance.

Raises:
   AttributeError: other is not an OverlayCommand or subclass instance.
"""
		self._dctArgs.update(other._dctArgs)
	
	def applyToFrame(self,imgFrame,drwFrame):
		"""Apply command to given frame.

This is a prototype that does nothing. Subclasses have to re-implement it.

Args:
   imgFrame: a PIL.Image instance.
   drwFrame: a PIL.ImageDraw instance, preferable derived from imgFrame.
"""
		pass
	
	def __str__(self):
		return f"""{self._strCmd} {", ".join([f"{key}={value}" for key,value in self._dctArgs.items()])}"""


class OverlayCommandGenericImage(OverlayCommand):
	"""Class for generic image manipulation in overlays.

This class manages a mapping of filenames to PIL.Image.Image instances
in order to reduce memory usage and image object creation overhead.
"""
	DCT_IMAGES = {}
	
	@classmethod
	def clearImages(cls):
		"""Clear the class variable that maps filenames to PIL.Image instances.
"""
		for key,value in cls.DCT_IMAGES:
			try:
				value.close()
			except:
				pass
		cls.DCT_IMAGES = {}
	
	@classmethod
	def getImage(cls,strFilename,strMode="RGBA"):
		"""Get the PIL.Image instance associated with given filename.

If filename is not yet known, open image file and convert the resulting
PIL.Image.Image instance to given mode.

For valid modes, please refer to:
   https://pillow.readthedocs.io/en/stable/handbook/concepts.html#concept-modes

Args:
   strFilename: a string, the image filename.
   strMode: a string, the desired mode; default: "RGBA".

Returns:
   A PIL.Image.Image instance associated with given filename.

Raises:
   ValueError: failed to load image file.
"""
		strFilename = cls.processFilename(strFilename)
		try:
			imgFilename = cls.DCT_IMAGES[strFilename]
		except KeyError:
			try:
				imgFilename = PIL.Image.open(strFilename).convert(strMode)
			except (ValueError,TypeError,FileNotFoundError,PIL.Image.UnidentifiedImageError,PIL.Image.DecompressionBombWarning,PIL.Image.DecompressionBombError) as e:
				raise ValueError(f"failed to load image file '{strFilename}' ({e})") from e
			else:
				cls.DCT_IMAGES[strFilename] = imgFilename
		return imgFilename


class OverlayCommandImage(OverlayCommandGenericImage):
	"""Class for an image load/modify/paste command.

Shares image database of parent class.
"""
	def __init__(self):
		"""Constructor: initialise instance.
"""
		super().__init__("image",["file","angle","pivot","move","size","alpha","mask"])
	
	def applyToFrame(self,imgFrame,drwFrame):
		"""Apply command to given frame.

This carries out the following operations:

 1) Load image specified by 'file'.
 2) Resize image if 'size' is defined.
 3) Rotate image if 'angle' is defined;
    if 'pivot' is defined, rotate around that point instead of center.
 4) Set image alpha channel to value 'alpha' if defined.
 5) Paste image to imgFrame at position specified in 'move' (default: (0,0)).

Args:
   imgFrame: a PIL.Image instance.
   drwFrame: a PIL.ImageDraw instance, preferable derived from imgFrame.

Raises:
   KeyError: no runtime values (you forgot to call evaluateArguments())
   ValueError: loading image failed.
   Any exceptions PIL might raise in resize(), rotate(), putalpha(), or paste().
"""
		strFilename = self._dctArgsRuntime["file"]
		tplSize     = self._dctArgsRuntime["size"]
		floatAngle  = self._dctArgsRuntime["angle"]
		tplPivot    = self._dctArgsRuntime["pivot"]
		tplMove     = self._dctArgsRuntime["move"]
		intAlpha    = self._dctArgsRuntime["alpha"]
		strMask     = self._dctArgsRuntime["mask"]
		
		imgPaste = self.getImage(strFilename)
		try:
			imgMask = self.getImage(strMask,"LA")
		except (ValueError,TypeError):
			imgMask = None
		
		if tplSize is not None:
			imgPaste = imgPaste.resize(tplSize)
			imgMask = imgMask.resize(tplSize)
		
		if floatAngle is not None and floatAngle != 0:
			imgPaste = imgPaste.rotate(floatAngle,center=tplPivot,translate=tplMove)
			tplMove = None
		
		if intAlpha is not None and intAlpha != 255:
			imgPaste.putalpha(intAlpha)
		
		imgFrame.paste(imgPaste,box=tplMove,mask=imgMask)


class OverlayCommandText(OverlayCommand):
	"""Class for printing text on a frame.

This class manages a mapping of filenames to PIL.ImageFont.ImageFont instances
in order to reduce memory usage and font object creation overhead.

"""
	DCT_FONTS = {}
	
	def __init__(self):
		"""Constructor: initialise instance.
"""
		super().__init__("print",["text","position","anchor","align","font","size","colour","mask"])
	
	@classmethod
	def clearFonts(cls):
		"""Clear the class variable that maps filenames to PIL.ImageFont.ImageFont instances.
"""
		cls.DCT_FONTS = {}
	
	@classmethod
	def getFont(cls,strFilename,intSizePx):
		"""Get the PIL.ImageFont.ImageFont instance associated with given filename and size.

If the combination of (strFilename,intSizePx) is not yet known, load and
memorise truetype font.

Args:
   strFilename: a string, the font filename.
   intSizePx: an integer, pixel size of the font to load.

Returns:
   A PIL.ImageFont.ImageFont instance associated with given filename/size combo.

Raises:
   ValueError: failed to load truetype file.
"""
		strFilename = cls.processFilename(strFilename)
		try:
			fontFilename = cls.DCT_FONTS[(strFilename,intSizePx)]
		except KeyError:
			try:
				fontFilename = PIL.ImageFont.truetype(strFilename,intSizePx)
			except OSError:
				raise ValueError(f"failed to load TTF file '{strFilename}' with size {intSizePx} ({e})")
			else:
				cls.DCT_FONTS[(strFilename,intSizePx)] = fontFilename
		return fontFilename
	
	def applyToFrame(self,imgFrame,drwFrame):
		"""Draw text on given drawing context.

Args:
   imgFrame: a PIL.Image instance.
   drwFrame: a PIL.ImageDraw instance, preferable derived from imgFrame.

Raises:
   KeyError: no runtime values (you forgot to call evaluateArguments())
   ValueError: loading font failed.
   Any exceptions PIL might raise in text().
"""
		drwFrame.text(
			self._dctArgsRuntime["position"],
			self._dctArgsRuntime["text"],
			self._dctArgsRuntime["colour"],
			self.getFont(self._dctArgsRuntime["font"],self._dctArgsRuntime["size"]),
			anchor=self._dctArgsRuntime["anchor"],
			align=self._dctArgsRuntime["align"]
		)


class OverlayCommandMask(OverlayCommandGenericImage):
	"""Class for a mask command.

Shares image database of parent class.
"""
	
	def __init__(self):
		"""Constructor: initialise instance.
"""
		super().__init__("mask",["file"])
	
	def applyToFrame(self,imgFrame,drwFrame):
		"""Apply command to given frame.

This carries out the following operations:

 1) Load mask image and resize to frame size.
 2) Set alpha channel of imgFrame to this mask image.

Args:
   imgFrame: a PIL.Image instance.
   drwFrame: a PIL.ImageDraw instance, preferable derived from imgFrame.

Raises:
   KeyError: no runtime values (you forgot to call evaluateArguments())
   ValueError: loading image failed.
   Any exceptions PIL might raise in resize(), or putalpha().
"""
		imgMask = self.getImage(self._dctArgsRuntime["file"]).resize(imgFrame.size)
		imgFrame.putalpha(imgMask)


class Overlay:
	"""Class for overlay-based video frame processing.

Overlay Definition:

An overlay is a sequence of commands, applied to a video frame. It is defined
either as a JSON list of command lists or as an OVRL text file.
"""
	# regExp groups:
	#  0: optional tab (might be empty)
	#  1: identifier
	#  2: rest of line, starting with first non-whitespace character
	RE_TOKENISER = re.compile(r'''^(\t?)([\w]+)[\s]*(.*)$''',re.M)
	
	def __init__(self,fFileOverlay,strErrLog="last"):
		"""Constructor: initialise an instance.

Args:
   fFileOverlay: a file-like object; JSON or OVRL source of overlay commands.
   strErrLog: a string defining the error logging behaviour; if set to 'last',
              (default), only the most recent error is logged; if set to 'all',
              all errors are logged.
Raises:
   SyntaxError: invalid input format.
"""
		self.clear()
		self._strFilename = fFileOverlay.name
		OverlayCommand.setCWD(self._strFilename)
		self._strErrLog = str(strErrLog)
		try:
			self.loadJSON(fFileOverlay)
		except json.JSONDecodeError:
			self.loadOVRL(fFileOverlay)
	
	def clear(self):
		"""Clear the command list and reset warning variables.
"""
		self._strFilename = ""
		self._intIdxLine = 0
		self._boolIsTainted = False
		self._dctErrors = {}
	
	def warn(self,strMsg):
		"""Issue a warning to sys.stderr.
"""
		print(f"[{self._strFilename}:{self._intIdxLine}] {strMsg}",file=sys.stderr)
		self._boolIsTainted = True
	
	def loadOVRL(self,fOvrl):
		r"""Load a given OVRL overlay command file.

This method will keep parsing the text data but will print warnings.
If there is at least one warning, it raises a SyntaxError.

The OVRL file is line-oriented. Empty lines and lines starting with
'#' (comment) or '\t#' (indented comment) will be ignored.

Each un-indented line is interpreted as a command identifier, optionally
followed by an expression string.

Each tab-indented line is interpreted as an argument identifier, followed by
an expression string. Indented lines define arguments for the most recently
defined command.

Except for the 'uses' command, all expression strings will be compiled and
evaluated, so that every parameter can be tuned by telemetry data at runtime.

Since this empoys 'eval', you are free to shoot your own foot. Be cautious!
Any modules beyond builtins have to be imported explicitly with 'uses'.


Command: module import

   uses mod0 [, mod1, ...]

Request that given modules are loaded into the overlay's runtime scope;
mod0..mod1 specify module name strings.


Command: image pasting

   image
      file  expression_string
      size  expression_2tuple_of_integers
      angle expression_float
      pivot expression_2tuple_of_integers
      move  expression_2tuple_of_integers
      alpha expression_integer
      
Request that the image at given path is alpha-composited onto the frame,
optionally resizing size=(w,h), rotating angle degrees around pivot=(x,y),
moving move=(x,y) and alpha-blending it.


Command: text printing

   print
      text     expression_string
      position expression_2tuple_of_integers
      anchor   expression_string
      align    expression_string
      font     expression_string
      size     expression_integer
      colour   expression_string

Request that text is drawn onto the frame at a position with given
anchor (cf [1]), alignment ("left","center","right"), using given truetype font
file and pixel size, drawing in given colour (cf. [2])

[1] https://pillow.readthedocs.io/en/stable/handbook/text-anchors.html
[2] https://pillow.readthedocs.io/en/stable/reference/ImageColor.html


Args:
   fOvrl: a file-like object.

Raises:
   SyntaxError: invalid file content
"""
		lstCommands = []
		fOvrl.seek(0)
		cmdOverlay = None
		for self._intIdxLine,strLine in enumerate(fOvrl.readlines()):
			strLine = strLine.rstrip()
			if not strLine or strLine.startswith("\t#") or strLine.startswith("#"):
				# empty line or (indented) comment: ignore
				continue
			# token line: apply regExp, get optional leading tab, identifier and remaining expression
			try:
				strTab,strIdentifier,strExpression = self.RE_TOKENISER.match(strLine).groups()
			except AttributeError as e:
				# regExp didn't match: malformed line!
				self.warn("malformed line")
				continue
			
			if not strTab:
				# un-indented line: new command; finalise current command (if given)
				if cmdOverlay is not None:
					lstCommands.append(cmdOverlay)
				match strIdentifier:
					case "uses":
						# declare required python modules
						# syntax: 'uses name[,name,...]
						for strMod in strExpression.split(","):
							try:
								OverlayCommand.addModule(strMod.strip())
							except ImportError as e:
								self.warn(f'module import error ({e})')
					case "image":
						cmdOverlay = OverlayCommandImage()
					case "print":
						cmdOverlay = OverlayCommandText()
					case "mask":
						cmdOverlay = OverlayCommandMask()
					case _:
						self.warn("unkown command '{strIdentifier}'")
				
				# copy arguments from most recent command of same type
				# (define args once, re-use until redefined)
				for cmdOverlayRecent in lstCommands[::-1]:
					if isinstance(cmdOverlayRecent,type(cmdOverlay)):
						cmdOverlay.copyArguments(cmdOverlayRecent)
						break
			else:
				# indented line: new argument, add to current command
				if cmdOverlay is not None:
					try:
						cmdOverlay.setArgument(strIdentifier,strExpression)
					except SyntaxError as e:
						self.warn(f"syntax error in '{strExpression}' ({e})")
					except NameError as e:
						self.warn(f"unknown argument '{strIdentifier}'")
				else:
					self.warn(f"argument '{strIdentifier}' without command")
		
		# all lines processed: if there's an active command, append it
		if cmdOverlay is not None:
			lstCommands.append(cmdOverlay)
		
		if self._boolIsTainted:
			raise SyntaxError("tainted overlay file")
		else:
			for cmdOverlay in lstCommands:
				cmdOverlay.evaluateArguments()
			self._lstSteps = lstCommands
	
	
	def loadJSON(self,fJSON):
		"""Load a given JSON overlay command file.

This method will keep parsing the JSON data but will print warnings.
If there is at least one warning, it raises a SyntaxError.

The JSON data is expected to be a list of list, specifying a sequence of
commands.

Each command is a list with a command identifier, followed by a variable
number of arguments.

Please note: format is frozen in favour of the OVRL format. No new features
(such as 'mask') will be added.

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

Args:
	fJSON: a file-like object.

Raises:
	json.JSONDecodeError, TypeError: invalid JSON input.
	SyntaxError: Invalid input format
"""
		lstCommands = []
		for self._intIdxLine,(strCmd,*lstArgs) in enumerate(json.load(fJSON)):
			match strCmd:
				case "mod":
					# command: announce python module to use
					# todo: load all modules given in args
					# modules are stored in separate dictionary that is passed
					# to exec when it comes to string format evaluation
					for strMod in lstArgs:
						try:
							OverlayCommand.addModule(strMod.strip())
						except ImportError as e:
							self.warn(f'module import error ({e})')
					
				case "img":
					# command: apply image
					cmdOverlay = OverlayCommandImage()
					try:
						cmdOverlay.setArgument("file",f'f"""{lstArgs[0]}"""')
					except SyntaxError as e:
						self.warn(f"syntax error in '{strExpression}' ({e})")
					except NameError as e:
						self.warn(f"unknown argument '{strIdentifier}'")
					lstCommands.append(cmdOverlay)
					
				case "txt":
					# command: draw text
					cmdOverlay = OverlayCommandText()
					for strArg,intIdx in (("anchor",2),("align",3),("font",5),("colour",7)):
						try:
							cmdOverlay.setArgument(strArg,f'"""{lstArgs[intIdx]}"""')
						except SyntaxError as e:
							self.warn(f"syntax error in '{strExpression}' ({e})")
						except NameError as e:
							self.warn(f"unknown argument '{strIdentifier}'")
					try:
						cmdOverlay.setArgument("text",f'f"""{lstArgs[4]}"""')
					except SyntaxError as e:
						self.warn(f"syntax error in '{strExpression}' ({e})")
					except NameError as e:
						self.warn(f"unknown argument '{strIdentifier}'")
					try:
						cmdOverlay.setArgument("size",f"{lstArgs[6]}")
					except SyntaxError as e:
						self.warn(f"syntax error in '{strExpression}' ({e})")
					except NameError as e:
						self.warn(f"unknown argument '{strIdentifier}'")
					try:
						cmdOverlay.setArgument("position",f"{lstArgs[0]},{lstArgs[1]}")
					except SyntaxError as e:
						self.warn(f"syntax error in '{strExpression}' ({e})")
					except NameError as e:
						self.warn(f"unknown argument '{strIdentifier}'")
					lstCommands.append(cmdOverlay)
		
		if self._boolIsTainted:
			raise SyntaxError("tainted overlay file")
		else:
			for cmdOverlay in lstCommands:
				cmdOverlay.evaluateArguments()
			self._lstSteps = lstCommands
	
	
	def logError(self,strOperation,cmdOverlay,dctTelemetry,excError):
		"""Create a new error log entry according to the configured behaviour.

Args:
   strOperation: a string defining the failed operation, like 'apply' or 'eval'.
   cmdOverlay: an OverlayCommand or subclass instance.
   dctTelemetry: a dictionary with the current telemetry state.
   excError: the exception that triggered this method call.
"""
		if self._strErrLog == "all":
			self._dctErrors.setdefault((cmdOverlay,strOperation),[]).append((excError,dctTelemetry))
		else:
			self._dctErrors[(cmdOverlay,strOperation)] = [(excError,dctTelemetry)]
	
	def getErrorLog(self):
		return self._dctErrors
	
	def writeErrorLog(self,strFilename):
		if self._dctErrors:
			with open(strFilename,"w") as f:
				for (cmdOvr,strOp),value in self._dctErrors.items():
					f.write(f"{strOp} {cmdOvr}:\n")
					for excErr,dctTele in value:
						f.write(f"\tError: {excErr!r}\n")
						for key,value in dctTele.items():
							f.write(f"\t{key} = {value!r}\n")
	
	def apply(self,frame,tplSize,dctTelemetry):
		"""Apply all Overlay commands to a given frame of given size.

Overlay commands can access the variables passed by dctTelemetry.

It will carry out the following operations:

 1) Create a transparent image of size tplSize.
 2) Apply the commands in sequence to this base image.
 3) Alpha-composite the imported frame with the modified base image
 4) Export the final image as a bytes instance.

Args:
   frame: a bytes instance; interpreted as PIL.Image.Image instance
	      (mode RGB, size tplSize).
   tplSize: a 2-tuple of integers (width, height) defining the frame size.
   dctTelemetry: a dictionary defining variables for the given frame.

Returns:
   A bytes instance.
"""
		# create new drawing canvas from frame bytes as alpha-channel RGB
		imgBase = PIL.Image.new("RGBA",tplSize,"#00000000")
		drwBase = PIL.ImageDraw.Draw(imgBase)
		# iterate over commands: paint on clear base image
		for cmdOverlay in self._lstSteps:
			try:
				cmdOverlay.evaluateArguments(dctTelemetry)
			except Exception as e:
				self.logError("eval",cmdOverlay,dctTelemetry,e)
			try:
				cmdOverlay.applyToFrame(imgBase,drwBase)
			except Exception as e:
				self.logError("apply",cmdOverlay,dctTelemetry,e)
		
		# in the end: paste imgBase to imgFrame and export to bytes
		return PIL.Image.alpha_composite(
			PIL.Image.frombytes("RGB",tplSize,frame).convert("RGBA"),
			imgBase
		).convert("RGB").tobytes()
	
	def __str__(self):
		return "\n".join([str(cmdOverlay) for cmdOverlay in self._lstSteps])


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
	STR_PARAMS_DEFAULT = "-preset slow -crf 28 -tune film"
	
	parser = argparse.ArgumentParser(description="Add an Overlay to every frame of a given MP4 file.")
	parser.add_argument("--version", action="version", version=STR_VERSION)
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
		help='Additional ffmpeg parameters, e.g. for the video and/or audio codec or to invoke a filter; specified as a command line string fragment; default: "-preset slow -crf 28 -tune film"; the default can be referenced using the variable $DEFAULT',
		default=STR_PARAMS_DEFAULT
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
	parser.add_argument("--duration",
		help="Limit duration of the input video file to DURATION seconds (default: no limit)",
		type=float
	)
	parser.add_argument("--start",
		help="Start encoding at timestamp START, given in seconds (default: 0.0)",
		type=float,
		default=0.0
	)
	parser.add_argument("--errlog",
		help="Define error logging behaviour; "
			"if ERRLOG is 'last' (default), only save the most recent error; "
			"if ERRLOG is 'all', save all errors (warning, might be a multiple of the frame number)",
		default="last"
	)
	parser.add_argument("--errlogfile",
		help="Safe error log as JSON data to given file",
	)
	args = parser.parse_args()
	
	# 20230518: process start and duration args
	#    -> seek input, limit duration
	#    -> switch to aac codec if start and/or duration are given (due to filtering)
	fltStart = max(0,args.start) # limit to positive numbers
	try:
		fltDuration = max(0,args.duration)
	except TypeError:
		fltDuration = -1.0 # signal undefined duration
	lstParamsIn = []
	if fltStart > 0:
		lstParamsIn.extend(["-ss",str(fltStart)])
	if fltDuration > 0:
		lstParamsIn.extend(["-t",str(fltDuration)])
	if lstParamsIn:
		strACodec = "aac"
	else:
		strACodec = args.acodec
	
	print(f"""Setting up video/audio reader for file {args.VIDEO}...""")
	# open MP4 reader
	readerMp4 = imageio_ffmpeg.read_frames(
		args.VIDEO,
		input_params = lstParamsIn
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
   size:     {'⨯'.join([str(i) for i in tplSize])}
   fps:      {fltFps}
   frames:   {intNumFrames}

Parsing overlay file {args.OVERLAY.name}...""")
	
	# parse overlay definition JSON file
	try:
		ovr = Overlay(args.OVERLAY,args.errlog)
	except json.JSONDecodeError as e:
		print(f"""   parsing failed: {e}""")
		sys.exit(1)

	print(f"""Parsing telemetry file {args.TELEMETRY.name}...""")
	# parse telemetry file and process offset arguments
	try:
		tele = Telemetry(args.TELEMETRY,fltFps,intNumFrames)
	except json.JSONDecodeError as e:
		print(f"""   parsing failed: {e}""")
		sys.exit(1)
	
	for strOffset in args.offset:
		try:
			tele.addOffset(strOffset)
		except ValueError as e:
			print(f"ignoring invalid argument '--offset {strOffset}' ({e})",file=sys.stderr)
	
	# 20230518: take duration and start argument into account to calculate frames-to-skip and total number of frames
	# reader has to decode from the start because of audio track
	# writer will skip until fltStart and break loop when reaching intNumFrames
	intFramesSkip = math.ceil(fltStart * fltFps)
	if fltDuration > 0:
		intNumFrames = math.ceil(fltDuration * fltFps)
	else:
		intNumFrames = math.ceil(meta["duration"] * fltFps)
	
	print(f"""
Setting up video/audio writer for file {args.OUTPUT}...""")
	
	# 20230518: deal with $DEFAULT variable in extra parameters
	#    video will start at 0, audio might start at different timestamp due to fltStart
	#    solution: filter audio by trimming and correcting the timestamps
	lstParamsIn = ["-thread_queue_size",str(args.tqs)]
	lstParamsOut = shlex.split(args.params.replace("$DEFAULT",STR_PARAMS_DEFAULT)) + ["-shortest"]
	lstFilter = []
	if fltStart > 0:
		lstFilter.append(f"start={fltStart}")
	if fltDuration > 0:
		lstFilter.append(f"duration={fltDuration}")
	if lstFilter:
		lstParamsOut.extend(["-af",f"atrim={':'.join(lstFilter)},asetpts=PTS-STARTPTS"])
	
	writerMp4 = imageio_ffmpeg.write_frames(
		args.OUTPUT,
		tplSize,
		macro_block_size = math.gcd(*tplSize), # set macro_block_size to the greatest common divisor of width and height
		fps = fltFps,
		codec = args.vcodec,
		audio_path = args.AUDIO,
		audio_codec = strACodec,
		input_params = lstParamsIn,
		output_params = lstParamsOut
	)
	# seed the writer generator
	writerMp4.send(None)
	
	print(f"""
   audio codec: {strACodec}
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
					tele.get(intFrame+intFramesSkip)
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
	
	if args.errlogfile:
		ovr.writeErrorLog(args.errlogfile)
