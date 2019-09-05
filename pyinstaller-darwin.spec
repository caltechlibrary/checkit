# -*- mode: python -*-
# =============================================================================
# @file    pyinstaller-darwin.spec
# @brief   Spec file for PyInstaller for macOS
# @author  Michael Hucka
# @license Please see the file named LICENSE in the project directory
# @website https://github.com/caltechlibrary/describeit
# =============================================================================

import imp
import os
import sys

# The list must contain tuples: ('file', 'destination directory').
data_files = [ ('describeit/describeit.ini', 'describeit'),
               ('describeit/data/client_secrets.json', 'describeit/data'),
               ('describeit/data/help.html', 'describeit/data') ]

configuration = Analysis(['describeit/__main__.py'],
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
                         # by the Describeit code.  Have to exclude them manually.
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
                         name = 'describeit',
                         debug = False,
                         strip = False,
                         upx = True,
                         runtime_tmpdir = None,
                         console = False,
                        )

app             = BUNDLE(executable,
                         name = 'DescribeIt.app',
                         icon = 'dev/icons/generated-icons/describeit-icon-512px.icns',
                         bundle_identifier = None,
                         info_plist = {'NSHighResolutionCapable': 'True',
                                       'NSAppleScriptEnabled': False},
                        )
