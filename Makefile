PACKAGE-NAME := ea-nac
PACKAGE-DESC := Network Access control module
PACKAGE-DEPENDS := ea-authentication, ea-core, ea-captive-portal, libdancer-perl, libdancer-plugin-dbic-perl, libsnmp-perl, libredis-perl, snmpd, libswitch-perl, \
                    libnetaddr-ip-perl, libjson-perl

include ../core/packaging.mk

.PHONY: test
test:
	py.test

.PHONY: install
install: python freeradius authz snmp conf

.PHONY: conf
conf:
	install -d ${DESTDIR}${ORIGIN_PREFIX}/bin
	install -m 755 bin/nac_configurator ${DESTDIR}${ORIGIN_PREFIX}/bin/nac_configurator

.PHONY: freeradius
freeradius:
	install -d ${DESTDIR}${ORIGIN_PREFIX}/nac/freeradius
	install -m 644 freeradius.server ${DESTDIR}${ORIGIN_PREFIX}/nac/freeradius/server
	install -d ${DESTDIR}/etc/freeradius/mods-available
	install -m 644 freeradius.eap ${DESTDIR}/etc/freeradius/mods-available/nac-eap
	install -m 644 freeradius.python ${DESTDIR}/etc/freeradius/mods-available/nac
	install -d ${DESTDIR}/etc/freeradius/mods-enabled
	ln -s ../mods-available/nac-eap ${DESTDIR}/etc/freeradius/mods-enabled
	ln -s ../mods-available/nac ${DESTDIR}/etc/freeradius/mods-enabled

.PHONY: nginx
nginx:
	install -d ${DESTDIR}${ORIGIN_PREFIX}/network/nginx
	install -m 644 nginx.captive-portal-server ${DESTDIR}${ORIGIN_PREFIX}/network/nginx/server

.PHONY: python
python: origin/nac.py origin/snmp.py
	install -d ${DESTDIR}${ORIGIN_PREFIX}/lib/python/origin/freeradius
	install -m 644 -t ${DESTDIR}${ORIGIN_PREFIX}/lib/python/origin origin/nac.py
	install -m 644 -t ${DESTDIR}${ORIGIN_PREFIX}/lib/python/origin origin/snmp.py
	install -m 644 -t ${DESTDIR}${ORIGIN_PREFIX}/lib/python/origin/freeradius origin/freeradius/__init__.py
	install -m 644 -t ${DESTDIR}${ORIGIN_PREFIX}/lib/python/origin/freeradius origin/freeradius/nac.py
  
.PHONY: authz
authz:
	install -d ${DESTDIR}${ORIGIN_PREFIX}/bin
	install -m 755 bin/mac_authz_manager ${DESTDIR}${ORIGIN_PREFIX}/bin

.PHONY: snmp
snmp: perl-lib mibs
	install -d ${DESTDIR}${ORIGIN_PREFIX}/bin
	install -m 755 bin/snmp_poller ${DESTDIR}${ORIGIN_PREFIX}/bin
	install -m 755 bin/snmp_notification_receiver ${DESTDIR}${ORIGIN_PREFIX}/bin
	install -d ${DESTDIR}${ORIGIN_PREFIX}/nac/snmp
	install -m 755 snmptrapd.conf ${DESTDIR}${ORIGIN_PREFIX}/nac/snmp/snmptrapd.conf

.PHONY: perl-lib
perl-lib:
	install -d ${DESTDIR}${ORIGIN_PREFIX}/lib
	cp -r lib/perl5 ${DESTDIR}${ORIGIN_PREFIX}/lib

.PHONY: mibs
mibs:
	install -d ${DESTDIR}${ORIGIN_PREFIX}/nac
	cp -r mibs ${DESTDIR}${ORIGIN_PREFIX}/nac/mibs
