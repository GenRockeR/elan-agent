PACKAGE-NAME := ea-core
PACKAGE-DESC := Edge Agent Core
PACKAGE-DEPENDS := nginx, python-pycurl, python-redis, redis-server, python3-netifaces, python-netiface

include ../core/packaging.mk

.PHONY: test
test:
	#py.test

.PHONY: install
install: python nginx

.PHONY: python
python: origin/*.py pylib bin/axon.py
	install -d ${DESTDIR}${ORIGIN_PREFIX}/bin
	install bin/axon.py ${DESTDIR}${ORIGIN_PREFIX}/bin/axon
	install -d ${DESTDIR}${ORIGIN_PREFIX}/lib/python/origin
	install -m 644 -t ${DESTDIR}${ORIGIN_PREFIX}/lib/python/origin origin/*.py

.PHONY: pylib
pylib: tornadoredis tornado redis pyrad
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
.PHONY: pyrad

.PHONY: nginx
nginx:
	install -d ${DESTDIR}/etc/init
	install -m 644 nginx.init ${DESTDIR}/etc/init/nginx.conf
	install -d ${DESTDIR}/etc/nginx/sites-available
	install -m 644 nginx.site.synapse ${DESTDIR}/etc/nginx/sites-available/synapse
	install -d ${DESTDIR}/etc/nginx/sites-enabled
	ln -s ../sites-available/synapse ${DESTDIR}/etc/nginx/sites-enabled/synapse
