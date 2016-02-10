PACKAGE-NAME := elan-agent
PACKAGE-DESC := Easy LAN Agent
PACKAGE-DEPENDS := freeradius, freeradius-ldap, ea-core, python3-mako, make, winbind, krb5-user, libsasl2-modules-gssapi-mit, krb5-pkinit, ea-core, python3, uwsgi-plugin-python3, ea-authentication, ea-network, python3-dateutil, python3-six, python-cffi, python-impacket, gcc, libnetfilter-log-dev, libnfnetlink-dev, python-dev, python-libpcap, python3-cffi, libglib2.0-dev, python3-dev, libwireshark-dev, libwiretap-dev, wireshark-common, python-pydhcplib

include ../core/packaging.mk

.PHONY: test
test:
	py.test

.PHONY: install
install: authentication-install captive-portal-install connection-tracker-install
authentication-install: authentication-freeradius authentication-python authentication-samba

.PHONY: authentication-python
authentication-python: origin/authentication.py origin/freeradius/*.py
	install -d ${DESTDIR}${ORIGIN_PREFIX}/lib/python/origin/freeradius
	install -t ${DESTDIR}${ORIGIN_PREFIX}/lib/python/origin origin/authentication.py
	install -t ${DESTDIR}${ORIGIN_PREFIX}/lib/python/origin/freeradius origin/freeradius/*.py
  
   
.PHONY: authentication-freeradius
authentication-freeradius:
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

.PHONY: authentication-samba
authentication-samba:
	install -d ${DESTDIR}/etc/samba/
	install -m 644 smb.conf ${DESTDIR}/etc/samba/smb.conf

.PHONY: captive-portal-install
captive-portal-install: conf www python

captive-portal-python: origin/captive_portal.py
	install -d ${DESTDIR}${ORIGIN_PREFIX}/lib/python/origin
	install -t ${DESTDIR}${ORIGIN_PREFIX}/lib/python/origin origin/captive_portal.py

.PHONY: captive-portal-conf
captive-portal-conf:
	install -d ${DESTDIR}${ORIGIN_PREFIX}/bin
	install -m 755 bin/configuration_cacher ${DESTDIR}${ORIGIN_PREFIX}/bin/captive-portal_configuration_cacher
	install -m 755 bin/guest_access_manager ${DESTDIR}${ORIGIN_PREFIX}/bin/
    
.PHONY: captive-portal-www
captive-portal-www:
	install -d ${DESTDIR}${ORIGIN_PREFIX}/captive-portal
	cp -p manage.py ${DESTDIR}${ORIGIN_PREFIX}/captive-portal/
	find captive_portal -type d -exec install -d ${DESTDIR}${ORIGIN_PREFIX}/captive-portal/{} \;
	find captive_portal -type f -not -name \*.pyc -exec cp -Pp {} ${DESTDIR}${ORIGIN_PREFIX}/captive-portal/{} \;
	# Although virtualenv was used to install django and co in this repository, it is deployed on edgeagent under /origin/lib/python
	( cd lib/python2.7/site-packages; \
	  find -type d -exec install -d ${DESTDIR}${ORIGIN_PREFIX}/lib/python/{} \;; \
	  find -type f -not -name \*.pyc -exec cp -Pp {} ${DESTDIR}${ORIGIN_PREFIX}/lib/python/{} \;; \
	  find -type l -exec cp -pP {} ${DESTDIR}${ORIGIN_PREFIX}/lib/python/{} \; \
	)
	install -d ${DESTDIR}/etc/uwsgi
	install -m 644 captive-portal_uwsgi.ini ${DESTDIR}/etc/uwsgi/
	install -d ${DESTDIR}/etc/sudoers.d
	install -m 440 captive-portal.sudoers ${DESTDIR}/etc/sudoers.d/captive-portal
  

.PHONY: connection-tracker-install
connection-tracker-install: origin/*.py bin/connection_trackerd.py bin/device_trackerd.py bin/session_trackerd.py connection-tracker-wirepy
	install -d ${DESTDIR}${ORIGIN_PREFIX}/lib/python/origin
	install -m 644 -t ${DESTDIR}${ORIGIN_PREFIX}/lib/python/origin origin/*.py
	rm -f ${DESTDIR}${ORIGIN_PREFIX}/lib/python/origin/__init__.py
	install -d ${DESTDIR}${ORIGIN_PREFIX}/bin
	install bin/connection_trackerd.py ${DESTDIR}${ORIGIN_PREFIX}/bin/connection-trackerd
	install bin/device_trackerd.py ${DESTDIR}${ORIGIN_PREFIX}/bin/device-trackerd
	install bin/session_trackerd.py ${DESTDIR}${ORIGIN_PREFIX}/bin/session-trackerd

connection-tracker-wirepy:
	install -d ${DESTDIR}${ORIGIN_PREFIX}/lib/python/wirepy
	cp -rp lib/wirepy/* ${DESTDIR}${ORIGIN_PREFIX}/lib/python/wirepy

