PACKAGE-NAME := ea-network
PACKAGE-DESC := Edge Agent Network module
PACKAGE-DEPENDS := bridge-utils, vlan, nftables

include ../core/packaging.mk

.PHONY: test
test:
	py.test

.PHONY: install
install:
	install -d ${DESTDIR}/etc/network/interfaces.d
	install -m 644 interfaces ${DESTDIR}/etc/network/
	install -d ${DESTDIR}/etc/init
	install -m 644 access-control.upstart ${DESTDIR}/etc/init/access-control.conf
	install -d ${DESTDIR}${ORIGIN_PREFIX}/bin
	install -m 755 bin/start_stop_access-control ${DESTDIR}${ORIGIN_PREFIX}/bin/
	install -d ${DESTDIR}${ORIGIN_PREFIX}/network
	install -m 755 nftables.sets   ${DESTDIR}${ORIGIN_PREFIX}/network/
	install -m 755 nftables.chains ${DESTDIR}${ORIGIN_PREFIX}/network/

