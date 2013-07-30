PACKAGE-NAME := light-controller
PACKAGE-DESC := Light COntroller main package

include ../core/packaging.mk

.PHONY: test
test:

.PHONY: install
install: test
