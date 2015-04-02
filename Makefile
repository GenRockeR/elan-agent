PACKAGE-NAME := ea-ids
PACKAGE-DESC := Edge Agent intrusion detection module
PACKAGE-DEPENDS := ea-core, suricata, python-tz, python-yaml, zsync, python-idstools

include ../core/packaging.mk

.PHONY: test
test:
	#py.test

.PHONY: install
install: install-suricata install-logger

.PHONY: install-suricata
install-suricata:
	install -d ${DESTDIR}/etc/init
	install -m 644 -T suricata/suricata.init ${DESTDIR}/etc/init/suricata.conf
	install -m 644 -T ids-logger.init ${DESTDIR}/etc/init/ids-logger.conf
	install -d ${DESTDIR}/etc/suricata
	install -m 644 suricata/suricata.yaml ${DESTDIR}/etc/suricata/
	install -m 644 suricata/reference.origin ${DESTDIR}/etc/suricata/
	install -m 644 suricata/classification.origin ${DESTDIR}/etc/suricata/
	install -d ${DESTDIR}${ORIGIN_PREFIX}/sbin
	install rule-fetcher ${DESTDIR}${ORIGIN_PREFIX}/sbin/
	install -d ${DESTDIR}/etc/cron.d
	install -m 644 rule-fetcher.cron ${DESTDIR}/etc/cron.d/

.PHONY: install-logger
install-logger:
	install -d ${DESTDIR}${ORIGIN_PREFIX}/sbin
	install ids_loggerd ${DESTDIR}${ORIGIN_PREFIX}/sbin/ids-loggerd
	install -d ${DESTDIR}${ORIGIN_PREFIX}/lib/python/origin
	install -m 644 -t ${DESTDIR}${ORIGIN_PREFIX}/lib/python/origin origin/*.py
	rm -f ${DESTDIR}${ORIGIN_PREFIX}/lib/python/origin/__init__.py # this is added by core


