PACKAGE-NAME := ea-nac
PACKAGE-DESC := Network Access control module
PACKAGE-DEPENDS := ea-authentication, ea-core

include ../core/packaging.mk

.PHONY: test
test:
	py.test

.PHONY: install
install:
	install -d ${DESTDIR}${ORIGIN_PREFIX}/nac/freeradius
	install -m644 freeradius.server ${DESTDIR}${ORIGIN_PREFIX}/nac/freeradius/server
	install -d ${DESTDIR}${ORIGIN_PREFIX}/bin
	install -m755 bin/freeradius_configurator ${DESTDIR}${ORIGIN_PREFIX}/bin/nac_freeradius_configurator
	install -d ${DESTDIR}/etc/freeradius/mods-available
	install -m644 freeradius.eap ${DESTDIR}/etc/freeradius/mods-available/nac-eap
	install -d ${DESTDIR}/etc/freeradius/mods-enabled
	ln -s ../mods-available/nac-eap ${DESTDIR}/etc/freeradius/mods-enabled
   
