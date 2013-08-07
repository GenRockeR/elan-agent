PACKAGE-NAME := lc-connection-tracker
PACKAGE-DESC := Connection Tracker Package

include ../core/packaging.mk

.PHONY: test
test:
	py.test

.PHONY: install
install: origin/*.py trackerd
	install -d ${DESTDIR}/opt/origin/lib/python/origin
	install -t ${DESTDIR}/opt/origin/lib/python/origin origin/*.py
	rm -f ${DESTDIR}/opt/origin/lib/python/origin/__init__.py
	install -d ${DESTDIR}/opt/origin/sbin
	install -t ${DESTDIR}/opt/origin/sbin trackerd
