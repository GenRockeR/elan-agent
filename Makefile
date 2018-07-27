PACKAGE-NAME := elan-agent
PACKAGE-DESC := Easy LAN Agent
PACKAGE-DEPENDS := python3, python3-dateutil, python3-six, python3-netifaces, python3-netaddr, libpython3-dev, python3-cffi, python3-dev, \
                 python3-yaml, python3-websockets, python3-redis, python3-pyrad, python3-mako, python3-pyroute2, python3-django, \
                 python3-logbook, python3-py, python3-lxml, python3-aiohttp, redis-server, gcc, python3-paho-mqtt, \
                 freeradius (>= 3.0.0), freeradius-ldap, freeradius-rest, make, winbind, krb5-user, \
                 libsasl2-modules-gssapi-mit, krb5-pkinit, uwsgi-plugin-python3, suricata, nginx, libnetfilter-log-dev, \
                 libnfnetlink-dev, libglib2.0-dev, zsync, snmpd, snmptrapd, bridge-utils, vlan, nftables, rdnssd, tshark, \
                 mosquitto, libswitch-perl, libdancer-perl, libsnmp-perl, libredis-perl, libjson-perl, libnet-snmp-perl, \
                 libnet-ip-perl, libreadonly-perl, libnet-radius-perl, liblist-moreutils-perl, libsoap-lite-perl, \
                 libtest-mockobject-perl, libhtml-form-perl, liblog-log4perl-perl, libjson-maybexs-perl, \
                 libfile-fcntllock-perl, libsocket6-perl, libchi-perl, netplan.io (>= 0.36.2), python3-dnspython, python3-watchdog

ELAN_PREFIX := /elan-agent
PYTHON_PIPENVFILES := embedded/python

.PHONY: build
build:
	# Nothing to build...

include packaging.mk

.PHONY: install
install: core-install authentication-install captive-portal-install connection-tracker-install ids-install nac-install network-install

.PHONY: install-dependencies
install-dependencies:
	echo "${PACKAGE-DEPENDS}" | sed 's/,/\n/g' | awk '{ print $$1}' | xargs apt install -y

.PHONY: test
test:
	#

.PHONY: test-python
test-python:
	PYTHONPATH=./embedded/python python3 -m unittest

.PHONY: test-coverage
test-coverage:
	coverage run -m unittest && coverage report; coverage html

authentication-install: authentication-freeradius authentication-python authentication-samba

.PHONY: authentication-python
authentication-python: elan/authentication.py elan/freeradius/*.py
	install -d ${DESTDIR}${ELAN_PREFIX}/lib/python/elan/freeradius
	install -t ${DESTDIR}${ELAN_PREFIX}/lib/python/elan elan/authentication.py
	install -t ${DESTDIR}${ELAN_PREFIX}/lib/python/elan/freeradius elan/freeradius/*.py
	install -d ${DESTDIR}${ELAN_PREFIX}/bin
	install bin/rest_elan_proxy.py ${DESTDIR}${ELAN_PREFIX}/bin/rest-elan-proxy
  
   
.PHONY: authentication-freeradius
authentication-freeradius:
	install -d ${DESTDIR}/etc/freeradius/3.0
	install -m 644 freeradius.dictionary       ${DESTDIR}/etc/freeradius/3.0/dictionary
	install -d ${DESTDIR}${ELAN_PREFIX}/authentication/freeradius
	install -m 644 freeradius.authentication.policy           ${DESTDIR}${ELAN_PREFIX}/authentication/freeradius/policy
	install -m 644 freeradius.ldap-module      ${DESTDIR}${ELAN_PREFIX}/authentication/freeradius/ldap-module
	install -m 644 freeradius.ad-module      ${DESTDIR}${ELAN_PREFIX}/authentication/freeradius/ad-module
	install -d ${DESTDIR}${ELAN_PREFIX}/bin
	install -m 755 bin/authentication_provider.py ${DESTDIR}${ELAN_PREFIX}/bin/authentication-provider
	install -d ${DESTDIR}${ELAN_PREFIX}/authentication/pyradius
	install -m 644 pyrad.dictionary            ${DESTDIR}${ELAN_PREFIX}/authentication/pyradius/dictionary
	install -d ${DESTDIR}/etc/freeradius/3.0/sites-available
	install -d ${DESTDIR}/etc/freeradius/3.0/sites-enabled
	install -m 644 freeradius.authentication.server           ${DESTDIR}/etc/freeradius/3.0/sites-available/authentication
	ln -fs ../sites-available/authentication    ${DESTDIR}/etc/freeradius/3.0/sites-enabled/
	install -d ${DESTDIR}/etc/default
	install -m 644 freeradius.default          ${DESTDIR}/etc/default/freeradius

.PHONY: authentication-samba
authentication-samba:
	install -d ${DESTDIR}${ELAN_PREFIX}/authentication
	install -m 644 smb.conf ${DESTDIR}${ELAN_PREFIX}/authentication/smb.conf
	install -d ${DESTDIR}/etc/sudoers.d
	install -m 440 authentication.sudoers ${DESTDIR}/etc/sudoers.d/authentication

.PHONY: captive-portal-install
captive-portal-install: captive-portal-conf captive-portal-www captive-portal-python

captive-portal-python: elan/captive_portal.py
	install -d ${DESTDIR}${ELAN_PREFIX}/lib/python/elan
	install -t ${DESTDIR}${ELAN_PREFIX}/lib/python/elan elan/captive_portal.py

.PHONY: captive-portal-conf
captive-portal-conf: bin/guest_access_manager.py bin/redirector.py
	install -d ${DESTDIR}${ELAN_PREFIX}/bin
	install -m 755 bin/guest_access_manager.py ${DESTDIR}${ELAN_PREFIX}/bin/guest-access-manager
	install -m 755 bin/redirector.py ${DESTDIR}${ELAN_PREFIX}/bin/redirector
    
.PHONY: captive-portal-www
captive-portal-www:
	install -d ${DESTDIR}${ELAN_PREFIX}/captive-portal
	find captive_portal -type d -exec install -d ${DESTDIR}${ELAN_PREFIX}/captive-portal/{} \;
	find captive_portal -type f -not -name \*.pyc -exec cp -Pp {} ${DESTDIR}${ELAN_PREFIX}/captive-portal/{} \;
	install -d ${DESTDIR}/etc/uwsgi
	install -m 644 captive-portal_uwsgi.ini ${DESTDIR}/etc/uwsgi/
  

.PHONY: connection-tracker-install
connection-tracker-install: elan/*.py bin/connection_trackerd.py bin/device_trackerd.py bin/dns_response_trackerd.py bin/session_trackerd.py connection-tracker-pyshark
	install -d ${DESTDIR}${ELAN_PREFIX}/lib/python/elan
	install -m 644 -t ${DESTDIR}${ELAN_PREFIX}/lib/python/elan elan/*.py
	rm -f ${DESTDIR}${ELAN_PREFIX}/lib/python/elan/__init__.py
	install -d ${DESTDIR}${ELAN_PREFIX}/bin
	install bin/connection_trackerd.py ${DESTDIR}${ELAN_PREFIX}/bin/connection-trackerd
	install bin/device_trackerd.py ${DESTDIR}${ELAN_PREFIX}/bin/device-trackerd
	install bin/dns_response_trackerd.py ${DESTDIR}${ELAN_PREFIX}/bin/dns-response-trackerd
	install bin/session_trackerd.py ${DESTDIR}${ELAN_PREFIX}/bin/session-trackerd

connection-tracker-pyshark:
	install -d ${DESTDIR}${ELAN_PREFIX}/lib/python/pyshark
	cp -rp ${PYTHON_PIPENVFILES}/pyshark/* ${DESTDIR}${ELAN_PREFIX}/lib/python/pyshark
	install -d ${DESTDIR}${ELAN_PREFIX}/lib/python/trollius
	cp -rp ${PYTHON_PIPENVFILES}/trollius/* ${DESTDIR}${ELAN_PREFIX}/lib/python/trollius

.PHONY: core-install
core-install: core-python

.PHONY: core-python
core-python: elan/*.py elan/nac/*.py core-pylib
	install -d ${DESTDIR}${ELAN_PREFIX}/lib/python/elan
	install -m 644 -t ${DESTDIR}${ELAN_PREFIX}/lib/python/elan elan/*.py
	install -d ${DESTDIR}${ELAN_PREFIX}/bin
	install -m 755 bin/configuration_cacher.py ${DESTDIR}${ELAN_PREFIX}/bin/configuration-cacher

.PHONY: core-pylib
core-pylib: idstools paho scapy serialized_redis
	install -d ${DESTDIR}${ELAN_PREFIX}/lib/python
	( cd ${PYTHON_PIPENVFILES}; \
		find $^ -type d -exec install -d ${DESTDIR}${ELAN_PREFIX}/lib/python/{} \;; \
		find $^ -type f -not -name \*.pyc -exec cp -Pp {} ${DESTDIR}${ELAN_PREFIX}/lib/python/{} \;; \
		find $^ -type l -exec cp -pP {} ${DESTDIR}${ELAN_PREFIX}/lib/python/{} \; \
	)

.PHONY: idstools
.PHONY: paho
.PHONY: scapy
.PHONY: serialized_redis

core-redis:
	install -d ${DESTDIR}${ELAN_PREFIX}/core/redis
	install redis.conf ${DESTDIR}${ELAN_PREFIX}/core/redis/conf

.PHONY: ids-install
ids-install: ids-install-suricata ids-install-logger

.PHONY: ids-install-suricata
ids-install-suricata:
	install -d ${DESTDIR}${ELAN_PREFIX}/ids/suricata
	install -m 644 suricata.conf ${DESTDIR}${ELAN_PREFIX}/ids/suricata/conf
	install -m 644 suricata.reference ${DESTDIR}${ELAN_PREFIX}/ids/suricata/reference.config
	install -m 644 suricata.classification ${DESTDIR}${ELAN_PREFIX}/ids/suricata/classification.config
	install -d ${DESTDIR}${ELAN_PREFIX}/bin
	install bin/ids_monitor.py ${DESTDIR}${ELAN_PREFIX}/bin/ids-monitor

.PHONY: ids-install-logger
ids-install-logger:
	install -d ${DESTDIR}${ELAN_PREFIX}/bin
	install bin/ids_loggerd.py ${DESTDIR}${ELAN_PREFIX}/bin/ids-loggerd
	install -d ${DESTDIR}${ELAN_PREFIX}/lib/python/elan
	install -m 644 -t ${DESTDIR}${ELAN_PREFIX}/lib/python/elan elan/*.py

PHONY: nac-install
nac-install: nac-python nac-freeradius nac-authz nac-snmp nac-conf

.PHONY: nac-conf
nac-conf:
	install -d ${DESTDIR}${ELAN_PREFIX}/bin
	install -m 755 bin/radius_configurator.py ${DESTDIR}${ELAN_PREFIX}/bin/radius-configurator
	install -m 755 bin/snmp_configurator.py ${DESTDIR}${ELAN_PREFIX}/bin/snmp-configurator

.PHONY: nac-freeradius
nac-freeradius: freeradius.nac.server freeradius.nac.modules
	install -d ${DESTDIR}${ELAN_PREFIX}/nac/freeradius
	install -m 644 freeradius.nac.server ${DESTDIR}${ELAN_PREFIX}/nac/freeradius/server
	install -d ${DESTDIR}/etc/freeradius/3.0/mods-available
	install -d ${DESTDIR}/etc/freeradius/3.0/mods-enabled
	install -m 644 freeradius.nac.modules ${DESTDIR}/etc/freeradius/3.0/mods-available/nac
	ln -fs ../mods-available/nac ${DESTDIR}/etc/freeradius/3.0/mods-enabled

.PHONY: nac-nginx
nac-nginx:
	install -d ${DESTDIR}${ELAN_PREFIX}/network/nginx
	install -m 644 nginx.captive-portal-server ${DESTDIR}${ELAN_PREFIX}/network/nginx/server

.PHONY: nac-python
nac-python: elan/nac/*.py elan/snmp.py
	install -d ${DESTDIR}${ELAN_PREFIX}/lib/python/elan/freeradius
	install -d ${DESTDIR}${ELAN_PREFIX}/lib/python/elan/nac
	install -m 644 -t ${DESTDIR}${ELAN_PREFIX}/lib/python/elan/nac elan/nac/*.py
	install -m 644 -t ${DESTDIR}${ELAN_PREFIX}/lib/python/elan elan/snmp.py
	install -m 644 -t ${DESTDIR}${ELAN_PREFIX}/lib/python/elan/freeradius elan/freeradius/nac.py
  
.PHONY: nac-authz
nac-authz:
	install -d ${DESTDIR}${ELAN_PREFIX}/bin
	install -m 755 bin/mac_authz_manager.py ${DESTDIR}${ELAN_PREFIX}/bin/mac-authz-manager

.PHONY: nac-snmp
nac-snmp: nac-perl-lib nac-mibs
	install -d ${DESTDIR}${ELAN_PREFIX}/bin
	install -m 755 bin/snmp_poller.pl ${DESTDIR}${ELAN_PREFIX}/bin/snmp-poller
	install -m 755 bin/snmp_notification_receiver.py ${DESTDIR}${ELAN_PREFIX}/bin/snmp-notification-receiver
	install -d ${DESTDIR}${ELAN_PREFIX}/nac/snmp
	install -m 755 snmptrapd.conf ${DESTDIR}${ELAN_PREFIX}/nac/snmp/snmptrapd.conf

.PHONY: nac-perl-lib
nac-perl-lib: perl5/ELAN perl5/pf embedded/perl5/pf embedded/perl5/SNMP
	install -d ${DESTDIR}${ELAN_PREFIX}/lib/perl5
	cp -r $^ ${DESTDIR}${ELAN_PREFIX}/lib/perl5
	install -d ${DESTDIR}${ELAN_PREFIX}/nac/pf/conf
	install -m 644 pf/* ${DESTDIR}${ELAN_PREFIX}/nac/pf/conf/
	patch ${DESTDIR}${ELAN_PREFIX}/lib/perl5/pf/Switch.pm pf::Switch.ipv6-patch

.PHONY: nac-mibs
nac-mibs:
	install -d ${DESTDIR}${ELAN_PREFIX}/nac
	cp -r embedded/mibs ${DESTDIR}${ELAN_PREFIX}/nac/mibs

.PHONY: network-install
network-install:
	install -d ${DESTDIR}${ELAN_PREFIX}/bin
	install -m 755 bin/access_control_monitor.py ${DESTDIR}${ELAN_PREFIX}/bin/access-control-monitor
	install -m 755 bin/access_control_configurator.py ${DESTDIR}${ELAN_PREFIX}/bin/access-control-configurator
	install -m 755 bin/network_configurator.py ${DESTDIR}${ELAN_PREFIX}/bin/network-configurator
	install -d ${DESTDIR}${ELAN_PREFIX}/network
	install -m 755 nftables ${DESTDIR}${ELAN_PREFIX}/network/
	install -m 644 netplan-*.yaml ${DESTDIR}${ELAN_PREFIX}/network/
	install -d ${DESTDIR}${ELAN_PREFIX}/network/nginx
	install -m 644 nginx.captive-portal-server ${DESTDIR}${ELAN_PREFIX}/network/nginx/server
	install -d ${DESTDIR}${ELAN_PREFIX}/lib/python/elan
	install -t ${DESTDIR}${ELAN_PREFIX}/lib/python/elan elan/network.py


.PHONY: embedded-python
embedded-python:
	rm -rf ${PYTHON_PIPENVFILES}
	mkdir -p ${PYTHON_PIPENVFILES}
	cp Pipfile* ${PYTHON_PIPENVFILES}/
	cd ${PYTHON_PIPENVFILES}; pipenv --three install --ignore-pipfile; \
		cp -rp $$(pipenv --venv)/lib/python3.6/site-packages/*/ .; \
		rm -rf *.dist-info easy_install.py pip  pkg_resources  setuptools wheel; \
		find . -name \*.pyc -o -name __pycache__ -print0 | xargs -0 -I {} /bin/rm -rf "{}" \;; \
		pipenv --rm

deb: embedded-python
