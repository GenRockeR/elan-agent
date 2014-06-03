PACKAGE-NAME := ea-nac
PACKAGE-DESC := Network Access control module
PACKAGE-DEPENDS := ea-authentication, ea-core, ea-captive-portal

include ../core/packaging.mk

.PHONY: test
test:
	py.test

.PHONY: install
install: python freeradius firewall

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
  
.PHONY: firewall
firewall:
	install -d ${DESTDIR}${ORIGIN_PREFIX}/bin
	install -m755 bin/firewall_configurator ${DESTDIR}${ORIGIN_PREFIX}/bin/nac_firewall_configurator
