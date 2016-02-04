PACKAGE-NAME := ea-authentication
PACKAGE-DESC := Authentication component of Edge Agent
PACKAGE-DEPENDS := freeradius, freeradius-ldap, ea-core, python3-mako, make, winbind, krb5-user, libsasl2-modules-gssapi-mit, krb5-pkinit

include ../core/packaging.mk

.PHONY: test
test:
	

.PHONY: install
install: freeradius python samba

.PHONY: python
python: origin/authentication.py origin/freeradius/*.py
	install -d ${DESTDIR}${ORIGIN_PREFIX}/lib/python/origin/freeradius
	install -t ${DESTDIR}${ORIGIN_PREFIX}/lib/python/origin origin/authentication.py
	install -t ${DESTDIR}${ORIGIN_PREFIX}/lib/python/origin/freeradius origin/freeradius/*.py
  
   
.PHONY: freeradius
freeradius:
	install -d ${DESTDIR}${ORIGIN_PREFIX}/authentication/freeradius
	install -m 644 freeradius.dictionary       ${DESTDIR}${ORIGIN_PREFIX}/authentication/freeradius/dictionary
	install -m 644 freeradius.policy           ${DESTDIR}${ORIGIN_PREFIX}/authentication/freeradius/policy
	install -m 644 freeradius.rest-module      ${DESTDIR}${ORIGIN_PREFIX}/authentication/freeradius/rest-module
	install -m 644 freeradius.ldap-module      ${DESTDIR}${ORIGIN_PREFIX}/authentication/freeradius/ldap-module
	install -m 644 freeradius.python-module    ${DESTDIR}${ORIGIN_PREFIX}/authentication/freeradius/python-module
	install -d ${DESTDIR}${ORIGIN_PREFIX}/bin
	install -m 755 bin/authentication_provider ${DESTDIR}${ORIGIN_PREFIX}/bin/
	install -d ${DESTDIR}${ORIGIN_PREFIX}/authentication/pyradius
	install -m 644 pyrad.dictionary            ${DESTDIR}${ORIGIN_PREFIX}/authentication/pyradius/dictionary
	install -d ${DESTDIR}/etc/freeradius/sites-available
	install -d ${DESTDIR}/etc/freeradius/sites-enabled
	install -m 644 freeradius.server           ${DESTDIR}/etc/freeradius/sites-available/authentication
	ln -s ../sites-available/authentication    ${DESTDIR}/etc/freeradius/sites-enabled
	install -d ${DESTDIR}/etc/default
	install -m 644 freeradius.default          ${DESTDIR}/etc/default/freeradius

.PHONY: samba
samba:
	install -d ${DESTDIR}/etc/samba/
	install -m 644 smb.conf ${DESTDIR}/etc/samba/smb.conf
