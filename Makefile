PACKAGE-NAME := elan-agent
PACKAGE-DESC := Easy LAN Agent
PACKAGE-DEPENDS := freeradius, freeradius-ldap, python3-mako, make, winbind, krb5-user, libsasl2-modules-gssapi-mit, krb5-pkinit, \
                   python3, uwsgi-plugin-python3, python3-dateutil, python3-six, python-cffi, python-impacket, \
                   gcc, libnetfilter-log-dev, libnfnetlink-dev, python-dev, python-libpcap, python3-cffi, libglib2.0-dev, python3-dev, \
                   libwireshark-dev, libwiretap-dev, wireshark-common, python-pydhcplib, nginx, python-pycurl, python-redis, redis-server,\
                   python3-netifaces, python-netifaces, python-netaddr, python3-netaddr, postfix, suricata, python-tz, python-yaml, \
                   zsync, python-idstools, libapache-htpasswd-perl, libapache-session-perl, libauthen-krb5-simple-perl, \
                   libauthen-radius-perl, libcache-memcached-perl, libchi-driver-memcached-perl, libchi-perl, libconfig-inifiles-perl, \
                   libcrypt-generatepassword-perl, libcrypt-openssl-x509-perl, libdancer-perl, libdancer-plugin-dbic-perl, libdbd-mysql-perl, \
                   libdbi-perl, libfile-flock-perl, libfile-slurp-perl, libfile-which-perl, libhash-merge-perl, libhttp-browserdetect-perl, \
                   libio-interface-perl, libjson-perl, liblog-any-adapter-log4perl-perl, liblog-log4perl-perl, libnamespace-autoclean-perl, \
                   libnetaddr-ip-perl, libnet-appliance-session-perl, libnet-arp-perl, libnet-ldap-perl, libnet-netmask-perl, libnet-snmp-perl, \
                   libreadonly-perl, libredis-perl, libsnmp-perl, libsoap-lite-perl, libsort-naturally-perl, libswitch-perl, libtemplate-perl, \
                   libtest-mockobject-perl, libtime-period-perl, libtry-tiny-perl, libuniversal-require-perl, liburi-escape-xs-perl, \
                   libwww-curl-perl, libxml-simple-perl, libemail-valid-perl, libhtml-form-perl, snmpd, \
                   bridge-utils, vlan, nftables, rdnssd, python3-mako

include packaging.mk

.PHONY: install
install: core-install authentication-install captive-portal-install connection-tracker-install ids-install nac-install network-install

.PHONY: test
test:
	#py.test tests/

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
	install -m 755 exec/authentication_provider ${DESTDIR}${ORIGIN_PREFIX}/bin/
	install -d ${DESTDIR}${ORIGIN_PREFIX}/authentication/pyradius
	install -m 644 pyrad.dictionary            ${DESTDIR}${ORIGIN_PREFIX}/authentication/pyradius/dictionary
	install -d ${DESTDIR}/etc/freeradius/sites-available
	install -d ${DESTDIR}/etc/freeradius/sites-enabled
	install -m 644 freeradius.authentication.server           ${DESTDIR}/etc/freeradius/sites-available/authentication
	ln -s ../sites-available/authentication    ${DESTDIR}/etc/freeradius/sites-enabled
	install -d ${DESTDIR}/etc/default
	install -m 644 freeradius.default          ${DESTDIR}/etc/default/freeradius

.PHONY: authentication-samba
authentication-samba:
	install -d ${DESTDIR}/etc/samba/
	install -m 644 smb.conf ${DESTDIR}/etc/samba/smb.conf

.PHONY: captive-portal-install
captive-portal-install: captive-portal-conf captive-portal-www captive-portal-python

captive-portal-python: origin/captive_portal.py
	install -d ${DESTDIR}${ORIGIN_PREFIX}/lib/python/origin
	install -t ${DESTDIR}${ORIGIN_PREFIX}/lib/python/origin origin/captive_portal.py

.PHONY: captive-portal-conf
captive-portal-conf:
	install -d ${DESTDIR}${ORIGIN_PREFIX}/bin
	install -m 755 exec/configuration_cacher ${DESTDIR}${ORIGIN_PREFIX}/bin/captive-portal_configuration_cacher
	install -m 755 exec/guest_access_manager ${DESTDIR}${ORIGIN_PREFIX}/bin/
    
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
connection-tracker-install: origin/*.py exec/connection_trackerd.py exec/device_trackerd.py exec/session_trackerd.py connection-tracker-wirepy
	install -d ${DESTDIR}${ORIGIN_PREFIX}/lib/python/origin
	install -m 644 -t ${DESTDIR}${ORIGIN_PREFIX}/lib/python/origin origin/*.py
	rm -f ${DESTDIR}${ORIGIN_PREFIX}/lib/python/origin/__init__.py
	install -d ${DESTDIR}${ORIGIN_PREFIX}/bin
	install exec/connection_trackerd.py ${DESTDIR}${ORIGIN_PREFIX}/bin/connection-trackerd
	install exec/device_trackerd.py ${DESTDIR}${ORIGIN_PREFIX}/bin/device-trackerd
	install exec/session_trackerd.py ${DESTDIR}${ORIGIN_PREFIX}/bin/session-trackerd

connection-tracker-wirepy:
	install -d ${DESTDIR}${ORIGIN_PREFIX}/lib/python/wirepy
	cp -rp lib/wirepy/* ${DESTDIR}${ORIGIN_PREFIX}/lib/python/wirepy

.PHONY: core-install
install: core-python core-nginx

.PHONY: core-python
core-python: origin/*.py core-pylib exec/axon.py
	install -d ${DESTDIR}${ORIGIN_PREFIX}/bin
	install exec/axon.py ${DESTDIR}${ORIGIN_PREFIX}/bin/axon
	install -d ${DESTDIR}${ORIGIN_PREFIX}/lib/python/origin
	install -m 644 -t ${DESTDIR}${ORIGIN_PREFIX}/lib/python/origin origin/*.py

.PHONY: core-pylib
core-pylib: tornadoredis tornado redis pyrad
	install -d ${DESTDIR}${ORIGIN_PREFIX}/lib/python
	# Although virtualenv was used to install tornado and co in this repository, it is deployed on edgeagent under /origin/lib/python
	( cd lib/python3.4/site-packages; \
		find $^ -type d -exec install -d ${DESTDIR}${ORIGIN_PREFIX}/lib/python/{} \;; \
		find $^ -type f -not -name \*.pyc -exec cp -Pp {} ${DESTDIR}${ORIGIN_PREFIX}/lib/python/{} \;; \
		find $^ -type l -exec cp -pP {} ${DESTDIR}${ORIGIN_PREFIX}/lib/python/{} \; \
	)

.PHONY: tornadoredis
.PHONY: tornado
.PHONY: redis
core-redis:
	install -d ${DESTDIR}${ORIGIN_PREFIX}/core/redis
	install redis.conf ${DESTDIR}${ORIGIN_PREFIX}/core/redis/conf
.PHONY: pyrad

.PHONY: core-nginx
core-nginx:
	install -d ${DESTDIR}/etc/nginx/sites-enabled
	ln -s ../sites-available/axon ${DESTDIR}/etc/nginx/sites-enabled/
	install -d ${DESTDIR}${ORIGIN_PREFIX}/core/nginx
	install -m 644 nginx.site.axon ${DESTDIR}${ORIGIN_PREFIX}/core/nginx/axon
	install -m 644 control-center-ca.crt ${DESTDIR}${ORIGIN_PREFIX}/core/

.PHONY: ids-install
ids-install: ids-install-suricata ids-install-logger

.PHONY: ids-install-suricata
ids-install-suricata:
	install -d ${DESTDIR}${ORIGIN_PREFIX}/ids/suricata
	install -m 644 suricata.conf ${DESTDIR}${ORIGIN_PREFIX}/ids/suricata/conf
	install -m 644 suricata.reference ${DESTDIR}${ORIGIN_PREFIX}/ids/suricata/reference.config
	install -m 644 suricata.classification ${DESTDIR}${ORIGIN_PREFIX}/ids/suricata/classification.config
	install -d ${DESTDIR}${ORIGIN_PREFIX}/bin
	install exec/rule_fetcher ${DESTDIR}${ORIGIN_PREFIX}/bin/rule-fetcher
	install exec/ids_monitor ${DESTDIR}${ORIGIN_PREFIX}/bin/ids-monitor

.PHONY: ids-install-logger
ids-install-logger:
	install -d ${DESTDIR}${ORIGIN_PREFIX}/bin
	install exec/ids_loggerd ${DESTDIR}${ORIGIN_PREFIX}/bin/ids-loggerd
	install -d ${DESTDIR}${ORIGIN_PREFIX}/lib/python/origin
	install -m 644 -t ${DESTDIR}${ORIGIN_PREFIX}/lib/python/origin origin/*.py

PHONY: nac-install
nac-install: nac-python nac-freeradius nac-authz nac-snmp nac-conf

.PHONY: nac-conf
nac-conf:
	install -d ${DESTDIR}${ORIGIN_PREFIX}/bin
	install -m 755 exec/nac_configurator ${DESTDIR}${ORIGIN_PREFIX}/bin/nac_configurator

.PHONY: nac-freeradius
nac-freeradius:
	install -d ${DESTDIR}${ORIGIN_PREFIX}/nac/freeradius
	install -m 644 freeradius.nac.server ${DESTDIR}${ORIGIN_PREFIX}/nac/freeradius/server
	install -d ${DESTDIR}/etc/freeradius/mods-available
	install -m 644 freeradius.eap ${DESTDIR}/etc/freeradius/mods-available/nac-eap
	install -m 644 freeradius.python ${DESTDIR}/etc/freeradius/mods-available/nac
	install -d ${DESTDIR}/etc/freeradius/mods-enabled
	ln -s ../mods-available/nac-eap ${DESTDIR}/etc/freeradius/mods-enabled
	ln -s ../mods-available/nac ${DESTDIR}/etc/freeradius/mods-enabled

.PHONY: nac-nginx
nac-nginx:
	install -d ${DESTDIR}${ORIGIN_PREFIX}/network/nginx
	install -m 644 nginx.captive-portal-server ${DESTDIR}${ORIGIN_PREFIX}/network/nginx/server

.PHONY: nac-python
nac-python: origin/nac.py origin/snmp.py
	install -d ${DESTDIR}${ORIGIN_PREFIX}/lib/python/origin/freeradius
	install -m 644 -t ${DESTDIR}${ORIGIN_PREFIX}/lib/python/origin origin/nac.py
	install -m 644 -t ${DESTDIR}${ORIGIN_PREFIX}/lib/python/origin origin/snmp.py
	install -m 644 -t ${DESTDIR}${ORIGIN_PREFIX}/lib/python/origin/freeradius origin/freeradius/nac.py
  
.PHONY: nac-authz
nac-authz:
	install -d ${DESTDIR}${ORIGIN_PREFIX}/bin
	install -m 755 exec/mac_authz_manager ${DESTDIR}${ORIGIN_PREFIX}/bin

.PHONY: nac-snmp
nac-snmp: nac-perl-lib nac-mibs
	install -d ${DESTDIR}${ORIGIN_PREFIX}/bin
	install -m 755 exec/snmp_poller ${DESTDIR}${ORIGIN_PREFIX}/bin
	install -m 755 exec/snmp_notification_receiver ${DESTDIR}${ORIGIN_PREFIX}/bin
	install -d ${DESTDIR}${ORIGIN_PREFIX}/nac/snmp
	install -m 755 snmptrapd.conf ${DESTDIR}${ORIGIN_PREFIX}/nac/snmp/snmptrapd.conf

.PHONY: nac-perl-lib
nac-perl-lib:
	install -d ${DESTDIR}${ORIGIN_PREFIX}/lib
	cp -r lib/perl5 ${DESTDIR}${ORIGIN_PREFIX}/lib
	install -d ${DESTDIR}${ORIGIN_PREFIX}/nac/pf/conf
	install -m 644 pf/* ${DESTDIR}${ORIGIN_PREFIX}/nac/pf/conf/

.PHONY: nac-mibs
nac-mibs:
	install -d ${DESTDIR}${ORIGIN_PREFIX}/nac
	cp -r mibs ${DESTDIR}${ORIGIN_PREFIX}/nac/mibs

.PHONY: network-install
network-install:
	install -d ${DESTDIR}/etc/network
	install -m 644 interfaces ${DESTDIR}/etc/network/
	install -d ${DESTDIR}${ORIGIN_PREFIX}/bin
	install -m 755 exec/access_control_configurator ${DESTDIR}${ORIGIN_PREFIX}/bin/access-control-configurator
	install -d ${DESTDIR}${ORIGIN_PREFIX}/network
	install -m 755 nftables.sets   ${DESTDIR}${ORIGIN_PREFIX}/network/
	install -m 755 nftables.chains ${DESTDIR}${ORIGIN_PREFIX}/network/
	install -m 755 interfaces.d ${DESTDIR}${ORIGIN_PREFIX}/network/interfaces
	install -d ${DESTDIR}${ORIGIN_PREFIX}/network/nginx
	install -m 644 nginx.captive-portal-server ${DESTDIR}${ORIGIN_PREFIX}/network/nginx/server
	install -d ${DESTDIR}${ORIGIN_PREFIX}/lib/python/origin
	install -t ${DESTDIR}${ORIGIN_PREFIX}/lib/python/origin origin/network.py


