'''
access.py: code to deal with getting user access credentials

Authors
-------

Michael Hucka <mhucka@caltech.edu> -- Caltech Library

Copyright
---------

Copyright (c) 2018-2019 by the California Institute of Technology.  This code
is open-source software released under a 3-clause BSD license.  Please see the
file "LICENSE" for more information.
'''

from .credentials import keyring_credentials, save_keyring_credentials
from .debug import log
from .ui import login_details


# Global constants.
# .............................................................................

_KEYRING = "org.caltechlibrary.".format(__package__)
'''The name of the keyring used to store Caltech access credentials, if any.'''


# Exported class.
# .............................................................................

class AccessHandler():
    '''Class to use the command line to ask the user for credentials.'''

    def __init__(self, user, pswd, use_keyring):
        '''Initializes internal data with user and password if available.'''
        self._user = user
        self._pswd = pswd
        self._use_keyring = use_keyring


    @property
    def user(self):
        '''Returns the last-provided user name.'''
        return self._user

    @property
    def pswd(self):
        '''Returns the last-provided password.'''
        return self._pswd


    def name_and_password(self, text, user = None, password = None):
        '''Returns a tuple of user, password, and a Boolean indicating
        whether the user cancelled the dialog.
        '''
        tmp_user = user if user is not None else self._user
        tmp_pswd = password if password is not None else self._pswd
        if __debug__: log('keyring {}', 'enabled' if self._use_keyring else 'disabled')
        if not all([tmp_user, tmp_pswd]) and self._use_keyring:
            if __debug__: log('getting credentials from keyring')
            k_user, k_pswd, _, _ = keyring_credentials(_KEYRING, tmp_user)
            if k_user is not None:
                tmp_user = k_user
                tmp_pswd = k_pswd
        tmp_user, tmp_pswd, cancel = login_details(text, tmp_user, tmp_pswd)
        if cancel:
            return tmp_user, tmp_pswd, True
        if self._use_keyring:
            # Save the credentials if they're different.
            s_user, s_pswd, _, _ = keyring_credentials(_KEYRING)
            if s_user != tmp_user or s_pswd != tmp_pswd:
                if __debug__: log('saving credentials to keyring')
                save_keyring_credentials(_KEYRING, tmp_user, tmp_pswd)
        self._user = tmp_user
        self._pswd = tmp_pswd
        return self._user, self._pswd, False
