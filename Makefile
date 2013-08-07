PACKAGE-NAME := lc-core
PACKAGE-DESC := Edge Agent Core

include ../core/packaging.mk

.PHONY: test
test:
	py.test

.PHONY: install
install: origin/*.py
	install -d ${DESTDIR}/opt/origin/lib/python
	install -t ${DESTDIR}/opt/origin/lib/python origin/*.py
