PACKAGE-NAME := ea-captive-portal
PACKAGE-DESC := Captive Portal component of Edge Agent
PACKAGE-DEPENDS := ea-core, python, uwsgi-plugin-python, ebtables, iptables

include ../core/packaging.mk

.PHONY: test
test:
	

.PHONY: install
install: nginx www access-control

python: *.py
	install -d ${DESTDIR}${ORIGIN_PREFIX}/lib/python
	install -t ${DESTDIR}${ORIGIN_PREFIX}/lib/python *.py

.PHONY: nginx
nginx:
	install -d ${DESTDIR}/etc/nginx/sites-available
	install -m 644 nginx.site.captive-portal ${DESTDIR}/etc/nginx/sites-available/captive-portal
	install -d ${DESTDIR}/etc/nginx/sites-enabled
	ln -s ../sites-available/captive-portal ${DESTDIR}/etc/nginx/sites-enabled/captive-portal

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
	install -m 644 captive-portal.init ${DESTDIR}/etc/init/captive-portal.conf
	install -d ${DESTDIR}/etc/sudoers.d
	install -m 440 sudoers ${DESTDIR}/etc/sudoers.d/captive-portal

access-control:
	install -d ${DESTDIR}/etc/init
	install -m 644 access-control.init ${DESTDIR}/etc/init/access-control.conf
	install -d ${DESTDIR}${ORIGIN_PREFIX}/bin
	install -m 755 bin/start_stop_nac ${DESTDIR}${ORIGIN_PREFIX}/bin/
