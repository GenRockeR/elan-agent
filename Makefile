PACKAGE-NAME := edge-agent
PACKAGE-DESC := Edge Agent main package
PACKAGE-DEPENDS := ea-ids, ea-connection-tracker, bridge-utils, ea-captive-portal

include ../core/packaging.mk

.PHONY: test
test:

.PHONY: install
install: 
	install -d ${DESTDIR}/etc/network
	install -m 644 interfaces ${DESTDIR}/etc/network/
