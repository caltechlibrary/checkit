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
from checkit.progress import ProgressIndicatorGUI, ProgressIndicatorCLI


# Main program.
# ......................................................................

@plac.annotations(
    no_color   = ('do not color-code terminal output',                  'flag',   'C'),
    no_gui     = ('do not start the GUI interface (default: do)',       'flag',   'G'),
    input_csv  = ('input file containing list of barcodes',             'option', 'i'),
    no_keyring = ('do not store credentials in a keyring service',      'flag',   'K'),
    output_csv = ('output file where results should be written as CSV', 'option', 'o'),
    password   = ('Caltech access user password',                       'option', 'p'),
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

    # Preprocess arguments and handle early exits -----------------------------

    if debug != 'OUT':
        set_debug(True, debug)
    if version:
        print_version()
        sys.exit()

    user     = None if user == 'U' else user
    password = None if password == 'P' else password
    infile   = None if input_csv == 'I' else input_csv
    outfile  = None if output_csv == 'O' else output_csv

    # Do the real work --------------------------------------------------------

    try:
        if __debug__: log('initializing handlers')
        if use_gui:
            controller = ControlGUI('Check It!')
            accessor   = AccessHandlerGUI(user, password)
            notifier   = MessageHandlerGUI()
            tracer     = ProgressIndicatorGUI()
        else:
            controller = ControlCLI('Check It!')
            accessor   = AccessHandlerCLI(user, password, use_keyring, reset_keys)
            notifier   = MessageHandlerCLI(use_color)
            tracer     = ProgressIndicatorCLI(use_color)

        if __debug__: log('starting main body thread')
        body = MainBody(infile, outfile, controller, accessor, notifier, tracer, debug)
        #controller.start(body)
    except (KeyboardInterrupt, UserCancelled) as err:
        tracer.stop('Quitting.')
        controller.stop()
    except ServiceFailure:
        tracer.stop('Stopping due to a problem connecting to services')
        controller.stop()
    except Exception as err:
        import traceback
        if debug:
            tracer.stop('{}\n{}'.format(str(ex), traceback.format_exc()))
            import pdb; pdb.set_trace()
        else:
            notifier.fatal(__package__ + ' encountered an error',
                           str(err) + '\n' + traceback.format_exc())
            tracer.stop('Stopping due to error')
            controller.stop()
    else:
        tracer.stop('Done')
        controller.stop()



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
