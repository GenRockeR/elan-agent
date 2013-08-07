PACKAGE-NAME := lc-ids
PACKAGE-DESC := Light Controller intrusion detection module

include ../core/packaging.mk

.PHONY: test
test:
	py.test

.PHONY: install
install:
	install -d ${DESTDIR}/etc/init
	install -T suricata.init ${DESTDIR}/etc/init/suricata.conf
	install -T ids-logger.init ${DESTDIR}/etc/init/ids-logger.conf
	install -d ${DESTDIR}/etc/suricata
	install suricata.yaml ${DESTDIR}/etc/suricata
	install -d ${DESTDIR}/opt/origin/sbin
	install ids-loggerd ${DESTDIR}/opt/origin/sbin
	install -d ${DESTDIR}/opt/origin/lib/python/origin
	install -t ${DESTDIR}/opt/origin/lib/python/origin origin/*.py
	rm -f ${DESTDIR}/opt/origin/lib/python/origin/__init__.py


