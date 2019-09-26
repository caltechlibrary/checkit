'''
__main__: main command-line interface to Check It!

Authors
-------

Michael Hucka <mhucka@caltech.edu> -- Caltech Library

Copyright
---------

Copyright (c) 2018-2019 by the California Institute of Technology.  This code
is open-source software released under a 3-clause BSD license.  Please see the
file "LICENSE" for more information.
'''

import plac
import sys

import checkit
from checkit.access import AccessHandlerGUI, AccessHandlerCLI
from checkit.control import ControlGUI, ControlCLI
from checkit.exceptions import *
from checkit.debug import set_debug, log
from checkit.main_body import MainBody
from checkit.messages import MessageHandlerGUI, MessageHandlerCLI
from checkit.network import network_available


# Main program.
# ......................................................................

@plac.annotations(
    no_color   = ('do not color-code terminal output',                  'flag',   'C'),
    no_gui     = ('do not start the GUI interface (default: do)',       'flag',   'G'),
    input_csv  = ('input file containing list of barcodes',             'option', 'i'),
    no_keyring = ('do not store credentials in a keyring service',      'flag',   'K'),
    output_csv = ('output file where results should be written as CSV', 'option', 'o'),
    password   = ('Caltech access password',                            'option', 'p'),
    reset_keys = ('reset user and password used',                       'flag',   'R'),
    user       = ('Caltech access user name',                           'option', 'u'),
    version    = ('print version info and exit',                        'flag',   'V'),
    debug      = ('write detailed trace to "OUT" ("-" means console)',  'option', '@'),
)

def main(no_color = False, no_gui = False, input_csv = 'I', no_keyring = False,
         output_csv = 'O', password = 'P', reset_keys = False, user = 'U',
         version = False, debug = 'OUT'):
    '''Check It!'''

    # Initial setup -----------------------------------------------------------

    # Our defaults are to do things like color the output, which means the
    # command line flags make more sense as negated values (e.g., "no-color").
    # However, dealing with negated variables in our code is confusing, so:
    use_color   = not no_color
    use_keyring = not no_keyring
    use_gui     = not no_gui
    debugging   = debug != 'OUT'

    # Preprocess arguments and handle early exits -----------------------------

    if debugging:
        set_debug(True, debug)
    if version:
        print_version()
        sys.exit()

    user     = None if user == 'U' else user
    password = None if password == 'P' else password
    infile   = None if input_csv == 'I' else input_csv
    outfile  = None if output_csv == 'O' else output_csv

    # Do the real work --------------------------------------------------------

    controller = accessor = notifier = exception = None
    try:
        if __debug__: log('initializing handlers')
        byline = 'look up barcodes in Caltech TIND'
        if use_gui:
            controller = ControlGUI('Check It!', byline, debugging)
            accessor   = AccessHandlerGUI(user, password)
            notifier   = MessageHandlerGUI()
        else:
            controller = ControlCLI('Check It!', byline, debugging)
            accessor   = AccessHandlerCLI(user, password, use_keyring, reset_keys)
            notifier   = MessageHandlerCLI(use_color)

        if __debug__: log('starting main body thread')
        body = MainBody(infile, outfile, controller, accessor, notifier)
        controller.run(body)
        exception = body.exception
    except (KeyboardInterrupt, UserCancelled) as ex:
        if __debug__: log('received {}', ex.__class__.__name__)
    except Exception as ex:
        # MainBody exceptions are caught in the thread, so this is something else.
        exception = sys.exc_info()

    # Common exception handling regardless of whether they came from.
    if exception:
        from traceback import format_exception
        details = ''.join(format_exception(*exception))
        if __debug__: log('Exception: ' + details)
        if debugging:
            import pdb; pdb.set_trace()
        if notifier:
            notifier.fatal('Encountered an error', details = details)
        if controller:
            controller.quit()


# Miscellaneous utilities.
# .............................................................................

def print_version():
    this_module = sys.modules[__package__]
    print('{} version {}'.format(this_module.__name__, this_module.__version__))
    print('Authors: {}'.format(this_module.__author__))
    print('URL: {}'.format(this_module.__url__))
    print('License: {}'.format(this_module.__license__))


# Main entry point.
# ......................................................................

# On windows, we want plac to use slash intead of hyphen for cmd-line options.
if sys.platform.startswith('win'):
    main.prefix_chars = '/'

# The following allows users to invoke this using "python3 -m checkit".
if __name__ == '__main__':
    plac.call(main)


# For Emacs users
# ......................................................................
# Local Variables:
# mode: python
# python-indent-offset: 4
# End:
