# Frank Abelbeck GoPro Telemetry Overlay Toolset: example Makefile
# Copyright (C) 2023 Frank Abelbeck <frank@abelbeck.info>
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <http://www.gnu.org/licenses/>.


# output file names
# might be combined with other custom variables like this prefix
PREFIX = 20230414_DEABC_Start-Ziel

# name of the final overlay-added video file
NAME_VIDEO_OUT_OVERLAY = $(PREFIX)_overlay.mp4

# name of the intercom recording audio file
NAME_AUDIO_INTERCOM = $(PREFIX)_Intercom_HHMMSSZ.wav

# name of the mixed audio file
NAME_AUDIO_MIX = $(PREFIX)_Mix.aac

# name of the raw (compressed, concated) video file
NAME_VIDEO_OUT = $(PREFIX).mp4


# input file names
# pattern of all input files (ie files from the GoPro)
# will be expanded during processing to $(PATTERN).json (telemetry) and $(PATTERN).mp4 (overlay-added video file)
PATTERN_VIDEO_IN = GX*.MP4


# filename of the Overlay file to use
OVERLAY = /path/to/Overlay.json


# audio mixing parameters: OFFSET (+-secs), TEMPO (+-), VOLCOCKPIT (0..), VOLINTERCOM (0..),  DOJOIN (if non-empty, join audio to 3.0 instead of 2.0)
OFFSET      = -1.23
VOLCOCKPIT  = 0.5
VOLINTERCOM = 2
DOJOIN = True

# telemetry processing parameter:
#   SAMPLES: if non-empty, defines the number of samples interpolated from sequence-type telemetry values
#            if undefined, defaults to framerate
#   OFFSETS: space-separated list of values passed via --offset arguments to addOverlay.py; Key=Value:TStart-TEnd[:Method]
#            default: none
#   HDOP: horizontal dilution of precision value used during telemetry conversion
#         default: 10
#   MIN_SPEED: set a minimum GPS speed (m/s) that needs to be reached to calculate true course and rate of descend
#              default: 1
#   INITIAL_ROW: JSON dictionary of initial values used during telemetry conversion
#   TQS: set thread_queue_size for reading frames (default: 1024)
#   TPRINT: set number of seconds between addOverlay.py progress updates
#           default: 5
#SAMPLES = 50
#OFFSETS = Altitude=4.2672:0-790 Altitude=0.9144:2966-
#HDOP = 5
#MIN_SPEED = 1
#INITIAL_ROW = { "Distance": 0.0 }
#TQS = 1024
#TPRINT = 5


# include main makefile
include /path/to/Makefile.mk


# sample of post include rule: speed up parts of a video
# takes NAME_VIDEO_OUT_OVERLAY, applies a complex speed change filter, and
# writes the result to NAME_VIDEO_OUT_OVERLAY with .mp4 replaced by _speedup.mp4
speedup: $(NAME_VIDEO_OUT_OVERLAY)
	@$(FFMPEG) -i "$^" \
		-filter_complex "$(shell $(GEN_FILTER_SPEED) \
			--change 0:727:32 \
			--change 844:2837:64 \
			--change 2873:2951:32 \
			--change 2993::32 \
			"$^")" \
		-c:v libx264 -preset superfast \
		-vsync vfr \
		"$(^:.mp4=_speedup.mp4)"
