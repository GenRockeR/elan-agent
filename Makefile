PACKAGE-NAME := ea-nac
PACKAGE-DESC := Network Access control module
PACKAGE-DEPENDS := ea-authentication, ea-core, ea-captive-portal

include ../core/packaging.mk

.PHONY: test
test:
	py.test

.PHONY: install
install: python freeradius authz

.PHONY: freeradius
freeradius:
	install -d ${DESTDIR}${ORIGIN_PREFIX}/nac/freeradius
	install -m644 freeradius.server ${DESTDIR}${ORIGIN_PREFIX}/nac/freeradius/server
	install -d ${DESTDIR}${ORIGIN_PREFIX}/bin
	install -m755 bin/freeradius_configurator ${DESTDIR}${ORIGIN_PREFIX}/bin/nac_freeradius_configurator
	install -d ${DESTDIR}/etc/freeradius/mods-available
	install -m644 freeradius.eap ${DESTDIR}/etc/freeradius/mods-available/nac-eap
	install -d ${DESTDIR}/etc/freeradius/mods-enabled
	ln -s ../mods-available/nac-eap ${DESTDIR}/etc/freeradius/mods-enabled

.PHONY: nginx
nginx:
	install -d ${DESTDIR}${ORIGIN_PREFIX}/network/nginx
	install -m 644 nginx.captive-portal-server ${DESTDIR}${ORIGIN_PREFIX}/network/nginx/server

.PHONY: python
python: origin/nac.py
	install -d ${DESTDIR}${ORIGIN_PREFIX}/lib/python/origin
	install -t ${DESTDIR}${ORIGIN_PREFIX}/lib/python/origin origin/nac.py
  
.PHONY: authz
authz:
	install -d ${DESTDIR}${ORIGIN_PREFIX}/bin
	install -m 755 bin/mac_authz_manager ${DESTDIR}${ORIGIN_PREFIX}/bin
