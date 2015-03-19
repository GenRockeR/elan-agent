PACKAGE-NAME := ea-nac
PACKAGE-DESC := Network Access control module
PACKAGE-DEPENDS := ea-authentication, ea-captive-portal, ea-core, libapache-htpasswd-perl, libapache-session-perl, libauthen-krb5-simple-perl, \
                   libauthen-radius-perl, libcache-memcached-perl, libchi-driver-memcached-perl, libchi-perl, libconfig-inifiles-perl, \
                   libcrypt-generatepassword-perl, libcrypt-openssl-x509-perl, libdancer-perl, libdancer-plugin-dbic-perl, libdbd-mysql-perl, \
                   libdbi-perl, libfile-flock-perl, libfile-slurp-perl, libfile-which-perl, libhash-merge-perl, libhttp-browserdetect-perl, \
                   libio-interface-perl, libjson-perl, liblog-any-adapter-log4perl-perl, liblog-log4perl-perl, libnamespace-autoclean-perl, \
                   libnetaddr-ip-perl, libnet-appliance-session-perl, libnet-arp-perl, libnet-ldap-perl, libnet-netmask-perl, libnet-snmp-perl, \
                   libreadonly-perl, libredis-perl, libsnmp-perl, libsoap-lite-perl, libsort-naturally-perl, libswitch-perl, libtemplate-perl, \
                   libtest-mockobject-perl, libtime-period-perl, libtry-tiny-perl, libuniversal-require-perl, liburi-escape-xs-perl, \
                   libwww-curl-perl, libxml-simple-perl, snmpd

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
	install -d ${DESTDIR}${ORIGIN_PREFIX}/nac/pf/conf
	install -m 644 pf/chi.conf ${DESTDIR}${ORIGIN_PREFIX}/nac/pf/conf/
	install -m 644 pf/log.conf ${DESTDIR}${ORIGIN_PREFIX}/nac/pf/conf/
	install -m 644 pf/switches.conf ${DESTDIR}${ORIGIN_PREFIX}/nac/pf/conf/
	install -m 644 pf/dictionnary ${DESTDIR}${ORIGIN_PREFIX}/nac/pf/conf/

.PHONY: mibs
mibs:
	install -d ${DESTDIR}${ORIGIN_PREFIX}/nac
	cp -r mibs ${DESTDIR}${ORIGIN_PREFIX}/nac/mibs
