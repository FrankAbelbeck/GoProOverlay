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
 * **NumPy** https://numpy.org/
 * **SciPy** https://scipy.org/

## Contents

 * `addOverlay.py` add an overlay image to a video, based on its telemetry data
 * `concatTelemetry.py` concatenate telemetry JSON files
 * `convertTelemetry.py` convert JSON telemetry extracted by ExifTool
 * `genFilterComplexAudioMix.py` generate complex filter expression for audio mixing/merging
 * `genFilterComplexSpeedChange.py` generate complex filter expression for video speed changes
 * `getGPS.py` create GPX file from JSON telemetry
 * `Makefile.mk` pre-defined workflow
 * `Makefile` example Makefile
 * `Overlay_HUD_AT01_6.ovrl` example overlay configuration file (OVRL format)
 * `Overlay_HUD_AT01_6_alt.png` HUD overlay: altitude indicator image
 * `Overlay_HUD_AT01_6_fg.png` HUD overlay: foreground image
 * `Overlay_HUD_AT01_6_mask.png` HUD overlay: mask image
 * `Overlay_HUD_AT01_6_speed.png` HUD overlay: speed indicator image
 * `Overlay_HUD_AT01_6.svg` HUD overlay: original Inkscape drawing
 * `Overlay_HUD_AT01_6_tc.png` HUD overlay: true course indicator image
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

 * `NAME_VIDEO_OUT_OVERLAY` Name of the final overlay-added video file.
 * `NAME_AUDIO_MIX` Name of the mixed audio stream file.
 * `NAME_VIDEO_OUT` Name of the raw (concatenated) video file.
 * `PATTERN_VIDEO_IN` Pattern of all input files (i.e. file from the GoPro, e.g. GX*.MP4)
 * `OVERLAY` Name of the overlay JSON configuration file.

### Optional Variables

The following variables are optional and can be used to tweak the workflow:

 * `NAME_AUDIO_INTERCOM` Name of the intercom recording file. Can be left undefined; in that case the video's audio is used.
 * `GPMD_STREAM_IDX` Number of the telemetry data stream; my GoPro HERO9 uses 3 (default).
 * `X264_PARAMS` Additional parameters for the libx264 codec; default: "-preset slow -tune film -crf 28".
 * `ROTATE_180` If defined (e.g. = True), the video is flipped vertically+horizontally, resulting in a rotation of 180°, during encoding.
    Handy if you accidentally deactivated auto-rotation in the cam.
 * `AUDIO_VOL_COCKPIT` Volume of the cockpit sound; =1 means unchanged volume, >1 means louder, <1 means quieter; default = 1.
 * `AUDIO_VOL_INTERCOM` Volume of the intercom sound; =1 means unchanged volume, >1 means louder, <1 means quieter; default = 1.
 * `AUDIO_OFFSET` Seconds to shift intercom audio relative to cockpit audio (negative value = intercom recording starts earlier than video recording); default = 0.
 * `AUDIO_TEMPO` Speed of the intercom audio relative to cockpit audio; =1 means same speed, >1 means speed up intercom, <1 means slow down intercom; default = 1.
 * `AUDIO_DOJOIN` If defined (e.g. = True), audio mixing is done by joining stereo cockpit sound (front left/right) with mono intercom sound (front center) as 3.0 sound.
    Otherwise down-mix to stereo 2.0 sound (default).
 * `TELE_HDOP` Maximum horizontal dilution of precision (HDOP) value for which GPS data is accepted.
    Excellent: 1-2; good: 2-5; moderate: 5-10; fair: 10-20; poor: 20+. Default = 10.
 * `TELE_MIN_SPEED` Minimum GPS speed (3D, metres/second) that has to be reached to do calculations on true course, rate of climb/descend, and GPS pitch. Default = 1.
 * `TELE_GRAV` Mapping of components of the gravity vector; expects a 3-letter string consisting of the characters X, Y, and Z.
    If a letter is lower-case, the axis is inverted. Default = 'XZY'.
 * `TELE_QUAT` Mapping of components of quaternions (camera and image orientation).
    Expects a 4-letter string consisting of the characters R (real component), X, Y, and Z.
    If a letter is lower-case, the axis is inverted. Default = 'RXZY'.
 * `TELE_EULER` Axis sequence used for quaternion-to-euler-angle calculation. 
    Expects a 3-letter string consisting of the characters X, Y, Z. 
    If all letters are lower-case, an extrinsic rotation about the axes of the original coordinate system is applied.
    Otherweise an intrinsic rotation about the axes of the rotating coordinate system is applied. Default = 'ZXY'.
 * `TELE_ORI_OUT` Axis mapping of roll, pitch, and yaw.
    This is applied after getting the Euler angles from the quaternions.
    Expects a 3-letter string consisting of the characters X, Y, and Z.
    If a letter is lower-case, the axis is inverted. Default = 'yxz'.
 * `TELE_CAL_GRAV` Determine the camera's orientation by aligning the gravity vector with the ideal gravity vector (0,0,1)^t.
    Expects a string `T0-T1` with T0 and T1 being float values.
    Calculates the median of all gravity vector samples between timestamp T0 and T1, given in seconds. "
    If T0 is empty, the minimal timestamp is used. If T1 is empty, the maximal timestamp is used. If T1 equals T2, gravity calibration is disabled.
    Default = '-1'.
 * `TELE_NO_TC_MATCH` If defined (e.g. = True), automatic matching of true course and yaw angle is disabled.
 * `TELE_NO_RPY_ZERO` If defined (e.g. = True), automatic zeroing of roll and pitch angles is disabled.
 * `TELE_OFFSETS` Define expected values for defined timeframes in order to calculate and apply the offset.
    Expects a string `Key=Value:T0-T1:Method` with `Key` being a telemetry data identifier string like `Altitude`, and
    `Value` being some value (JSON-parsed). Both `T0` and `T1` refer to timestamps, given in seconds.
    Finally, `Method` specifies the statistic function to use when calculating the central value ('median', 'mean', 'meanGeometric', 'meanHarmonic', 'meanPower'). Default = 'median'.
 * `TQS`  Thread_queue_size for reading frames. Ddefault = 1024.
 * `TPRINT` Number of seconds between addOverlay.py progress updates. Default = 5.
 * `ERRLOG` addOverlay.py error logging behaviour. If = 'last', only save the most recent error. If = 'all', save all errors (warning, might be a multiple of the number of frames). Default = 'last'.
 * `ERRLOGFILE` Define a filename. This will safe the error log as JSON data to this file. Default = no error saving.
 * `START` Start encoding at this timestamp, given in seconds. Default = 0.
 * `DURATION` Limit duration of the input video file to this number of seconds. Default: no limit.

### Calculated Variables

The following variables are calculated during runtime and are available in the Makefile after including `Makefile.mk`:

 * `$(FFMPEG)` name of the FFmpeg executable
 * `$(EXIFTOOL)` name of the ExifTool executable
 * `$(GPSBABEL)` name of the GPSBabel executable
 * `$(PATH_GOPRO)` path to the included `Makefile.mk`
 * `$(ADD_OVERLAY)` path to `addOverlay.py`
 * `$(CONVERT_TELE)` path to `convertTelemetry.py`
 * `$(GET_GPS)` path to `getGPS.py`
 * `$(GEN_FILTER_AUDIOMIX)` path to `genFilterComplexAudioMix.py`
 * `$(GEN_FILTER_SPEED)` path to `genFilterComplexSpeedChange.py`
 * `$(NEWLINE)` a newline character
 * `$(COMMA)` a comma character 

## Overlay Definition Language: OVRL

### Synopsis

An overlay is defined by a list of commands. OVRL files encoded them as text lines, with indented lines denoting argument definitions.

The values of all arguments are given as strings which are subsequently compiled and evaluated.
This allows dynamic modification of all commands during runtime. Most noteably you can present text based on telemetry data.
But also dynamic image rotation (gauges) is possible.

**WARNING**: This employs `eval()`, which is the IT equivalent of opening the gates of hell. You are free to shoot your own foot. Be cautious!

There is an example `Overlay.ovrl` file.

### Command "uses": Load Python Modules

Load python modules needed for expression evaluation. This is used to create the expression evaluation environment.

Args: one or more module name identifiers, comma-separated.

### Command "image": Apply an Image

Alpha-composite an image on the current canvas.

Args: file, angle, pivot, move, size, alpha, mask (in parentheses: expected type after expression evaluation)

 * `file` (string) name of the image file
 * `angle` (float) rotation angle in degrees; default 0.0
 * `pivot` (2-tuple of integers (x,y)) rotation center point; default None (image center)
 * `move` (2-tuple of integers (dx,dy)) translate the image after rotation by this value; default None
 * `size` (2-tuple of integers (w,h)) resize the image prior to rotation to this value; default None
 * `alpha` (integer 0..255) apply this alpha value to the resized/rotated image prior to pasting on the canvas; default 255
 * `mask` (string) name of the mask file, having the same size as the frames

### Command "print": Draw Text

Draw text on the current working frame.

Args: text, position, anchor, align, font, size, fillColour, spacing, strokeWidth, strokeColour, embeddedColor, mask (in parentheses: expected type after expression evaluation)

 * `position` (2-tuple of integers (x,y)) frame coordinates of the text anchor point
 * `anchor` (string) text anchor ; see https://pillow.readthedocs.io/en/stable/handbook/text-anchors.html for details
 * `align` (string) text alignment; either "left", "center", or "right"
 * `text` (string) text to print
 * `font` (string) TrueType font file name; the example uses the Topic font, available at https://www.1001fonts.com/topic-font.html
 * `size` (integer) font size, in pixels
 * `fillColour` (string|tuple) font colour identifier; see https://pillow.readthedocs.io/en/stable/reference/ImageColor.html for valid identifiers
 * `spacing` (integer) number of pixels between lines
 * `strokeWidth` (integer) width of the text stroke
 * `strokeColour` (string|tuple) stroke colour identifier; see https://pillow.readthedocs.io/en/stable/reference/ImageColor.html for valid identifiers
 * `embeddedColor` (boolean) whether to use font embedded colour glyphs
 * `mask` (string) name of the mask file, having the same size as the frames

### Command "arc": Draw Arc

Draw an arc on the current working frame.

Args: origin, radius, start, end, strokeColour, strokeWidth, mask (in parentheses: expected type after expression evaluation)

 * `origin` (2-tuple of integers (x,y)) frame coordinates of the center point
 * `radius` (integer) text anchor ; see https://pillow.readthedocs.io/en/stable/handbook/text-anchors.html for details
 * `start` (float) starting angle in degrees; counter-clockwise, starting a three o'clock
 * `end` (float) ending angle in degrees
 * `strokeColour` (string|tuple) stroke colour identifier; see https://pillow.readthedocs.io/en/stable/reference/ImageColor.html for valid identifiers
 * `strokeWidth` (integer) width of the arc's stroke
 * `mask` (string) name of the mask file, having the same size as the frames
 
### Command "rect": Draw Rectangle

Draw a rectangle on the current working frame.

Args: topLeft, bottomRight, radius, corners, fillColour, strokeColour, strokeWidth, mask (in parentheses: expected type after expression evaluation)

 * `topLeft` (2-tuple of integers (x,y)) frame coordinates of the upper left corner
 * `bottomRight` (2-tuple of integers (x,y)) frame coordinates of the lower right corner
 * `radius` (integer) radius of rounded corners, in pixels; default 0 (no rounded corners)
 * `corners` (4-tuple of booleans) whether to round a corner (topLeft, topRight, bottomRight, bottomLeft)
 * `fillColour` (string|tuple) fill colour identifier; see https://pillow.readthedocs.io/en/stable/reference/ImageColor.html for valid identifiers
 * `strokeColour` (string|tuple) stroke colour identifier; see https://pillow.readthedocs.io/en/stable/reference/ImageColor.html for valid identifiers
 * `strokeWidth` (integer) width of the arc's stroke
 * `mask` (string) name of the mask file, having the same size as the frames
 
### Command "rect": Draw Rectangle

Mask the current frame, i.e. remove areas as defined in the mask image.

Args: mask (in parentheses: expected type after expression evaluation)

 * `mask` (string) name of the mask file, having the same size as the frames;
   the image is converted to a 8-bit greyscale image; mask pixels with value 255
   are erased in the frame; mask pixels with value 0 are kept; values inbetween
   lead to partial erasure.

## Available Telemetry Values

The program `convertTelemetry.py` extracts telemetry data from a GoPro MP4 file
and converts it to a JSON file with the following content:

```
{
   "fieldName": [value0, value1, ... valueN],
   ...
}
```

Each telemetry data field represents a series of values, with a sampling rate
matching the video's framerate.

For now the following values are extracted (reference: GoPro HERO9). They can be accessed by the given variable names:

 * `Acceleration` acceleration vector values (x,y,z) \[m/s²\]
 * `Altitude` GPS altitude values \[m\]
 * `CameraAngle` camera angle values (x=roll,y=pitch,z=yaw) \[radians\]
 * `DistanceStep` distance travelled from last sample \[m\]
 * `GPSAcceleration2D` GPS 2D acceleration, dervied from 2D speed \[m/s²\]
 * `GPSAcceleration3D` GPS 3D acceleration, dervied from 3D speed \[m/s²\]
 * `GPSHorizontalError` GPS horizontal error \[-\]
 * `GPSPitch` GPS pitch angle along TrueCourse \[radians\]
 * `GPSSpeed2D` GPS ground speed \[m/s\]
 * `GPSSpeed3D` GPS spatial speed \[m/s\]
 * `GPSTime` timestamps, as measured by GPS, in seconds since 1970-01-01T00:00:00Z \[s\]
 * `Gravity` gravity vector values (x,y,z), normalised; upright camera will yield ideally (0,0,1) \[-\]
 * `Gyroscope` gyroscope vector values (x,y,z) \[radians/s\]
 * `ImageAngle` camera angle values (x=roll,y=pitch,z=yaw) \[radians\]
 * `Latitude` GPS latitude values, degrees, N=+, S=- \[°\]
 * `Longitude` GPS longitude values, degrees, E=+, W=- \[°\]
 * `Temperature` temperature values of the camera \[°C\]
 * `Timestamp` timestamps, seconds since start of recording \[s\]
 * `TrueCourse` true course, calculated from current and previous GPS coordinates, flat earth approximation \[radians\]
 * `TurnRate` change of true course, derived from TrueCourse variable \[radians/s\]
 * `Vario` change of altitude values, derived from Altitude variable \[m/s\]

You can access these values in your OVRL file using the exact name as given above.

If you want to access all values up until the current frame, put an underscore in front of the variable name.

If you want to access all values after the current frame, append an underscore to the variable name.

For example, you can get the overal distance travelled so far by specifying
```
sum(_DistanceStep)
```

If you want the distance yet to travel until the end of the video, specify
```
sum(DistanceStep_)
```

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
                  added float fraction parsing to audio tempo parameter,
                  renamed some Makefile variables (to avoid OFFSET vs OFFSETS)
 * **2023-06-06** added new values GPSPitch, VelocityX/Y/Z, AngleX/Y/Z,
                  calculated from gyro, accelerometer, and GPS coordinates,
                  fixed handling of accelerometer/gyroscope values (parse InputOrientation data),
                  introduced --calibrate argument for coordinate transformation (camera mount),
                  moved telemetry data mangling to convertTelemetry.py
 * **2023-07-09** rewrote telemetry processing, fine-tuned new overlay language,
                  added scipy/numpy for better quaternion/Euler angle processing,
                  expanded OVRL processing, now includes arcs, masks, and rects,
                  added HUD-style overlay
