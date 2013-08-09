PACKAGE-NAME := lc-ids
PACKAGE-DESC := Light Controller intrusion detection module
PACKAGE-DEPENDS := lc-core, suricata, python-tz

include ../core/packaging.mk

.PHONY: test
test:
	py.test

.PHONY: install
install: suricata logger

.PHONY: suricata
suricata:
	install -d ${DESTDIR}/etc/init
	install -m 644 -T suricata/suricata.init ${DESTDIR}/etc/init/suricata.conf
	install -m 644 -T ids-logger.init ${DESTDIR}/etc/init/ids-logger.conf
	install -d ${DESTDIR}/etc/suricata
	install -m 644 suricata/suricata.yaml ${DESTDIR}/etc/suricata/
	install -m 644 suricata/reference.origin ${DESTDIR}/etc/suricata/
	install -m 644 suricata/classification.origin ${DESTDIR}/etc/suricata/

.PHONY: logger
logger:
	install -d ${DESTDIR}/opt/origin/sbin
	install ids-loggerd ${DESTDIR}/opt/origin/sbin/
	install -d ${DESTDIR}/opt/origin/lib/python/origin
	install -m 644 -t ${DESTDIR}/opt/origin/lib/python/origin origin/*.py
	rm -f ${DESTDIR}/opt/origin/lib/python/origin/__init__.py # this is added by core


