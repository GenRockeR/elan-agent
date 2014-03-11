PACKAGE-NAME := ea-core
PACKAGE-DESC := Edge Agent Core
PACKAGE-DEPENDS := nginx-full, python-pycurl

include ../core/packaging.mk

.PHONY: test
test:
	py.test

.PHONY: install
install: python nginx

.PHONY: python
python: origin/*.py
	install -d ${DESTDIR}${ORIGIN_PREFIX}/lib/python/origin
	install -m 644 -t ${DESTDIR}${ORIGIN_PREFIX}/lib/python/origin origin/*.py

.PHONY: nginx
nginx:
	install -d ${DESTDIR}/etc/init
	install -m 644 nginx.init ${DESTDIR}/etc/init/nginx.conf
	install -d ${DESTDIR}/etc/nginx/sites-available
	install -m 644 nginx.site.synapse ${DESTDIR}/etc/nginx/sites-available/synapse
	install -d ${DESTDIR}/etc/nginx/sites-enabled
	ln -s ../sites-available/synapse ${DESTDIR}/etc/nginx/sites-enabled/synapse
