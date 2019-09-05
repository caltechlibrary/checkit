#!/usr/bin/env python3
# =============================================================================
# @file    setup.py
# @brief   Describe It! setup file
# @author  Michael Hucka <mhucka@caltech.edu>
# @license Please see the file named LICENSE in the project directory
# @website https://github.com/caltechlibrary/describeit
# =============================================================================

import os
from   os import path
from   setuptools import setup


# Read the contents of auxiliary files.
# ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

here = path.abspath(path.dirname(__file__))

with open(path.join(here, 'requirements.txt')) as f:
    reqs = f.read().rstrip().splitlines()

with open(path.join(SETUP_DIR, 'README.md'), 'r', errors = 'ignore') as f:
    readme = f.read()

# The following reads the variables without doing an import, because the
# latter would cause the python execution environment to fail if any
# dependencies are not already installed -- negating most of the reason we're
# using setup() in the first place.  This code also avoids eval, for security.

version = {}
with open(path.join(here, 'describeit/__version__.py')) as f:
    text = f.read().rstrip().splitlines()
    vars = [line for line in text if line.startswith('__') and '=' in line]
    for v in vars:
        setting = v.split('=')
        version[setting[0].strip()] = setting[1].strip().replace("'", '')


# Now define our namesake.
# ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

package_name = version['__title__'].lower()

setup(
    name             = package_name,
    description      = version['__description__'],
    long_description = readme,
    version          = version['__version__'],
    license          = version['__license__'],
    url              = version['__url__'],
    download_url     = version['__download_url__'],
    author           = version['__author__'],
    author_email     = version['__email__'],
    maintainer       = version['__maintainer__'],
    maintainer_email = version['__maintainer_email__'],
    keywords         = version['__keywords__'],
    project_urls     = {
          'Source' : version['__source_url__'],
          'Tracker': version['__source_url__'] + '/issues',
      },
    packages         = [package_name],
    scripts          = ['bin/describeit'],
    package_data     = {'describeit': ['describeit/describeit.ini',
                                   'describeit/data/default_template.docx',
                                   'describeit/data/client_secrets.json']},

    include_package_data = True,
    install_requires = reqs,
    platforms        = 'any',
    python_requires  = '>=3',
)
