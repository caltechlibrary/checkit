# =============================================================================
# @file    substitute_version.py
# @brief   Replace version string in the InnoSetup script
# @author  Michael Hucka <mhucka@caltech.edu>
# @license Please see the file named LICENSE in the project directory
# @website https://github.com/caltechlibrary/checkit
# =============================================================================

import glob
import os
from   os import path
from   setuptools.config import read_configuration

here      = path.abspath(path.dirname(__file__))
setup_cfg = path.join(here, '../../..', 'setup.cfg')
conf_dict = read_configuration(setup_cfg)
conf      = conf_dict['metadata']

inno_in = glob.glob('dev/installers/windows/*_innosetup_script.iss.in')
if not inno_in:
    # This happens when testing the script from the current directory.
    inno_in = glob.glob('*_innosetup_script.iss.in')

inno_in  = inno_in[0]
inno_out = path.splitext(inno_in)[0]

with open(inno_in) as infile:
    with open(inno_out, 'w') as outfile:
        outfile.write(infile.read().replace('@@VERSION@@', conf['version']))
