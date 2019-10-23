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
from checkit import print_version
from checkit.access import AccessHandler
from checkit.ui import UI
from checkit.exceptions import *
from checkit.debug import set_debug, log
from checkit.main_body import MainBody
from checkit.run_manager import RunManager
from checkit.network import network_available


# Main program.
# ......................................................................

@plac.annotations(
    no_color   = ('do not color-code terminal output',                      'flag',   'C'),
    no_gui     = ('do not start the GUI interface (default: do)',           'flag',   'G'),
    input_csv  = ('input file containing list of barcodes',                 'option', 'i'),
    no_keyring = ('do not store credentials in a keyring service',          'flag',   'K'),
    output_csv = ('output file where results should be written as CSV',     'option', 'o'),
    password   = ('Caltech access password (default: ask for it)',          'option', 'p'),
    quiet      = ('only print important diagnostic messages while working', 'flag',   'q'),
    user       = ('Caltech access user name (default: ask for it)',         'option', 'u'),
    version    = ('print version info and exit',                            'flag',   'V'),
    debug      = ('write detailed trace to "OUT" ("-" means console)',      'option', '@'),
)

def main(no_color = False, no_gui = False, input_csv = 'I', no_keyring = False,
         output_csv = 'O', password = 'P', quiet = False, user = 'U',
         version = False, debug = 'OUT'):
    '''Check It!'''

    # Initial setup -----------------------------------------------------------

    # Our defaults are to do things like color the output, which means the
    # command line flags make more sense as negated values (e.g., "no-color").
    # However, dealing with negated variables in our code is confusing, so:
    use_color   = not no_color
    use_gui     = not no_gui
    use_keyring = not no_keyring
    debugging   = debug != 'OUT'

    # Preprocess arguments and handle early exits -----------------------------

    if debugging:
        set_debug(True, debug)
    if version:
        print_version()
        sys.exit()

    user    = None if user == 'U' else user
    pswd    = None if password == 'P' else password
    infile  = None if input_csv == 'I' else input_csv
    outfile = None if output_csv == 'O' else output_csv

    # Do the real work --------------------------------------------------------

    if __debug__: log('starting')
    ui = manager = exception = None
    try:
        ui = UI('Check It!', 'look up barcodes in TIND', use_gui, use_color, quiet)
        body = MainBody(infile, outfile, AccessHandler(user, pswd, use_keyring))
        manager = RunManager()
        manager.run(ui, body)
        exception = body.exception
    except Exception as ex:
        # MainBody exceptions are caught in its thread, so this is something else.
        exception = sys.exc_info()

    # Try to deal with exceptions gracefully ----------------------------------

    if exception and type(exception[1]) in [KeyboardInterrupt, UserCancelled]:
        if __debug__: log('received {}', exception[1].__class__.__name__)
    elif exception:
        from traceback import format_exception
        ex_type = str(exception[1])
        details = ''.join(format_exception(*exception))
        if __debug__: log('Exception: {}\n{}', ex_type, details)
        if debugging:
            import pdb; pdb.set_trace()
        if ui:
            ui.stop()
        if manager:
            manager.stop()
    if __debug__: log('exiting')


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
