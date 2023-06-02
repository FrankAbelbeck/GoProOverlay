# Frank Abelbeck GoPro Telemetry Overlay Toolset: basic Makefile
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

#-------------------------------------------------------------------------------
# This makefile assumes that it was included after the following variables
# were defined: PREFIX, PATTERN, OVERLAY, OFFSET, TEMPO, VOLCOCKPIT, VOLINTERCOM
#
# In order to use it, create your own Makefile (preferably in the directory of
# your video files), and define these variables. As minimum requirement,
# PREFIX, PATTERN, and OVERLAY have to be defined.
#
# Right after these definitions, state the following line:
#
#    include /path/to/this/Makefile.mk
#
#-------------------------------------------------------------------------------
#
# Configuration: get this makefile's directory, define executable paths,
#                get first file in input video file pattern
#
FFMPEG              = ffmpeg
EXIFTOOL            = exiftool
GPSBABEL            = gpsbabel
PATH_GOPRO          = $(dir $(realpath $(lastword $(MAKEFILE_LIST))))
ADD_OVERLAY         = $(PATH_GOPRO)/addOverlay.py
CONVERT_TELE        = $(PATH_GOPRO)/convertTelemetry.py
GET_GPS             = $(PATH_GOPRO)/getGPS.py
GEN_FILTER_AUDIOMIX = $(PATH_GOPRO)/genFilterComplexAudioMix.py
GEN_FILTER_SPEED    = $(PATH_GOPRO)/genFilterComplexSpeedChange.py
CONCAT_TELE         = $(PATH_GOPRO)/concatTelemetry.py

#
# custom function: copy tags from FIRSTINPUT to filename given as first argument
#
define copyTags
	@$(EXIFTOOL) -overwrite_original -api largefilesupport=1 \
		-TagsFromFile $(1) \
		-CreateDate -Camera:All -Location:All \
		$(2)
endef

define NEWLINE


endef
COMMA = ,

funPrintError = $(info $(shell echo -e "\033[1;31mERROR:\033[0m $(1)"))
funPrintHint = $(info $(shell echo -e "\033[1;33mHINT:\033[0m $(1)"))

funCheckVariable = $(if $(1),,$(call funPrintError,variable \033[1m$(1)\033[0m not defined))
funCheckInternal = $(if $(1),$(call funPrintError,own script \033[1m$(1)\033[0m not found or it is malfunctioning))
funCheckExternal = $(if $(1),$(call funPrintError,program \033[1m$(1)\033[0m not found))

#
# check external requirements
#
MISSING += $(call funCheckExternal,$(shell $(FFMPEG) -version >/dev/null 2>&1 || echo FFmpeg))
MISSING += $(call funCheckExternal,$(shell $(EXIFTOOL) -ver >/dev/null 2>&1 || echo ExifTool))
MISSING += $(call funCheckExternal,$(shell $(GPSBABEL) -V >/dev/null 2>&1 || echo GPSBabel))
#
# check internal requirements (all scripts available, variables defined?)
#
MISSING += $(call funCheckVariable,NAME_VIDEO_OUT)
MISSING += $(call funCheckVariable,NAME_VIDEO_OUT_OVERLAY)
MISSING += $(call funCheckVariable,NAME_AUDIO_MIX)
MISSING += $(call funCheckVariable,PATTERN_VIDEO_IN)
MISSING += $(call funCheckVariable,OVERLAY)

MISSING += $(call funCheckInternal,$(shell $(ADD_OVERLAY) --version >/dev/null 2>&1 || echo "1",addOverlay.py))
MISSING += $(call funCheckInternal,$(shell $(CONVERT_TELE) --version >/dev/null 2>&1 || echo "1",convertTelemetry.py))
MISSING += $(call funCheckInternal,$(shell $(GET_GPS) --version >/dev/null 2>&1 || echo "1",getGPS.py))
MISSING += $(call funCheckInternal,$(shell $(GEN_FILTER_AUDIOMIX) --version >/dev/null 2>&1 || echo "1",generateFilterExpression.py))
MISSING += $(call funCheckInternal,$(shell $(GEN_FILTER_SPEED) --version >/dev/null 2>&1 || echo "1",generateFilterExpression.py))
MISSING += $(call funCheckInternal,$(shell $(CONCAT_TELE) --version >/dev/null 2>&1 || echo "1",concatTelemetry.py))

ifneq ($(strip $(MISSING)),)
$(error program not properly set up)
endif

ifndef GPMD_STREAM_IDX
GPMD_STREAM_IDX = 3
endif

ifndef X264_PARAMS
X264_PARAMS = -preset slow -tune film -crf 28
endif

PATTERN_IN_IMPLICIT = $(subst *,%,$(PATTERN_VIDEO_IN))
FILES_RECODED = $(foreach FILE,$(wildcard $(PATTERN_VIDEO_IN)),$(FILE).mp4)

.PHONY: audio video overlay

audio: $(NAME_AUDIO_MIX)
video: $(NAME_VIDEO_OUT) $(NAME_VIDEO_OUT).json $(NAME_VIDEO_OUT).gpx
overlay: $(NAME_VIDEO_OUT_OVERLAY) video

#
# rule: convert raw footage chunk to x264 reduced-size file, copy audio and gpmd data
#
$(PATTERN_IN_IMPLICIT).mp4: $(PATTERN_IN_IMPLICIT)
	@echo "transcoding video $^ to $@"
	@$(FFMPEG) -y \
		-i "$<" \
		-map_metadata 0 \
		-map 0:v -map 0:a -map 0:$(GPMD_STREAM_IDX) \
		-c:v libx264 $(X264_PARAMS) \
		-c:a copy \
		-c:d copy -copy_unknown \
		"$@"
	$(call copyTags,$<,$@)

#
# rule: create list of converted video chunks
#
$(NAME_VIDEO_OUT).files: $(FILES_RECODED)
	@echo "creating concatenation file list - $^"
	@$(foreach FILE,$^,echo "file $(PWD)/$(FILE)" >> "$(NAME_VIDEO_OUT).files";)

#
# rule: create output video by concatenating converted video chunks and adding mixed cockpit/intercom audio
#
$(NAME_VIDEO_OUT): $(FILES_RECODED) $(NAME_VIDEO_OUT).files
	@echo "concatenating video $@"
	@$(FFMPEG) -y \
		-f concat \
		-safe 0 -i "$(NAME_VIDEO_OUT).files" \
		-map_metadata 0 \
		-map 0:v -map 0:a -map 0:d \
		-c:v copy \
		-c:a copy \
		-c:d copy -copy_unknown \
		"$(NAME_VIDEO_OUT)"
	$(call copyTags,$<,$(NAME_VIDEO_OUT))

#
# rule: extract and convert telemetry of concatenated output video
#
$(NAME_VIDEO_OUT).json: $(NAME_VIDEO_OUT)
	@echo "converting telemetry data of $^"
	@$(EXIFTOOL) -n -b -ee -G3 -json -api largefilesupport=1 "$(NAME_VIDEO_OUT)" | \
	$(CONVERT_TELE) \
		$(if $(TELE_SAMPLES),--samples "$(TELE_SAMPLES)") \
		$(if $(TELE_INITIAL_ROW),--init "$(TELE_INITIAL_ROW)") \
		$(if $(TELE_HDOP),--hdop $(TELE_HDOP) ) \
		$(if $(TELE_MIN_SPEED),--minspeed $(TELE_MIN_SPEED) ) \
		"$(NAME_VIDEO_OUT).json"

#
# rule: create GPX file from concatenated JSON telemetry data
#
$(NAME_VIDEO_OUT).gpx: $(NAME_VIDEO_OUT).json
	@echo "creating GPX file $@"
	@$(GET_GPS) $(NAME_VIDEO_OUT).json | $(GPSBABEL) -t -i unicsv -f - -o gpx -F $(NAME_VIDEO_OUT).gpx

#
# rule: create video overlayed with telemetry data
#
$(NAME_VIDEO_OUT_OVERLAY): $(NAME_VIDEO_OUT) $(NAME_VIDEO_OUT).json $(NAME_AUDIO_MIX) $(OVERLAY)
	@echo "creating overlay video"
	@$(ADD_OVERLAY) --vcodec libx264 --acodec copy --params "$(X264_PARAMS)" \
		$(foreach STR_OFFSET,$(OFFSETS),--offset $(STR_OFFSET) ) \
		$(if $(TQS),--tqs $(TQS) ) \
		$(if $(TQS),--tprint $(TPRINT) ) \
		$(if $(START),--start $(START) ) \
		$(if $(DURATION),--duration $(DURATION) ) \
		$(if $(ERRLOG),--errlog $(ERRLOG) ) \
		$(if $(ERRLOGFILE),--errlogfile $(ERRLOGFILE) ) \
		$(NAME_VIDEO_OUT) \
		$(NAME_AUDIO_MIX) \
		$(OVERLAY) \
		$(NAME_VIDEO_OUT).json \
		$(NAME_VIDEO_OUT_OVERLAY)
	$(call copyTags,$(NAME_VIDEO_OUT),$(NAME_VIDEO_OUT_OVERLAY))

#
# rule: mix audio track (Cockpit) and external recording (Intercom)
#
$(NAME_AUDIO_MIX): $(NAME_VIDEO_OUT) $(NAME_AUDIO_INTERCOM)
ifndef NAME_AUDIO_INTERCOM
	@echo "no intercom recording file defined, just extracting audio track"
	@$(FFMPEG) -y \
		-i $(NAME_VIDEO_OUT) \
		-map 0:a \
		-c:a copy \
		$(NAME_AUDIO_MIX)
else
	@echo "$(if $(AUDIO_DOJOIN),joining,mixing) audio tracks"
	@$(FFMPEG) -y \
		-i $(NAME_VIDEO_OUT) \
		-i $(NAME_AUDIO_INTERCOM) \
		-shortest \
		-filter_complex "$(shell $(GEN_FILTER_AUDIOMIX) \
			$(if $(AUDIO_VOL_COCKPIT),--volcockpit $(AUDIO_VOL_COCKPIT)) \
			$(if $(AUDIO_VOL_INTERCOM),--volintercom $(AUDIO_VOL_INTERCOM)) \
			$(if $(AUDIO_OFFSET),--offset $(AUDIO_OFFSET)) \
			$(if $(AUDIO_TEMPO),--tempo $(AUDIO_TEMPO)) \
			$(if $(AUDIO_DOJOIN),--dojoin))" \
		-map "[audio_muxed]" \
		$(NAME_AUDIO_MIX)
endif
