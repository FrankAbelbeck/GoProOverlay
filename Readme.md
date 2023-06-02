# Frank Abelbeck GoPro Telemetry Overlay Toolset

Copyright (C) 2023 Frank Abelbeck <frank@abelbeck.info>

Lizenz: GLP 3

## Overview

This toolset features several programs to concat videos, extract audio tracks,
mix audio tracks and apply a user-defined telemetry overlay to a video.
An example workflow is provided as Makefiles.

## External Dependencies

 * **FFmpeg** https://ffmpeg.org/
 * **ExifTool** https://exiftool.org/
 * **GPSBabel** https://www.gpsbabel.org/
 * **imageio-ffmpeg** https://github.com/imageio/imageio-ffmpeg/
 * **PIL** https://python-pillow.org/

## Contents

 * `addOverlay.py` add an overlay image to a video, based on its telemetry data
 * `concatTelemetry.py` concatenate telemetry JSON files
 * `convertTelemetry.py` convert JSON telemetry extracted by ExifTool
 * `genFilterComplexAudioMix.py` generate complex filter expression for audio mixing/merging
 * `genFilterComplexSpeedChange.py` generate complex filter expression for video speed changes
 * `getGPS.py` create GPX file from JSON telemetry
 * `Makefile.mk` pre-defined workflow
 * `Makefile` example Makefile
 * `Overlay.json` example overlay configuration file (JSON format)
 * `Overlay.ovrl` example overlay configuration file (OVRL format)
 * `Overlay.png` example overlay image file
 * `Readme.md` you are reading it atm
 * `COPYING` GPL 3 license text

## Workflow

The workflow I use to process my GoPro flight videos is given in `Makefile.mk`.
It is divided as follows:

 1) Convert GoPro files (usually trunkated every 4 GB) into smaller, easier to handle files, including the telemetry data stream.
 2) Concatenate files to one raw video file.
 3) Mix cockpit audio (recorded via GoPro mic, from concatenated video) and intercom audio (recorded via mic-in-headset as separate file).
 4) Extract telemetry via Exiftool, convert it to a manageable custom JSON format, and extract GPS data as GPX file.
 5) Wrap it up: feed raw video, mixed audio, telemetry data and overlay JSON/OVRL file to `addOverlay.py`, resulting in the final video file.

Best practive to employ this pre-defined workflow:

 1) Create a new directory and place the GoPro video files and the Intercom recording in it.
 2) Create a file `Makefile` in this new directory along the lines of the example Makefile. It needs to include `Makefile.mk`.
 3) Change into this directory and execute `make`, `make video`, and `make overlay`.

## Makefile Variables

### Mandatory Variables

The workflow is controlled by these mandatory variables:

 * **NAME_VIDEO_OUT_OVERLAY** Name of the final overlay-added video file.
 * **NAME_AUDIO_MIX** Name of the mixed audio stream file.
 * **NAME_VIDEO_OUT** Name of the raw (concatenated) video file.
 * **PATTERN_VIDEO_IN** Pattern of all input files (i.e. file from the GoPro, e.g. GX*.MP4)
 * **OVERLAY** Name of the overlay JSON configuration file.

### Optional Variables

The following variables are optional and can be used to tweak the workflow:

 * **NAME_AUDIO_INTERCOM** Name of the intercom recording file. Can be left undefined; in that case the video's audio is used.
 * **OFFSET** Seconds to shift intercom audio relative to cockpit audio (negative value = intercom recording starts earlier than video recording); default = 0.
 * **TEMPO** Speed of the intercom audio relative to cockpit audio; =1 means same speed, >1 means speed up intercom, <1 means slow down intercom; default = 1.
 * **VOLCOCKPIT** Volume of the cockpit sound; =1 means unchanged volume, >1 means louder, <1 means quieter; default = 1.
 * **VOLINTERCOM** Volume of the intercom sound; =1 means unchanged volume, >1 means louder, <1 means quieter; default = 1.
 * **DOJOIN** If defined (e.g. = True), audio mixing is done by joining stereo cockpit sound (front left/right) with mono intercom sound (front center) as 3.0 sound;
   otherwise down-mix to stereo 2.0 sound (default).
 * **NUM_SAMPLES** If defined, gives the number of samples interpolated from sequence-type telemetry values (e.g. accelerometer, gyroscope); default: number of frames per second
 * **INITIAL_ROW** This variable can be used to set initial values for telemetry, so that accumulating values like distance can be initialised. Expects a sequence of values given as a JSON string. Default: none, start at zero.
 * **GPMD_STREAM_IDX** Number of the telemetry data stream; my GoPro HERO9 uses 3 (default).
 * **X264_PARAMS** Additional parameters for the libx264 codec; default: "-preset slow -tune film -crf 28"
 
### Calculated Variables

The following variables are calculated during runtime and are available in the Makefile after including `Makefile.mk`:

 * **$(FFMPEG)** name of the FFmpeg executable
 * **$(EXIFTOOL)** name of the ExifTool executable
 * **$(GPSBABEL)** name of the GPSBabel executable
 * **$(PATH_GOPRO)** path to the included `Makefile.mk`
 * **$(ADD_OVERLAY)** path to `addOverlay.py`
 * **$(CONVERT_TELE)** path to `convertTelemetry.py`
 * **$(GET_GPS)** path to `getGPS.py`
 * **$(GEN_FILTER_AUDIOMIX)** path to `genFilterComplexAudioMix.py`
 * **$(GEN_FILTER_SPEED)** path to `genFilterComplexSpeedChange.py`
 * **$(CONCAT_TELE)** path to `concatTelemetry.py`
 * **$(NEWLINE)** a newline character
 * **$(COMMA)** a comma character 

## Overlay Definition Language: JSON (deprecated)

### Synopsis

An overlay is defined by a list of commands, encoded as a JSON file. Each command is a list of a command string and one or more arguments.

Each input video frame is copied into a current working frame (RGBA) and all commands are applied in given order.

There is an example `Overlay.json` file.

**Please note: Development of this format is suspended in favour of OVRL!**

### Command "mod": Load Python Module

Load python modules needed for text value processing. This is used to create a safe evaluation environment for format strings.

Args: one or more module name strings.

### Command "img": Apply Image

Blend an image to the current working frame.

Args: an image filename string.

### Command "txt": Draw Text

Draw text on the current working frame.

Args: intX, intY, strAnchor, strAlign, strFormat, strTTF, intSizePx, strColor

 * `intX, intY` frame coordinates of the text anchor point
 * `strAnchor` see https://pillow.readthedocs.io/en/stable/handbook/text-anchors.html#text-anchors for details
 * `strAlign` either "left", "center", or "right"
 * `strFormat` a Python format string, evaluated at runtime; see below for available variable names
 * `strTTF` TrueType font name or font file name; the example uses the Topic font, available at https://www.1001fonts.com/topic-font.html
 * `intSizePx` font size, in pixels
 * `strColor` font colour, given as hexadecimal string; see https://pillow.readthedocs.io/en/stable/reference/ImageColor.html for details

## Overlay Definition Language: OVRL

### Synopsis

An overlay is defined by a list of commands. OVRL files encoded them as text lines, with indented lines denoting argument definitions.

The values of all arguments are given as strings which are subsequently compiled and evaluated.
This allows dynamic modification of all commands during runtime. Most noteably you can present text based on telemetry data.
But also dynamic image rotation (gauges) is possible.

For each frame a clean black-transparent canvas image is generated, which is modified by the commands specified in the file.
In the end the frame and the canvas are alpha-composited and fed to the encoder.

There is an example `Overlay.ovrl` file.

### Command "uses": Load Python Modules

Load python modules needed for expression evaluation. This is used to create the expression evaluation environment.

Args: one or more module name identifiers, comma-separated.

### Command "image": Apply an Image

Alpha-composite an image on the current canvas.

Args: file, angle, pivot, move, size, alpha (in parentheses: expected type after expression evaluation)

 * `file` name of the image file (string)
 * `angle` rotation angle in degrees (float); default 0.0
 * `pivot` rotation center point (2-tuple of integers = (x,y)); default None (image center)
 * `move` translate the image after rotation by this value (2-tuple of integers = (dx,dy)); default None
 * `size` resize the image prior to rotation to this value (2-tuple of integers = (tx,ty)); default None
 * `alpha` apply this alpha value to the resized/rotated image prior to pasting on the canvas (integer); default 255

### Command "print": Draw Text

Draw text on the current working frame.

Args: position, anchor, align, text, font, size, colour

 * `position` frame coordinates of the text anchor point (2-tuple of integers = (x,y))
 * `anchor` text anchor (string); see https://pillow.readthedocs.io/en/stable/handbook/text-anchors.html for details
 * `align` text alignment (string); either "left", "center", or "right"
 * `text` text to print (string)
 * `font` TrueType font file name; the example uses the Topic font, available at https://www.1001fonts.com/topic-font.html
 * `size` font size, in pixels
 * `colour` font colour identifier (string|tuple); see https://pillow.readthedocs.io/en/stable/reference/ImageColor.html for valid identifiers

## Available Telemetry Values

The program `convertTelemetry.py` extracts telemetry data from a GoPro MP4 file
and converts it to a JSON file with the following content:

```
{
   "headings": [...],
   "rows": [...],
   "min": [...],
   "max": [...],
}
```

Field `headings` defines the column headings.
During overlay application the values can be retrieved with these variable names.

Field `rows` defines the telemetry data itself, as a list of rows. Each row is a list of values.

Fields `min` and `max` record the minimum and maximum values in this dataset.

For now the following values are extracted (reference: GoPro HERO9). They can be accessed by the given variable names:

 * `Timestamp` timestamp of the row, seconds since start of recording
 * `Duration` duration represented by this row (GoPro HERO9: 1 second)
 * `TimeGPS` timestamp of the row, as measured by GPS, in seconds since 1970-01-01T00:00:00Z
 * `AccelerationX` list of acceleration values, x axis
 * `AccelerationY` list of acceleration values, y axis
 * `AccelerationZ` list of acceleration values, z axis
 * `GyroscopeX` list of gyroscope values, x axis
 * `GyroscopeY` list of gyroscope values, y axis
 * `GyroscopeZ` list of gyroscope values, z axis
 * `Latitude` GPS latitude, float, degrees, N=+, S=-
 * `Longitude` GPS longitude, float, degrees, E=+, W=-
 * `Altitude` GPS altitude, float, metres
 * `HorizontalError` GPS horizontal error, float, metres
 * `Vario` difference to previous altitude value divided by previous duration value (rate of climb)
 * `TrueCourse` true course, calculated from current and previous GPS coordinates, flat earth approximation
 * `GPSSpeed2D` ground speed, measured by GPS
 * `GPSSpeed3D` spatial speed, measured by GPS
 * `Temperature` temperature of the camera, float, degrees Celsius
 * `Distance` distance travelled, float, metres

## Partial Video Speed-Up/Slow-Down

If you want to speed up parts of a video (perhaps long, uneventful phases),
you can use the script `genFilterComplexSpeedChange.py`. It creates a complex
filter expression. The example `Makefile` shows how to use it.

## Changelog

 * **2023-03-20** initial script-based version
 * **2023-04-23** transition from scripts to central Makefile
 * **2023-04-24** initial commit
 * **2023-04-28** added offset calculation (to calibrate e.g. altitude), 
                  GPS precision handling (honour HDOP/Speed), 
                  changed initial/last row representation from list to dict, 
                  added variables to Makefile.mk to allow more tweaking
 * **2023-05-18** addOverlay.py: added start/duration arguments,
                  added $DEFAULT variable for params argument
 * **2023-05-19** added start/duration variables to example Makefile
 * **2023-05-31** fixed base Makefile,
                  added OVRL overlay file format and error logging function,
                  fixed version information
 * **2023-06-02** fixed adelay usage (ms instead of s),
                  added float fraction parsing to audio offset parameter,
                  renamed some Makefile variables (to avoid OFFSET vs OFFSETS)
