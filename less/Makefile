#!/usr/bin/make
# -*- makefile -*-

BOOTSTRAP_INCLUDE = ../lib/bootstrap/less
css_depends = $(wildcard $(BOOTSTRAP_INCLUDE)/*.less) \
			  $(wildcard *.less) \
			  $(wildcard theme/*.less) \
			  $(wildcard theme/pages/*.less)

LESSC = lessc --include-path=$(BOOTSTRAP_INCLUDE)

snowball.css : $(css_depends)
	$(LESSC) --compile main.less > $@

test : $(css_depends)
	$(LESSC) main.less

clean : 
	rm -f snowball.css

.PHONY : clean test
.DEFAULT_GOAL := snowball.css
