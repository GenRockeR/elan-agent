PACKAGE-NAME := light-controller
PACKAGE-DESC := Light Controller main package

include ../core/packaging.mk

.PHONY: test
test:

.PHONY: install
install: test
