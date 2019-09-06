# -*- mode: python -*-
# =============================================================================
# @file    pyinstaller-darwin.spec
# @brief   Spec file for PyInstaller for macOS
# @author  Michael Hucka
# @license Please see the file named LICENSE in the project directory
# @website https://github.com/caltechlibrary/checkit
# =============================================================================

import imp
import os
import sys

# The list must contain tuples: ('file', 'destination directory').
data_files = [ ('checkit/checkit.ini', 'checkit'),
               ('checkit/data/client_secrets.json', 'checkit/data'),
               ('checkit/data/help.html', 'checkit/data') ]

configuration = Analysis(['checkit/__main__.py'],
                         pathex = ['.'],
                         binaries = [],
                         datas = data_files,
                         hiddenimports = ['apiclient', 'keyring.backends',
                                          'keyring.backends.OS_X', 'wx._html',
                                          'wx._xml'],
                         hookspath = [],
                         runtime_hooks = [],
                         # For reasons I can't figure out, PyInstaller tries
                         # to load these even though they're never imported
                         # by the Checkit code.  Have to exclude them manually.
                         excludes = ['PyQt4', 'PyQt5', 'gtk', 'matplotlib',
                                     'numpy'],
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
                         name = 'checkit',
                         debug = False,
                         strip = False,
                         upx = True,
                         runtime_tmpdir = None,
                         console = False,
                        )

app             = BUNDLE(executable,
                         name = 'Checkit.app',
                         icon = 'dev/icons/generated-icons/checkit-icon-512px.icns',
                         bundle_identifier = None,
                         info_plist = {'NSHighResolutionCapable': 'True',
                                       'NSAppleScriptEnabled': False},
                        )
