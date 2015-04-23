PACKAGE-NAME := ea-connection-tracker
PACKAGE-DESC := Connection Tracker Package
PACKAGE-DEPENDS := ea-core, python-cffi, python-impacket, gcc, libnetfilter-log-dev, libnfnetlink-dev, python-dev, python-libpcap, python3-cffi, libglib2.0-dev, python3-dev, libwireshark-dev, libwiretap-dev


include ../core/packaging.mk

.PHONY: test
test:
	#py.test

.PHONY: install
install: origin/*.py bin/connection_trackerd.py bin/device_trackerd.py bin/session_trackerd.py wirepy
	install -d ${DESTDIR}${ORIGIN_PREFIX}/lib/python/origin
	install -m 644 -t ${DESTDIR}${ORIGIN_PREFIX}/lib/python/origin origin/*.py
	rm -f ${DESTDIR}${ORIGIN_PREFIX}/lib/python/origin/__init__.py
	install -d ${DESTDIR}${ORIGIN_PREFIX}/bin
	install bin/connection_trackerd.py ${DESTDIR}${ORIGIN_PREFIX}/bin/connection-trackerd
	install bin/device_trackerd.py ${DESTDIR}${ORIGIN_PREFIX}/bin/device-trackerd
	install bin/session_trackerd.py ${DESTDIR}${ORIGIN_PREFIX}/bin/session-trackerd

wirepy:
	install -d ${DESTDIR}${ORIGIN_PREFIX}/lib/python/wirepy
	cp -rp lib/wirepy/* ${DESTDIR}${ORIGIN_PREFIX}/lib/python/wirepy
