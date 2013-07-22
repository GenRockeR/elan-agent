.PHONY: test
test:
	py.test

.PHONY: install
install: *.py
	install -d ${DESTDIR}/opt/origin/lib/python
	install -t ${DESTDIR}/opt/origin/lib/python *.py
