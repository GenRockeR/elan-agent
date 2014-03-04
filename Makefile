PACKAGE-NAME := 
PACKAGE-DESC := 
PACKAGE-DEPENDS :=

include ../core/packaging.mk

.PHONY: test
test:
	py.test

.PHONY: install
install: *.py
	install -d ${DESTDIR}${ORIGIN_PREFIX}/lib/python
	install -t ${DESTDIR}${ORIGIN_PREFIX}/lib/python *.py
