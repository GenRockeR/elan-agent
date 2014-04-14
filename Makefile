PACKAGE-NAME := ea-network
PACKAGE-DESC := Edge Agent Network module
PACKAGE-DEPENDS := bridge-utils

include ../core/packaging.mk

.PHONY: test
test:
	py.test

.PHONY: install
install: *.py
	install -d ${DESTDIR}/etc/network
	install -m 644 interfaces ${DESTDIR}/etc/network/

