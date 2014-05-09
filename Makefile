PACKAGE-NAME := ea-captive-portal
PACKAGE-DESC := Captive Portal component of Edge Agent
PACKAGE-DEPENDS := ea-core, python, uwsgi-plugin-python, ea-authentication, python-pyrad

include ../core/packaging.mk

.PHONY: test
test:
	

.PHONY: install
install: nginx www freeradius

python: *.py
	install -d ${DESTDIR}${ORIGIN_PREFIX}/lib/python
	install -t ${DESTDIR}${ORIGIN_PREFIX}/lib/python *.py

.PHONY: nginx
nginx:
	install -d ${DESTDIR}${ORIGIN_PREFIX}/captive-portal/nginx
	install -m 644 nginx.captive-portal-servers-header ${DESTDIR}${ORIGIN_PREFIX}/captive-portal/nginx/servers-header
	install -m 644 nginx.captive-portal-server ${DESTDIR}${ORIGIN_PREFIX}/captive-portal/nginx/server
	install -d ${DESTDIR}${ORIGIN_PREFIX}/bin
	install -m 755 bin/nginx_configurator ${DESTDIR}${ORIGIN_PREFIX}/bin/captive-portal_nginx_configurator
	install -d ${DESTDIR}/etc/init
	install -m 644 nginx_configurator.upstart ${DESTDIR}/etc/init/captive-portal_nginx_configurator.conf
  
.PHONY: freeradius
freeradius:
	install -d ${DESTDIR}${ORIGIN_PREFIX}/etc/freeradius/sites-enabled
	install -m644 freeradius.server ${DESTDIR}${ORIGIN_PREFIX}/etc/freeradius/sites-enabled

.PHONY: www
www:
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
	install -d ${DESTDIR}/etc/init
	install -m 644 captive-portal.upstart ${DESTDIR}/etc/init/captive-portal.conf
	install -d ${DESTDIR}/etc/sudoers.d
	install -m 440 sudoers ${DESTDIR}/etc/sudoers.d/captive-portal
