PACKAGE-NAME := ea-connection-tracker
PACKAGE-DESC := Connection Tracker Package
PACKAGE-DEPENDS := ea-core, python-cffi, python-impacket, gcc, libnetfilter-log-dev, libnfnetlink-dev, python-dev


include ../core/packaging.mk

.PHONY: test
test:
	py.test

.PHONY: install
install: origin/*.py trackerd.py dhcp_trackerd.py
	install -d ${DESTDIR}/opt/origin/lib/python/origin
	install -m 644 -t ${DESTDIR}/opt/origin/lib/python/origin origin/*.py
	rm -f ${DESTDIR}/opt/origin/lib/python/origin/__init__.py
	install -d ${DESTDIR}/opt/origin/sbin
	install connection-trackerd.py ${DESTDIR}/opt/origin/sbin/connection-trackerd
