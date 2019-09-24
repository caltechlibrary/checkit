# =============================================================================
# @file    Makefile
# @brief   Makefile for some steps in creating a Check It! application
# @author  Michael Hucka
# @date    2019-09-05
# @license Please see the file named LICENSE in the project directory
# @website https://github.com/caltechlibrary/checkit
# =============================================================================

# Application-specific configuration ------------------------------------------

python_name := checkit
app_name    := CheckIt

# Other variables (should not need changing) ----------------------------------

release	   := $(file < VERSION.txt)
platform   := $(shell python3 -c 'import sys; print(sys.platform)')
distro	   := $(shell python3 -c 'import platform; print(platform.dist()[0].lower())')
linux_vers := $(shell python3 -c 'import platform; print(platform.dist()[1].lower())' | cut -f1-2 -d'.')
macos_vers := $(shell sw_vers -productVersion 2>/dev/null | cut -f1-2 -d'.' || true)
github-css := dev/github-css/github-markdown-css.html

about-file := ABOUT.html
help-file  := $(python_name)/data/help.html

# Main build targets ----------------------------------------------------------

build: | dependencies data-files build-$(platform)

# Platform-specific instructions ----------------------------------------------

build-darwin: $(about-file) $(help-file) dist/$(app_name).app
	packagesbuild dev/installers/macos/$(app_name).pkgproj
	mv dist/$(app_name).pkg dist/$(app_name)-$(release)-macos-$(macos_vers).pkg 

build-linux: dist/$(python_name)
	(cd dist; tar czf $(app_name)-$(release)-$(distro)-$(linux_vers).tar.gz $(python_name))

dist/$(app_name).app:
	pyinstaller --clean pyinstaller-$(platform).spec
	sed -i '' -e 's/0.0.0/$(release)/' dist/$(app_name).app/Contents/Info.plist
	rm -f dist/$(app_name).app/Contents/Info.plist.bak
	rm -f dist/$(python_name)

dependencies:;
	pip3 install -r requirements.txt

data-files: $(about-file) $(help-file)

# Component files placed in the installers ------------------------------------

# Temporary link so that the generic .md -> .html rule works for ABOUT.html.
ABOUT.md: README.md
	ln -s ${<F} ${@F}

%.html: %.md
	pandoc --standalone --quiet -f gfm -H $(github-css) $< | inliner -n > $@

# Miscellaneous directives ----------------------------------------------------

clean: clean-dist clean-html

clean-dist:;
	-rm -fr dist/$(app_name).app dist/$(app_name).pkg dist/$(python_name) build

clean-html:;
	-rm -fr ABOUT.md ABOUT.html $(python_name)/data/help.html tmp.html

.PHONY: build build-darwin build-linux clean clean-dist clean-html
