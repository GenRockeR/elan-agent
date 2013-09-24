PACKAGE-NAME := ea-connection-tracker
PACKAGE-DESC := Connection Tracker Package
PACKAGE-DEPENDS := ea-core, python-cffi, python-impacket, gcc, libnetfilter-log-dev, libnfnetlink-dev, python-dev


include ../core/packaging.mk

.PHONY: test
test:
	py.test

.PHONY: install
install: origin/*.py connection-trackerd.py dhcp-trackerd.py
	install -d ${DESTDIR}${ORIGIN_PREFIX}/lib/python/origin
	install -m 644 -t ${DESTDIR}${ORIGIN_PREFIX}/lib/python/origin origin/*.py
	rm -f ${DESTDIR}${ORIGIN_PREFIX}/lib/python/origin/__init__.py
	install -d ${DESTDIR}${ORIGIN_PREFIX}/sbin
	install connection-trackerd.py ${DESTDIR}${ORIGIN_PREFIX}/sbin/connection-trackerd
	install dhcp-trackerd.py ${DESTDIR}${ORIGIN_PREFIX}/sbin/dhcp-trackerd
