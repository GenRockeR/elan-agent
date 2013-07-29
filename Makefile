PACKAGE-NAME := lc-ids
PACKAGE-DESC := Light Controller intrusion detection module

include ../core/packaging.mk

.PHONY: test
test:
	py.test

.PHONY: install
install: *.py
	install -d ${DESTDIR}/opt/origin/lib/python
	install -t ${DESTDIR}/opt/origin/lib/python *.py
