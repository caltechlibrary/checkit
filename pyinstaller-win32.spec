# -*- mode: python -*-
# =============================================================================
# @file    pyinstaller-win32.spec
# @brief   Spec file for PyInstaller for Windows
# @author  Michael Hucka
# @license Please see the file named LICENSE in the project directory
# @website https://github.com/caltechlibrary/checkit
# =============================================================================

import importlib
from   os import path
import sys

# The addition of setup.cfg is so that our __init__.py code can work even
# when bundled into the PyInstaller-created application.
data_files = [ ('checkit\data\help.html', 'checkit\data'),
               ('setup.cfg',              'checkit\data') ]

# The "colorful" package has a data file that doesn't get picked up
# automatically, so we have to deal with it ourselves.

colorful_package = importlib.import_module('colorful')
colorful_path = path.dirname(colorful_package.__file__)
data_files += [(path.join(colorful_path, 'data', 'rgb.txt'), 'colorful\data')]

# The rest is pretty normal PyInstaller stuff.

configuration = Analysis([r'checkit\__main__.py'],
                         pathex = ['.'],
                         binaries = [],
                         datas = data_files,
                         hiddenimports = ['apiclient', 'keyring.backends',
                                          'wx._html', 'wx._xml',
                                          'win32timezone', 'winreg'],
                         hookspath = [],
                         runtime_hooks = [],
                         excludes = [],
                         win_no_prefer_redirects = False,
                         win_private_assemblies = False,
                         cipher = None,
                        )

application_pyz    = PYZ(configuration.pure,
                         configuration.zipped_data,
                         cipher = None,
                        )

executable         = EXE(application_pyz,
                         configuration.scripts,
                         configuration.binaries,
                         configuration.zipfiles,
                         configuration.datas,
                         name = 'CheckIt',
                         icon = r'dev\icons\generated-icons\checkit-icon.ico',
                         debug = False,
                         strip = False,
                         upx = True,
                         runtime_tmpdir = None,
                         console = False,
                        )

app             = BUNDLE(executable,
                         name = 'CheckIt.exe',
                         icon = r'dev\icons\generated-icons\checkit-icon.ico',
                         bundle_identifier = None,
                         info_plist = {'NSHighResolutionCapable': 'True'},
                        )
