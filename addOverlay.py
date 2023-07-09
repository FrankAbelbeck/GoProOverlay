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

STR_VERSION="20230709"

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
	DCT_IMAGES = {}
	DCT_FONTS = {}
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
	def clearFonts(cls):
		"""Clear the class variable that maps filenames to PIL.ImageFont.ImageFont instances.
"""
		cls.DCT_FONTS = {}
	
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
				imgFilename = PIL.Image.open(strFilename)
			except (ValueError,TypeError,FileNotFoundError,PIL.Image.UnidentifiedImageError,PIL.Image.DecompressionBombWarning,PIL.Image.DecompressionBombError) as e:
				raise ValueError(f"failed to load image file '{strFilename}' ({e})") from e
			else:
				cls.DCT_IMAGES[strFilename] = imgFilename
		return imgFilename.convert(strMode)
	
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
			raise ImportError(f"non-standard module '{strMod}'")
	
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
   drwFrame: a PIL.ImageDraw instance, preferably derived from imgFrame.
"""
		pass
	
	def __str__(self):
		return f"""{self._strCmd} {", ".join([f"{key}={value}" for key,value in self._dctArgsRuntime.items()])}"""


class OverlayCommandImage(OverlayCommand):
	"""Class for an image load/modify/paste command.

Shares image database of parent class.
"""
	def __init__(self):
		"""Constructor: initialise instance.
"""
		super().__init__("image",["file","angle","pivot","move","size","alpha","mask","resample"])
	
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
   drwFrame: a PIL.ImageDraw instance, preferably derived from imgFrame.

Raises:
   KeyError: no runtime values (you forgot to call evaluateArguments())
   ValueError: loading image failed.
   Any exceptions PIL might raise in resize(), rotate(), putalpha(), or paste().
"""
		strFilename = self._dctArgsRuntime["file"]
		tplSize     = self._dctArgsRuntime["size"]
		fltAngle    = self._dctArgsRuntime["angle"]
		tplPivot    = self._dctArgsRuntime["pivot"]
		tplMove     = self._dctArgsRuntime["move"]
		intAlpha    = self._dctArgsRuntime["alpha"]
		strMask     = self._dctArgsRuntime["mask"]
		strResample = self._dctArgsRuntime["resample"]
		
		match strResample:
			case "nearest":
				resampling = PIL.Image.Resampling.NEAREST
			case "bicubic":
				resampling = PIL.Image.Resampling.BICUBIC
			case _:
				resampling = PIL.Image.Resampling.BILINEAR
		
		imgPaste = self.getImage(strFilename)
		if strMask is not None:
			try:
				imgMask = self.getImage(strMask,"L")
			except (ValueError,TypeError):
				imgMask = None
		else:
			imgMask = None
		
		if tplSize is not None:
			imgPaste = imgPaste.resize(tplSize,resample=resampling)
		
		if fltAngle is not None and fltAngle != 0:
			imgPaste = imgPaste.rotate(fltAngle,center=tplPivot,resample=resampling)
		
		if tplMove is None:
			tplMove = (0,0)
		
		if intAlpha is not None and intAlpha != 255:
			imgPaste = PIL.Image.blend(
				PIL.Image.new("RGBA",imgPaste.size,"#00000000"),
				imgPaste,
				intAlpha
			)
		
		if imgMask is not None:
			imgTmp1 = PIL.Image.new("RGBA",imgFrame.size,"#00000000")
			imgTmp2 = imgTmp1.copy()
			imgTmp2.paste(imgPaste,tplMove)
			imgPaste = PIL.Image.composite(imgTmp1,imgTmp2,imgMask)
			tplMove = (0,0)
		
		imgFrame.alpha_composite(imgPaste,dest=tplMove)


class OverlayCommandDraw(OverlayCommand):
	"""Generic class for drawing on a frame.

This class manages mask application for drawing commands.
"""
	def __init__(self,strCmd=None,lstArgs=None):
		"""Constructor: initialise instance.
"""
		if strCmd is None:
			strCmd = "draw"
		if lstArgs is None:
			lstArgs = ["mask"]
		elif "mask" not in lstArgs:
			lstArgs.append("mask")
		super().__init__(strCmd,lstArgs)
	
	def draw(self,imgFrame,drwFrame):
		"""Do something with the given drawing context and/or image.

This is a prototype for drawing doing nothing. You have to subclass
and re-define this method.

Args:
   imgFrame: a PIL.Image instance.
   drwFrame: a PIL.ImageDraw instance, preferably derived from imgFrame.
"""
		pass
	
	def applyToFrame(self,imgFrame,drwFrame):
		"""Draw something (to be defined in method 'draw()' on given drawing context.

Args:
   imgFrame: a PIL.Image instance.
   drwFrame: a PIL.ImageDraw instance, preferably derived from imgFrame.

Raises:
   KeyError: no runtime values (you forgot to call evaluateArguments())
   Any exceptions PIL draw() might raise.
"""
		imgMask = self._dctArgsRuntime["mask"]
		if imgMask is not None:
			try:
				imgMask = self.getImage(imgMask).resize(imgFrame.size)
			except (ValueError,TypeError):
				imgMask = None
		
		if imgMask is None:
			self.draw(imgFrame,drwFrame)
		else:
			imgTmp1 = PIL.Image.new("RGBA",imgFrame.size,"#00000000")
			imgTmp2 = imgTmp1.copy()
			drwTmp = PIL.ImageDraw.Draw(imgTmp)
			self.draw(imgTmp.drwTmp)
			imgTmp1 = PIL.Image.composite(imgTmp2,imgTmp1,imgMask)
			imgFrame.alpha_composite(imgTmp)


class OverlayCommandText(OverlayCommandDraw):
	"""Class for printing text on a frame.

This class manages a mapping of filenames to PIL.ImageFont.ImageFont instances
in order to reduce memory usage and font object creation overhead.

"""
	def __init__(self):
		"""Constructor: initialise instance.
"""
		super().__init__("print",["text","position","anchor","align","font","size","fillColour","spacing","strokeWidth","strokeColour","embeddedColor","mask"])
	
	def draw(self,imgFrame,drwFrame):
		"""Draw text on given drawing context.

Args:
   imgFrame: a PIL.Image instance.
   drwFrame: a PIL.ImageDraw instance, preferably derived from imgFrame.

Raises:
   KeyError: no runtime values (you forgot to call evaluateArguments())
   ValueError: loading font failed.
   Any exceptions PIL might raise in text().
"""
		intSpacing = self._dctArgsRuntime["spacing"]
		if not isinstance(intSpacing,int):
			intSpacing = 4
		
		intStrokeWidth = self._dctArgsRuntime["strokeWidth"]
		if not isinstance(intSpacing,int):
			intStrokeWidth = 0
		
		varColour = self._dctArgsRuntime["fillColour"]
		varStrokeFill = self._dctArgsRuntime["strokeColour"]
		if varStrokeFill is None:
			varStrokeFill = varColour
			intStrokeWidth = 0
		
		boolEmbeddedColour = self._dctArgsRuntime["embeddedColor"]
		if not isinstance(boolEmbeddedColour,bool):
			boolEmbeddedColour = False
		
		drwFrame.text(
			xy             = self._dctArgsRuntime["position"],
			text           = self._dctArgsRuntime["text"],
			fill           = varColour,
			font           = self.getFont(self._dctArgsRuntime["font"],self._dctArgsRuntime["size"]),
			anchor         = self._dctArgsRuntime["anchor"],
			align          = self._dctArgsRuntime["align"],
			spacing        = intSpacing,
			stroke_width   = intStrokeWidth,
			stroke_fill    = varStrokeFill,
			embedded_color = boolEmbeddedColour
		)


class OverlayCommandArc(OverlayCommandDraw):
	"""Class for drawing an arc on a frame.

This class manages a mapping of filenames to PIL.ImageFont.ImageFont instances
in order to reduce memory usage and font object creation overhead.

"""
	
	def __init__(self):
		"""Constructor: initialise instance.
"""
		super().__init__("arc",["origin","radius","start","end","strokeColour","strokeWidth","mask"])
	
	def draw(self,imgFrame,drwFrame):
		"""Draw an arc on given drawing context.

Args:
   imgFrame: a PIL.Image instance.
   drwFrame: a PIL.ImageDraw instance, preferably derived from imgFrame.

Raises:
   KeyError: no runtime values (you forgot to call evaluateArguments())
   ValueError: loading font failed.
   Any exceptions PIL might raise in text().
"""
		# tplBBox = (left,upper,right,down) calc from origin and radius
		x,y = self._dctArgsRuntime["origin"]
		r = self._dctArgsRuntime["radius"]
		drwFrame.arc(
			xy    = (x-r, y-r, x+r, y+r),
			start = self._dctArgsRuntime["start"],
			end   = self._dctArgsRuntime["end"],
			fill  = self._dctArgsRuntime["strokeColour"],
			width = self._dctArgsRuntime["strokeWidth"]
		)


class OverlayCommandRect(OverlayCommandDraw):
	"""Class for drawing an arc on a frame.

This class manages a mapping of filenames to PIL.ImageFont.ImageFont instances
in order to reduce memory usage and font object creation overhead.

"""
	
	def __init__(self):
		"""Constructor: initialise instance.
"""
		super().__init__("rect",["topLeft","bottomRight","radius","corners","fillColour","strokeColour", "strokeWidth","mask"])
	
	def draw(self,imgFrame,drwFrame):
		"""Draw a rectangle on given drawing context.

Args:
   imgFrame: a PIL.Image instance.
   drwFrame: a PIL.ImageDraw instance, preferably derived from imgFrame.

Raises:
   KeyError: no runtime values (you forgot to call evaluateArguments())
   ValueError: loading font failed.
   Any exceptions PIL might raise in text().
"""
		# tplBBox = (left,upper,right,down) calc from origin and radius
		x0,y0 = self._dctArgsRuntime["topLeft"]
		x1,y1 = self._dctArgsRuntime["bottomRight"]
		r = self._dctArgsRuntime["radius"]
		if r is None:
			r = 0
		try:
			cTopLeft,cTopRight,cBottomRight,cBottomLeft = self._dctArgsRuntime["corners"]
			corners = (cTopLeft,cTopRight,cBottomRight,cBottomLeft)
		except:
			corners = None
		drwFrame.rounded_rectangle(
			xy      = (x0,y0,x1,y1),
			radius  = r,
			corners = corners,
			fill    = self._dctArgsRuntime["fillColour"],
			outline = self._dctArgsRuntime["strokeColour"],
			width   = self._dctArgsRuntime["strokeWidth"]
		)


class OverlayCommandMask(OverlayCommand):
	"""Class for a mask command.

Shares image database of parent class.
"""
	
	def __init__(self):
		"""Constructor: initialise instance.
"""
		super().__init__("mask",["file"])
	
	def applyToFrame(self,imgFrame,drwFrame):
		"""Apply command to given frame.

Paste a black transparent frame to the current frame, using the given mask.

This will erase all areas that are set to 255 in the (grayscale) mask image,
and will keep all areas that are set to 0 in the mask. Intermediate mask values
will result in partially erased pixels.

Args:
   imgFrame: a PIL.Image instance.
   drwFrame: a PIL.ImageDraw instance, preferably derived from imgFrame.

Raises:
   KeyError: no runtime values (you forgot to call evaluateArguments())
   ValueError, TypeError: loading image failed.
   Any exceptions PIL might raise in resize(), or putalpha().
"""
		imgFrame.paste(
			PIL.Image.new("RGBA",imgFrame.size,"#00000000"),
			self.getImage(self._dctArgsRuntime["file"],"L").resize(imgFrame.size)
		)


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
	DCT_COMMANDS = {
		"image" : OverlayCommandImage,
		"print" : OverlayCommandText,
		"mask"  : OverlayCommandMask,
		"arc"   : OverlayCommandArc,
		"rect"  : OverlayCommandRect
	}
	
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

Since this employs 'eval', you are free to shoot your own foot. Be cautious!
Any modules beyond builtins have to be imported explicitly with 'uses'.

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
				if strIdentifier == "uses":
					# declare required python modules
					# syntax: 'uses name[,name,...]
					for strMod in strExpression.split(","):
						try:
							OverlayCommand.addModule(strMod.strip())
						except ImportError as e:
							self.warn(f'module import error ({e})')
				else:
					try:
						cmdOverlay = self.DCT_COMMANDS[strIdentifier]()
					except KeyError:
						cmdOverlay = None
						self.warn(f"unkown command '{strIdentifier}'")
				
#				# copy arguments from most recent command of same type
#				# (define args once, re-use until redefined)
#				for cmdOverlayRecent in lstCommands[::-1]:
#					if isinstance(cmdOverlayRecent,type(cmdOverlay)):
#						cmdOverlay.copyArguments(cmdOverlayRecent)
#						break
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
			self._dctErrors.setdefault((cmdOverlay,strOperation),[]).append(excError)
		else:
			self._dctErrors[(cmdOverlay,strOperation)] = [excError]
	
	def getErrorLog(self):
		return self._dctErrors
	
	def writeErrorLog(self,strFilename):
		if self._dctErrors:
			with open(strFilename,"w") as f:
				for (cmdOvr,strOp),value in self._dctErrors.items():
					f.write(f"{strOp} {cmdOvr}:\n")
					for excErr in value:
						f.write(f"\tError: {excErr!r}\n")
	
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
	"key": [value0, ..., valueN],
	...
}
"""
	
	def __init__(self, fJSON, fltFps, intNumFrames):
		"""Constructor: initialise instance.

Args:
   fJSON: a file-like object; telemetry data in JSON format.

Raises:
   TypeError, ValueError: invalid framerate.
   json.JSONDecodeError: invalid JSON input.
"""
		self._fltFps = fltFps
		self._intNumFrames = intNumFrames
		self._dctTele = {}
		self.load(fJSON)
	
	def load(self, fJSON):
		"""Load telemetry data from given JSON file.

Assumptions:
	1) data is given as a dictionary
	2) each dictionary key is a data name string
	3) each dictionary entry is a list of values
	4) all value lists have the same length (=framerate*duration=frame number)

Args:
   fJSON: a file-like object.

Raises:
   KeyError,TypeError: invalid JSON data.
   json.JSONDecodeError: invalid JSON input.
"""
		# load JSON data
		self._dctTele = json.load(fJSON)
	
	def get(self,intIdxFrame):
		"""Get telemetry data of the current frame and advance the internal pointers.

Returns:
   A dictionary, mapping all field names (as given in 'headings' to values).
"""
		dctReturn = {}
		try:
			for strKey,lstData in self._dctTele.items():
				dctReturn[strKey] = lstData[intIdxFrame]
				dctReturn["_"+strKey] = lstData[:intIdxFrame]
				dctReturn[strKey+"_"] = lstData[intIdxFrame+1:]
		except IndexError:
			pass
		else:
			dctReturn["Framerate"] = self._fltFps
			dctReturn["FrameIndex"] = intIdxFrame
			dctReturn["NumberFrames"] = self._intNumFrames
		return dctReturn


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
	except SyntaxError as e:
		print(f"""   parsing failed: {e}""")
		sys.exit(1)

	print(f"""Parsing telemetry file {args.TELEMETRY.name}...""")
	# parse telemetry file and process offset arguments
	try:
		tele = Telemetry(args.TELEMETRY,fltFps,intNumFrames)
	except json.JSONDecodeError as e:
		print(f"""   parsing failed: {e}""")
		sys.exit(1)
	
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
