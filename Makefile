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
	install -d ${DESTDIR}${ORIGIN_PREFIX}/ids/suricata
	install -m 644 suricata.conf ${DESTDIR}${ORIGIN_PREFIX}/ids/suricata/conf
	install -m 644 suricata.reference ${DESTDIR}${ORIGIN_PREFIX}/ids/suricata/reference.config
	install -m 644 suricata.classification ${DESTDIR}${ORIGIN_PREFIX}/ids/suricata/classification.config
	install -d ${DESTDIR}${ORIGIN_PREFIX}/bin
	install rule_fetcher ${DESTDIR}${ORIGIN_PREFIX}/bin/rule-fetcher
	install ids_monitor ${DESTDIR}${ORIGIN_PREFIX}/bin/ids-monitor

.PHONY: install-logger
install-logger:
	install -d ${DESTDIR}${ORIGIN_PREFIX}/bin
	install ids_loggerd ${DESTDIR}${ORIGIN_PREFIX}/bin/ids-loggerd
	install -d ${DESTDIR}${ORIGIN_PREFIX}/lib/python/origin
	install -m 644 -t ${DESTDIR}${ORIGIN_PREFIX}/lib/python/origin origin/*.py
	rm -f ${DESTDIR}${ORIGIN_PREFIX}/lib/python/origin/__init__.py # this is added by core


