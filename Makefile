PACKAGE-NAME := lc-connection-tracker
PACKAGE-DESC := Connection Tracker Package

include ../core/packaging.mk

.PHONY: test
test:
	py.test

.PHONY: install
install: origin/*.py trackerd
	install -d ${DESTDIR}/opt/origin/lib/python
	install -t ${DESTDIR}/opt/origin/lib/python origin/*.py
	install -d ${DESTDIR}/opt/origin/sbin
	install -t ${DESTDIR}/opt/origin/sbin trackerd
