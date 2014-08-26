PACKAGE-NAME := ea-core
PACKAGE-DESC := Edge Agent Core
PACKAGE-DEPENDS := nginx, python-pycurl, python-redis, redis-server, python3-netifaces, python-netifaces, linux-image-3.15.8-031508-generic, linux-headers-3.15.8-031508-generic, python-netaddr, python3-netaddr, postfix

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
redis:
	install -d ${DESTDIR}${ORIGIN_PREFIX}/core/redis
	install redis.conf ${DESTDIR}${ORIGIN_PREFIX}/core/redis/conf
.PHONY: pyrad

.PHONY: nginx
nginx:
	install -d ${DESTDIR}/etc/nginx/sites-enabled
	ln -s ../sites-available/axon ${DESTDIR}/etc/nginx/sites-enabled/
	install -d ${DESTDIR}${ORIGIN_PREFIX}/core/nginx
	install -m 644 nginx.site.axon ${DESTDIR}${ORIGIN_PREFIX}/core/nginx/axon
