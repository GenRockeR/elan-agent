ifeq ($(PACKAGE-NAME),)
$(error "Please define PACKAGE-NAME (and PACKAGE-DESC)")
endif

DEBUILD_FLAGS ?= -F

# Make sure that the Origin Nexus key exists in gpg configuration
.PHONY: gpgkey
gpgkey:
	@gpg --list-secret-keys "Origin Nexus" || gpg --import < packaging/gpg.key

$(HOME)/.dupload.conf: packaging/dupload.conf
	cp $< $@

gen-from-tmpl = @perl -pe 's:%\{PACKAGE-NAME\}:${PACKAGE-NAME}:g; s:%\{PACKAGE-DESC\}:${PACKAGE-DESC}:g; s:%\{PACKAGE-DEPENDS\}:${PACKAGE-DEPENDS}:g; s:%\{ELAN_PREFIX\}:${ELAN_PREFIX}:g;' $(1) > $(2)

.PHONY: deb-stable
deb-stable: ELAN_TARGET = stable
deb-stable: deb

.PHONY: deb
deb: gpgkey debian/changelog debian/control
	rm -f ../$(PACKAGE-NAME)_*
	debuild $(DEBUILD_FLAGS) -mdebian@origin-nexus.com --lintian-opts --suppress-tags=file-in-unusual-dir

ifneq ($(wildcard debian/preinst.in),)
deb: debian/preinst
endif

ifneq ($(wildcard debian/postinst.in),)
deb: debian/postinst
endif

ifneq ($(wildcard debian/prerm.in),)
deb: debian/prerm
endif

ifneq ($(wildcard debian/postrm.in),)
deb: debian/postrm
endif

# Make sure to regenerate changelog each time to add EPOCH time of build
.PHONY: debian/changelog
debian/changelog: debian/changelog.in Makefile
	$(call gen-from-tmpl,$<,$@)
	@if [ "$(ELAN_TARGET)" != "stable" ]; \
	then \
		# replace first line of change log with version followed by ~EPOCH (~ in deb-version ordering comes before anything, even nothing: version 1.0~whatever is less that 1.0) \
		perl -p -i -e '$$now=time(); s:\((.*)\):($${1}~$$now): if 1 .. 1' $@ ;\
	fi

debian/control: debian/control.in Makefile
	$(call gen-from-tmpl,$<,$@)

debian/preinst: debian/preinst.in Makefile
	$(call gen-from-tmpl,$<,$@)

debian/postinst: debian/postinst.in Makefile
	$(call gen-from-tmpl,$<,$@)

debian/prerm: debian/prerm.in Makefile
	$(call gen-from-tmpl,$<,$@)

debian/postrm: debian/postrm.in Makefile
	$(call gen-from-tmpl,$<,$@)

PACKAGE-VERSION = $(shell head -1 debian/changelog | cut -f 2 -d \( | cut -f 1 -d \))
.PHONY: ppa-unstable
ppa-unstable: DEBUILD_FLAGS = -S
ppa-unstable: deb
	dput ppa:easy-lan/unstable ../$(PACKAGE-NAME)_$(PACKAGE-VERSION)*_source.changes

.PHONY: ppa-stable
ppa-stable: DEBUILD_FLAGS = -S
ppa-stable: deb-stable
	dput ppa:easy-lan/stable ../$(PACKAGE-NAME)_$(PACKAGE-VERSION)*_source.changes


