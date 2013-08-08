PACKAGE-NAME := lc-connection-tracker
PACKAGE-DESC := Connection Tracker Package
PACKAGE-DEPENDS := lc-core, python-cffi, python-impacket


include ../core/packaging.mk

.PHONY: test
test:
	py.test

.PHONY: install
install: origin/*.py trackerd
	install -d ${DESTDIR}/opt/origin/lib/python/origin
	install -m 644 -t ${DESTDIR}/opt/origin/lib/python/origin origin/*.py
	rm -f ${DESTDIR}/opt/origin/lib/python/origin/__init__.py
	install -d ${DESTDIR}/opt/origin/sbin
	install trackerd ${DESTDIR}/opt/origin/sbin/connection-trackerd
