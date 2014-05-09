PACKAGE-NAME := ea-authentication
PACKAGE-DESC := Authentication component of Edge Agent
PACKAGE-DEPENDS := freeradius, freeradius-ldap, ea-core

include ../core/packaging.mk

.PHONY: test
test:
	

.PHONY: install
install: nginx www freeradius

  
.PHONY: freeradius
freeradius:
	install -d ${DESTDIR}${ORIGIN_PREFIX}/authentication/freeradius
	install -m 644 freeradius.dictionary ${DESTDIR}${ORIGIN_PREFIX}/authentication/freeradius/dictionary
	install -m 644 freeradius.server ${DESTDIR}${ORIGIN_PREFIX}/authentication/freeradius/server
	install -m 644 freeradius.rest-module ${DESTDIR}${ORIGIN_PREFIX}/authentication/freeradius/rest-module
	install -m 644 freeradius.ldap-module ${DESTDIR}${ORIGIN_PREFIX}/authentication/freeradius/ldap-module
	install -d ${DESTDIR}${ORIGIN_PREFIX}/bin
	install -m 755 bin/freeradius_configurator ${DESTDIR}${ORIGIN_PREFIX}/bin/authentication_freeradius_configurator
	install -d ${DESTDIR}/etc/init
	install -m 644 freeradius_configurator.upstart ${DESTDIR}/etc/init/authentication_freeradius_configurator.conf
