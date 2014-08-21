PACKAGE-NAME := ea-connection-tracker
PACKAGE-DESC := Connection Tracker Package
PACKAGE-DEPENDS := ea-core, python-cffi, python-impacket, gcc, libnetfilter-log-dev, libnfnetlink-dev, python-dev, python-libpcap


include ../core/packaging.mk

.PHONY: test
test:
	#py.test

.PHONY: install
install: origin/*.py connection_trackerd.py dhcp_trackerd.py device_trackerd.py session_trackerd.py
	install -d ${DESTDIR}${ORIGIN_PREFIX}/lib/python/origin
	install -m 644 -t ${DESTDIR}${ORIGIN_PREFIX}/lib/python/origin origin/*.py
	rm -f ${DESTDIR}${ORIGIN_PREFIX}/lib/python/origin/__init__.py
	install -d ${DESTDIR}${ORIGIN_PREFIX}/bin
	install connection_trackerd.py ${DESTDIR}${ORIGIN_PREFIX}/bin/connection-trackerd
	install dhcp_trackerd.py ${DESTDIR}${ORIGIN_PREFIX}/bin/dhcp-trackerd
	install device_trackerd.py ${DESTDIR}${ORIGIN_PREFIX}/bin/device-trackerd
	install session_trackerd.py ${DESTDIR}${ORIGIN_PREFIX}/bin/session-trackerd
  
