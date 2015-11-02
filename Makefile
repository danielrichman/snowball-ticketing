#!/usr/bin/make
# -*- makefile -*-

MAKEFILES = $(wildcard */Makefile)
BUILD_DIRS = $(patsubst %/Makefile,%._build_dir,$(MAKEFILES))
CLEAN_DIRS = $(patsubst %/Makefile,%._clean_dir,$(MAKEFILES))

all : $(BUILD_DIRS)
clean : $(CLEAN_DIRS)

$(BUILD_DIRS) :
	make -C $(patsubst %._build_dir,%,$@)

$(CLEAN_DIRS) :
	make -C $(patsubst %._clean_dir,%,$@) clean

.PHONY : clean all $(BUILD_DIRS) $(CLEAN_DIRS)
.DEFAULT_GOAL := all
