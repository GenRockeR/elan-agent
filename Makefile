PACKAGE-NAME := lc-ids
PACKAGE-DESC := Light Controller intrusion detection module
PACKAGE-DEPENDS := lc-core, suricata, python-tz, libnetfilter-log-dev, libnfnetlink-dev, python-dev

include ../core/packaging.mk

.PHONY: test
test:
	py.test

.PHONY: install
install:
	install -d ${DESTDIR}/etc/init
	install -m 644 -T suricata.init ${DESTDIR}/etc/init/suricata.conf
	install -m 644 -T ids-logger.init ${DESTDIR}/etc/init/ids-logger.conf
	install -d ${DESTDIR}/etc/suricata
	install -m 644 suricata.yaml ${DESTDIR}/etc/suricata
	install -d ${DESTDIR}/opt/origin/sbin
	install ids-loggerd ${DESTDIR}/opt/origin/sbin
	install -d ${DESTDIR}/opt/origin/lib/python/origin
	install -m 644 -t ${DESTDIR}/opt/origin/lib/python/origin origin/*.py
	rm -f ${DESTDIR}/opt/origin/lib/python/origin/__init__.py # this is added by core


