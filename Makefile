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
NAME_AUDIO_INTERCOM = /path/to/audio/recording/file

# name of the mixed audio file
NAME_AUDIO_MIX = $(PREFIX)_Mix.aac

# name of the raw (compressed, concated) video file
NAME_VIDEO_OUT = $(PREFIX).mp4

# filename of the Overlay file to use
OVERLAY = /path/to/Overlay.json

# pattern of all input files (ie files from the GoPro)
# will be expanded during processing to $(PATTERN).json (telemetry) and $(PATTERN).mp4 (overlay-added video file)
PATTERN_VIDEO_IN = GX*.MP4

# audio mixing parameters:
#AUDIO_OFFSET       = 10.5
#AUDIO_TEMPO        = 5760/5760.35
#AUDIO_VOL_COCKPIT  = 0.1
#AUDIO_VOL_INTERCOM = 2
#AUDIO_DOJOIN       = True

# telemetry processing parameters:
#TELE_OFFSETS = Altitude=5.7912:0-540 Altitude=5.7912:1780-
#TELE_HDOP = 5
#TELE_MIN_SPEED = 1
#TELE_GRAV = "XZY"
#TELE_QUAT = "RXZY"
#TELE_EULER = "ZYX"
#TELE_CAL_GRAV = 0-60
#TELE_NO_TC_MATCH = 1
#TELE_NO_RP_ZERO = 1

# overlay processing parameters:
#TQS = 1024
#TPRINT = 5

#START=1400
#DURATION=10

#ERRLOG = last
#ERRLOGFILE = ${PREFIX}.errlog

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
