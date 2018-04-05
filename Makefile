PACKAGE-NAME := elan-agent
PACKAGE-DESC := Easy LAN Agent
PACKAGE-DEPENDS := freeradius (>= 3.0.0), freeradius-ldap, freeradius-rest, make, winbind, krb5-user, libsasl2-modules-gssapi-mit, krb5-pkinit, \
                   python3, uwsgi-plugin-python3, python3-dateutil, python3-six, python3-netifaces, python3-netaddr, postfix, suricata, \
                   nginx, redis-server, gcc, libnetfilter-log-dev, libnfnetlink-dev, libpython3-dev, python3-cffi, libglib2.0-dev, python3-dev, \
                   zsync, python3-yaml, python3-websockets, snmpd, snmptrapd, python3-redis, python3-pyrad, bridge-utils, vlan, nftables, rdnssd, \
                   python3-mako, python3-pyroute2, python3-django, python3-logbook, python3-py, python3-lxml, tshark, mosquitto, python3-aiohttp, \
                   libswitch-perl, libdancer-perl, libsnmp-perl, libredis-perl, libjson-perl, libnet-snmp-perl, libnet-ip-perl, libreadonly-perl, \
                   libnet-radius-perl, liblist-moreutils-perl, libsoap-lite-perl, libtest-mockobject-perl, libhtml-form-perl, liblog-log4perl-perl, \
                   libjson-maybexs-perl, libfile-fcntllock-perl, libsocket6-perl, libchi-perl

include packaging.mk

.PHONY: install
install: core-install authentication-install captive-portal-install connection-tracker-install ids-install nac-install network-install

.PHONY: test
test:
	python -m unittest

.PHONY: test-coverage
test-coverage:
	coverage run -m unittest && coverage report; coverage html

authentication-install: authentication-freeradius authentication-python authentication-samba

.PHONY: authentication-python
authentication-python: elan/authentication.py elan/freeradius/*.py
	install -d ${DESTDIR}${ORIGIN_PREFIX}/lib/python/elan/freeradius
	install -t ${DESTDIR}${ORIGIN_PREFIX}/lib/python/elan elan/authentication.py
	install -t ${DESTDIR}${ORIGIN_PREFIX}/lib/python/elan/freeradius elan/freeradius/*.py
	install -d ${DESTDIR}${ORIGIN_PREFIX}/bin
	install bin/rest_elan_proxy.py ${DESTDIR}${ORIGIN_PREFIX}/bin/rest-elan-proxy
  
   
.PHONY: authentication-freeradius
authentication-freeradius:
	install -d ${DESTDIR}/etc/freeradius
	install -m 644 freeradius.dictionary       ${DESTDIR}/etc/freeradius/dictionary
	install -d ${DESTDIR}${ORIGIN_PREFIX}/authentication/freeradius
	install -m 644 freeradius.authentication.policy           ${DESTDIR}${ORIGIN_PREFIX}/authentication/freeradius/policy
	install -m 644 freeradius.ldap-module      ${DESTDIR}${ORIGIN_PREFIX}/authentication/freeradius/ldap-module
	install -m 644 freeradius.ad-module      ${DESTDIR}${ORIGIN_PREFIX}/authentication/freeradius/ad-module
	install -d ${DESTDIR}${ORIGIN_PREFIX}/bin
	install -m 755 bin/authentication_provider.py ${DESTDIR}${ORIGIN_PREFIX}/bin/authentication-provider
	install -d ${DESTDIR}${ORIGIN_PREFIX}/authentication/pyradius
	install -m 644 pyrad.dictionary            ${DESTDIR}${ORIGIN_PREFIX}/authentication/pyradius/dictionary
	install -d ${DESTDIR}/etc/freeradius/sites-available
	install -d ${DESTDIR}/etc/freeradius/sites-enabled
	install -m 644 freeradius.authentication.server           ${DESTDIR}/etc/freeradius/sites-available/authentication
	ln -fs ../sites-available/authentication    ${DESTDIR}/etc/freeradius/sites-enabled/
	install -d ${DESTDIR}/etc/default
	install -m 644 freeradius.default          ${DESTDIR}/etc/default/freeradius

.PHONY: authentication-samba
authentication-samba:
	install -d ${DESTDIR}${ORIGIN_PREFIX}/authentication
	install -m 644 smb.conf ${DESTDIR}${ORIGIN_PREFIX}/authentication/smb.conf
	install -d ${DESTDIR}/etc/sudoers.d
	install -m 440 authentication.sudoers ${DESTDIR}/etc/sudoers.d/authentication

.PHONY: captive-portal-install
captive-portal-install: captive-portal-conf captive-portal-www captive-portal-python

captive-portal-python: elan/captive_portal.py
	install -d ${DESTDIR}${ORIGIN_PREFIX}/lib/python/elan
	install -t ${DESTDIR}${ORIGIN_PREFIX}/lib/python/elan elan/captive_portal.py

.PHONY: captive-portal-conf
captive-portal-conf: bin/captive_portal_configuration_cacher.py bin/guest_access_manager.py
	install -d ${DESTDIR}${ORIGIN_PREFIX}/bin
	install -m 755 bin/captive_portal_configuration_cacher.py ${DESTDIR}${ORIGIN_PREFIX}/bin/captive-portal-configuration-cacher
	install -m 755 bin/guest_access_manager.py ${DESTDIR}${ORIGIN_PREFIX}/bin/guest-access-manager
	install -m 755 bin/redirector.py ${DESTDIR}${ORIGIN_PREFIX}/bin/redirector
    
.PHONY: captive-portal-www
captive-portal-www:
	install -d ${DESTDIR}${ORIGIN_PREFIX}/captive-portal
	find captive_portal -type d -exec install -d ${DESTDIR}${ORIGIN_PREFIX}/captive-portal/{} \;
	find captive_portal -type f -not -name \*.pyc -exec cp -Pp {} ${DESTDIR}${ORIGIN_PREFIX}/captive-portal/{} \;
	install -d ${DESTDIR}/etc/uwsgi
	install -m 644 captive-portal_uwsgi.ini ${DESTDIR}/etc/uwsgi/
	install -d ${DESTDIR}/etc/sudoers.d
	install -m 440 captive-portal.sudoers ${DESTDIR}/etc/sudoers.d/captive-portal
  

.PHONY: connection-tracker-install
connection-tracker-install: elan/*.py bin/connection_trackerd.py bin/device_trackerd.py bin/dns_response_trackerd.py bin/session_trackerd.py connection-tracker-pyshark
	install -d ${DESTDIR}${ORIGIN_PREFIX}/lib/python/elan
	install -m 644 -t ${DESTDIR}${ORIGIN_PREFIX}/lib/python/elan elan/*.py
	rm -f ${DESTDIR}${ORIGIN_PREFIX}/lib/python/elan/__init__.py
	install -d ${DESTDIR}${ORIGIN_PREFIX}/bin
	install bin/connection_trackerd.py ${DESTDIR}${ORIGIN_PREFIX}/bin/connection-trackerd
	install bin/device_trackerd.py ${DESTDIR}${ORIGIN_PREFIX}/bin/device-trackerd
	install bin/dns_response_trackerd.py ${DESTDIR}${ORIGIN_PREFIX}/bin/dns-response-trackerd
	install bin/session_trackerd.py ${DESTDIR}${ORIGIN_PREFIX}/bin/session-trackerd

connection-tracker-pyshark:
	install -d ${DESTDIR}${ORIGIN_PREFIX}/lib/python/pyshark
	cp -rp ${VIRTUAL_ENV}/lib/python3.5/site-packages/pyshark/* ${DESTDIR}${ORIGIN_PREFIX}/lib/python/pyshark
	install -d ${DESTDIR}${ORIGIN_PREFIX}/lib/python/trollius
	cp -rp ${VIRTUAL_ENV}/lib/python3.5/site-packages/trollius/* ${DESTDIR}${ORIGIN_PREFIX}/lib/python/trollius

.PHONY: core-install
install: core-python

.PHONY: core-python
core-python: elan/*.py elan/nac/*.py core-pylib
	install -d ${DESTDIR}${ORIGIN_PREFIX}/lib/python/elan
	install -m 644 -t ${DESTDIR}${ORIGIN_PREFIX}/lib/python/elan elan/*.py

.PHONY: core-pylib
core-pylib: idstools paho scapy serialized_redis
	install -d ${DESTDIR}${ORIGIN_PREFIX}/lib/python
	# Although virtualenv was used to install tornadoredis in this repository, it is deployed on edgeagent under /elan-agent/lib/python
	( cd ${VIRTUAL_ENV}/lib/python3.5/site-packages; \
		find $^ -type d -exec install -d ${DESTDIR}${ORIGIN_PREFIX}/lib/python/{} \;; \
		find $^ -type f -not -name \*.pyc -exec cp -Pp {} ${DESTDIR}${ORIGIN_PREFIX}/lib/python/{} \;; \
		find $^ -type l -exec cp -pP {} ${DESTDIR}${ORIGIN_PREFIX}/lib/python/{} \; \
	)

.PHONY: idstools
.PHONY: paho
.PHONY: scapy
.PHONY: serialized_redis

core-redis:
	install -d ${DESTDIR}${ORIGIN_PREFIX}/core/redis
	install redis.conf ${DESTDIR}${ORIGIN_PREFIX}/core/redis/conf

.PHONY: ids-install
ids-install: ids-install-suricata ids-install-logger

.PHONY: ids-install-suricata
ids-install-suricata:
	install -d ${DESTDIR}${ORIGIN_PREFIX}/ids/suricata
	install -m 644 suricata.conf ${DESTDIR}${ORIGIN_PREFIX}/ids/suricata/conf
	install -m 644 suricata.reference ${DESTDIR}${ORIGIN_PREFIX}/ids/suricata/reference.config
	install -m 644 suricata.classification ${DESTDIR}${ORIGIN_PREFIX}/ids/suricata/classification.config
	install -d ${DESTDIR}${ORIGIN_PREFIX}/bin
	install bin/ids_monitor.py ${DESTDIR}${ORIGIN_PREFIX}/bin/ids-monitor

.PHONY: ids-install-logger
ids-install-logger:
	install -d ${DESTDIR}${ORIGIN_PREFIX}/bin
	install bin/ids_loggerd.py ${DESTDIR}${ORIGIN_PREFIX}/bin/ids-loggerd
	install -d ${DESTDIR}${ORIGIN_PREFIX}/lib/python/elan
	install -m 644 -t ${DESTDIR}${ORIGIN_PREFIX}/lib/python/elan elan/*.py

PHONY: nac-install
nac-install: nac-python nac-freeradius nac-authz nac-snmp nac-conf

.PHONY: nac-conf
nac-conf:
	install -d ${DESTDIR}${ORIGIN_PREFIX}/bin
	install -m 755 bin/radius_configurator.py ${DESTDIR}${ORIGIN_PREFIX}/bin/radius-configurator
	install -m 755 bin/snmp_configurator.py ${DESTDIR}${ORIGIN_PREFIX}/bin/snmp-configurator

.PHONY: nac-freeradius
nac-freeradius: freeradius.nac.server freeradius.nac.modules
	install -d ${DESTDIR}${ORIGIN_PREFIX}/nac/freeradius
	install -m 644 freeradius.nac.server ${DESTDIR}${ORIGIN_PREFIX}/nac/freeradius/server
	install -d ${DESTDIR}/etc/freeradius/mods-available
	install -d ${DESTDIR}/etc/freeradius/mods-enabled
	install -m 644 freeradius.nac.modules ${DESTDIR}/etc/freeradius/mods-available/nac
	ln -fs ../mods-available/nac ${DESTDIR}/etc/freeradius/mods-enabled

.PHONY: nac-nginx
nac-nginx:
	install -d ${DESTDIR}${ORIGIN_PREFIX}/network/nginx
	install -m 644 nginx.captive-portal-server ${DESTDIR}${ORIGIN_PREFIX}/network/nginx/server

.PHONY: nac-python
nac-python: elan/nac/*.py elan/snmp.py
	install -d ${DESTDIR}${ORIGIN_PREFIX}/lib/python/elan/freeradius
	install -d ${DESTDIR}${ORIGIN_PREFIX}/lib/python/elan/nac
	install -m 644 -t ${DESTDIR}${ORIGIN_PREFIX}/lib/python/elan/nac elan/nac/*.py
	install -m 644 -t ${DESTDIR}${ORIGIN_PREFIX}/lib/python/elan elan/snmp.py
	install -m 644 -t ${DESTDIR}${ORIGIN_PREFIX}/lib/python/elan/freeradius elan/freeradius/nac.py
  
.PHONY: nac-authz
nac-authz:
	install -d ${DESTDIR}${ORIGIN_PREFIX}/bin
	install -m 755 bin/mac_authz_manager.py ${DESTDIR}${ORIGIN_PREFIX}/bin/mac-authz-manager

.PHONY: nac-snmp
nac-snmp: nac-perl-lib nac-mibs
	install -d ${DESTDIR}${ORIGIN_PREFIX}/bin
	install -m 755 bin/snmp_poller.pl ${DESTDIR}${ORIGIN_PREFIX}/bin/snmp-poller
	install -m 755 bin/snmp_notification_receiver.py ${DESTDIR}${ORIGIN_PREFIX}/bin/snmp-notification-receiver
	install -d ${DESTDIR}${ORIGIN_PREFIX}/nac/snmp
	install -m 755 snmptrapd.conf ${DESTDIR}${ORIGIN_PREFIX}/nac/snmp/snmptrapd.conf

.PHONY: nac-perl-lib
nac-perl-lib: perl5/ELAN perl5/pf embedded/perl5/pf embedded/perl5/SNMP
	install -d ${DESTDIR}${ORIGIN_PREFIX}/lib/perl5
	cp -r $^ ${DESTDIR}${ORIGIN_PREFIX}/lib/perl5
	install -d ${DESTDIR}${ORIGIN_PREFIX}/nac/pf/conf
	install -m 644 pf/* ${DESTDIR}${ORIGIN_PREFIX}/nac/pf/conf/
	patch ${DESTDIR}${ORIGIN_PREFIX}/lib/perl5/pf/Switch.pm pf::Switch.ipv6-patch

.PHONY: nac-mibs
nac-mibs:
	install -d ${DESTDIR}${ORIGIN_PREFIX}/nac
	cp -r embedded/mibs ${DESTDIR}${ORIGIN_PREFIX}/nac/mibs

.PHONY: network-install
network-install:
	install -d ${DESTDIR}${ORIGIN_PREFIX}/bin
	install -m 755 bin/access_control_configurator.py ${DESTDIR}${ORIGIN_PREFIX}/bin/access-control-configurator
	install -d ${DESTDIR}${ORIGIN_PREFIX}/network
	install -m 755 nftables.sets   ${DESTDIR}${ORIGIN_PREFIX}/network/
	install -m 755 nftables.chains ${DESTDIR}${ORIGIN_PREFIX}/network/
	install -m 755 interfaces.d ${DESTDIR}${ORIGIN_PREFIX}/network/interfaces
	install -m 644 interfaces ${DESTDIR}${ORIGIN_PREFIX}/network/interface.lo
	install -d ${DESTDIR}${ORIGIN_PREFIX}/network/nginx
	install -m 644 nginx.captive-portal-server ${DESTDIR}${ORIGIN_PREFIX}/network/nginx/server
	install -d ${DESTDIR}${ORIGIN_PREFIX}/lib/python/elan
	install -t ${DESTDIR}${ORIGIN_PREFIX}/lib/python/elan elan/network.py


