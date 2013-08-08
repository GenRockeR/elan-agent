PACKAGE-NAME := light-controller
PACKAGE-DESC := Light Controller main package
PACKAGE-DEPENDS := lc-ids, lc-connection-tracker, bridge-utils

include ../core/packaging.mk

.PHONY: test
test:

.PHONY: install
install: 
	install -d ${DESTDIR}/etc/network
	install -m 644 interfaces ${DESTDIR}/etc/network/
