#!/usr/bin/make
# -*- makefile -*-

COFFEE = coffee 
# TODO UGLIFY

coffee_files = $(wildcard *.coffee) $(wildcard theme/*.coffee)
javascript_files = $(patsubst %.coffee,../static/coffee/%.js,$(coffee_files))

all : $(javascript_files)

../static/coffee/%.js : %.coffee header.js
	cp header.js $@
	$(COFFEE) --print --compile $< >> $@ || (rm $@; exit 1)

clean : 
	rm -f $(javascript_files)

.PHONY : clean all
.DEFAULT_GOAL := all
