'''
__main__: main command-line interface to Check It!

Check It! is a program to help Caltech Librarians perform inventory.  It
takes a list of bar codes and generates a CSV file containing information
about the items drawn from Caltech's TIND server.

Authors
-------

Michael Hucka <mhucka@caltech.edu> -- Caltech Library

Copyright
---------

Copyright (c) 2018-2019 by the California Institute of Technology.  This code
is open-source software released under a 3-clause BSD license.  Please see the
file "LICENSE" for more information.
'''

import faulthandler
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
    '''Takes a file of barcodes and gets info about them from caltech.tind.io.

By default, Check It! will start a graphical user interface (GUI), unless
given the command-line option -G (or /G on Windows).  When running in GUI
mode, Check It! first opens a dialog box for an input file.  This file can be
a CSV file with one barcode per line, or even a plain text file with one
barcode per line.  Next, it will ask the user for their Caltech Access user
name and password, and subsequently, gather info from Caltech.tind.io.  It
will finish by presenting the user with one more file dialog, this time to
create a destination output file where the results will be written.

When started with the -G option (/G on Windows), Check It! will not start
the GUI, and instead, begin by asking for the input file interactively on the
command line.  If given the command-line option -i (or /i on Windows)
followed by a file path name, it will use that file as the input instead of
asking the user.

Next, it will ask the user for a Caltech Access user name and password.  By
default, Check It! uses the operating system's keyring/keychain functionality
to get a user name and password.  If the information does not exist from a
previous run of checkit, it will query the user interactively for the user
name and password, and unless the -K argument (/K on Windows) is given,
store them in the user's keyring/keychain so that it does not have to ask
again in the future.  It is possible to supply the information directly on
the command line using the -u and -p options (or /u and /p on
Windows), but this is discouraged because it is insecure on multiuser
computer systems.

Once it has login credentials, Check It! gets to work contacting
Caltech.tind.io to gather information about each barcode given in the input
file.  (This may take some time if there are a lot of barcodes to process.)

When it is done, it Check It! ask the user for a destination output file
where the results will be written.  If given the command-line option -o (or
/o on Windows) followed by a file path name, it will instead use that file
as the output destination.  The format of the output is the same as that
described in the section for the GUI interface above.

When running in command-line mode, Check It! produces color-coded diagnostic
output as it runs, by default.  However, some terminals or terminal
configurations may make it hard to read the text with colors, so Check It!
offers the -C option (/C on Windows) to turn off colored output.

If given the -@ argument (/@ on Windows), this program will output a detailed
trace of what it is doing, and will also drop into a debugger upon the
occurrence of any errors.  The debug trace will be written to the given
destination, which can be a dash character (-) to indicate console output, or
a file path.

If given the -V option (/V on Windows), this program will print the version
and other information, and exit without doing anything else.
'''

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
        faulthandler.enable()
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
