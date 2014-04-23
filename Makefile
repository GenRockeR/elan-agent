PACKAGE-NAME := edge-agent
PACKAGE-DESC := Edge Agent main package
PACKAGE-DEPENDS := ea-network, ea-ids, ea-connection-tracker, ea-captive-portal

include ../core/packaging.mk

.PHONY: test
test:

.PHONY: install
