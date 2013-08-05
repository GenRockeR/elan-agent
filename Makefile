PACKAGE-NAME := lc-ids
PACKAGE-DESC := Light Controller intrusion detection module

include ../core/packaging.mk

.PHONY: test
test:

.PHONY: install
install:
	install -d ${DESTDIR}/etc/init
	install -T suricata.init ${DESTDIR}/etc/init/suricata.conf
	install -d ${DESTDIR}/etc/suricata
	install suricata.yaml ${DESTDIR}/etc/suricata
