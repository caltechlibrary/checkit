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

import os
import os.path as path
import plac
import sys
import time
from   threading import Thread

import checkit
from checkit.access import AccessHandlerGUI, AccessHandlerCLI
from checkit.config import Config
from checkit.control import CheckitControlGUI, CheckitControlCLI
from checkit.debug import set_debug, log
from checkit.email import Mailer
from checkit.exceptions import *
from checkit.files import module_path
from checkit.google_sheet import Google
from checkit.messages import MessageHandlerGUI, MessageHandlerCLI
from checkit.network import network_available, net
from checkit.progress import ProgressIndicatorGUI, ProgressIndicatorCLI
from checkit.records import records_diff, records_filter
from checkit.tind import Tind


# Main program.
# ......................................................................

@plac.annotations(
    no_color   = ('do not color-code terminal output',                  'flag',   'C'),
    no_gui     = ('do not start the GUI interface (default: do)',       'flag',   'G'),
    input_csv  = ('input file containing list of barcodes',             'option', 'i'),
    no_keyring = ('do not store credentials in a keyring service',      'flag',   'K'),
    output_csv = ('output file where results should be written as CSV', 'option', 'o'),
    pswd       = ('Caltech access user password',                       'option', 'p'),
    reset_keys = ('reset user and password used',                       'flag',   'R'),
    user       = ('Caltech access user name',                           'option', 'u'),
    version    = ('print version info and exit',                        'flag',   'V'),
    debug      = ('turn on debugging',                                  'flag',   '@'),
)

def main(no_color = False, no_gui = False, input_csv = 'I', no_keyring = False,
         output_csv = 'O', pswd = 'P', reset_keys = False, user = 'U',
         version = False, debug = False):
    '''Check It!'''

    # Initial setup -----------------------------------------------------------

    # Our defaults are to do things like color the output, which means the
    # command line flags make more sense as negated values (e.g., "no-color").
    # However, dealing with negated variables in our code is confusing, so:
    use_color   = not no_color
    use_keyring = not no_keyring
    use_gui     = not no_gui

    # Preprocess arguments and handle early exits -----------------------------

    if debug:
        set_debug(True)
    if version:
        print_version()
        sys.exit()

    if input_csv == 'I' and use_gui:
        input_csv = file_to_open(splitit.__title__ + ': open input CSV file',
                                 wildcard = 'CSV file (*.csv)|*.csv|Any file (*.*)|*.*')
        if input_csv is None:
            exit('Quitting.')
    else:
        exit(say.error_text('Must supply input file using -i. {}'.format(hint)))
    if not readable(input_csv):
        exit(say.error_text('Cannot read file: {}'.format(input_csv)))
    elif not is_csv(input_csv):
        exit(say.error_text('File does not appear to contain CSV: {}'.format(input_csv)))

    if output_csv == 'O' and use_gui:
        output_csv = file_to_save(splitit.__title__ + ': save output file')
        if output_csv is None:
            exit('Quitting.')
    else:
        exit(say.error_text('Must supply output file using -o. {}'.format(hint)))
    if path.exists(output_csv):
        if file_in_use(output_csv):
            exit(say.error_text('File is open by another application: {}'.format(output_csv)))
        elif not writable(output_csv):
            exit(say.error_text('Unable to write to file: {}'.format(output_csv)))
    else:
        dest_dir = path.dirname(output_csv) or os.getcwd()
        if not writable(dest_dir):
            exit(say.error_text('Cannot write to folder: {}'.format(dest_dir)))

    if user == 'U':
        user = None
    if pswd == 'P':
        pswd = None

    # Do the real work --------------------------------------------------------

    if use_gui:
        controller = CheckitControlGUI()
        accesser   = AccessHandlerGUI(user, pswd)
        notifier   = MessageHandlerGUI()
        tracer     = ProgressIndicatorGUI()
    else:
        controller = CheckitControlCLI()
        accesser   = AccessHandlerCLI(user, pswd, use_keyring, reset_keys)
        notifier   = MessageHandlerCLI(use_color)
        tracer     = ProgressIndicatorCLI(use_color)

    # Start the worker thread.
    if __debug__: log('starting main body thread')
    controller.start(MainBody(input_csv, output_csv,
                              controller, accesser, notifier, tracer, debug))


class MainBody(Thread):
    '''Main body of Check It! implemented as a Python thread.'''

    def __init__(self, view_sheet, send_mail, debug,
                 controller, accesser, notifier, tracer):
        '''Initializes main thread object but does not start the thread.'''
        Thread.__init__(self, name = "MainBody")
        self._view_sheet = view_sheet
        self._send_mail  = send_mail
        self._debug      = debug
        self._controller = controller
        self._tracer     = tracer
        self._accesser   = accesser
        self._notifier   = notifier
        if controller.is_gui:
            # Only make this a daemon thread when using the GUI; for CLI, it
            # must not be a daemon thread or else Check It! exits immediately.
            self.daemon = True


    def run(self):
        # Set shortcut variables for better code readability below.
        view_sheet = self._view_sheet
        send_mail  = self._send_mail
        debug      = self._debug
        controller = self._controller
        accesser   = self._accesser
        notifier   = self._notifier
        tracer     = self._tracer

        # Preliminary sanity checks.  Do this here because we need the notifier
        # object to be initialized based on whether we're using GUI or CLI.
        tracer.start('Performing initial checks')
        if not network_available():
            notifier.fatal('No network connection.')

        # Let's do this thing.
        try:
            config      = Config(path.join(module_path(), "checkit.ini"))
            tind        = Tind(accesser, notifier, tracer)
            google      = Google(accesser, notifier, tracer)

            sid         = config.get('checkit', 'spreadsheet_id')
            mail_server = config.get('checkit', 'mail_server')
            mail_port   = config.get('checkit', 'mail_port')
            recipients  = config.get('checkit', 'mail_recipients')

            # Get the data from TIND and the Google spreadsheet of lost
            # items, we look at the two first tabs.  The tab lookup is done
            # by position, NOT by name; the names of the tabs make no
            # difference.  Check It! assumes that the first tab is the current
            # NOS list and the second tab is a list of historical records,
            # but it doesn't care what the cut-off is between the tabs.  It
            # merely gathers the records from both tabs.
            tind_records = tind.records()
            google_records = google.records(sid, tab = 0) + google.records(sid, tab = 1)

            # Figure out what's new.
            tracer.update('Comparing TIND records to our spreadsheet')
            new_records = records_diff(google_records, tind_records)
            num_new = len(new_records)
            tracer.update('Found {} new records'.format(num_new))

            # Update the Google spreadsheet with new records.
            if num_new > 0:
                new_records = sorted(new_records, key = lambda r: r.date_requested)
                tracer.update('Updating Google spreadsheet')
                google.update(sid, new_records)

            # Open the spreadsheet, if requested.
            if isinstance(notifier, MessageHandlerGUI):
                if notifier.yes_no('Open the tracking spreadsheet?'):
                    tracer.update('Opening the Google spreadsheet')
                    google.open(sid)
            elif view_sheet:
                tracer.update('Opening the Google spreadsheet')
                google.open(sid)

            # Send mail, if requested.
            if send_mail and num_new > 0:
                tracer.update('Sending mail')
                subject  = 'Check It! reports {} lost item{}'.format(
                    num_new, 's' if num_new > 1 else '')
                body     = email_body(new_records, google.spreadsheet_url(sid))
                sender   = accesser.user + '@caltech.edu'
                password = accesser.password
                mailer   = Mailer(mail_server, mail_port)
                mailer.send(sender, password, recipients, subject, body)

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
                notifier.fatal(checkit.__title__ + ' encountered an error',
                               str(err) + '\n' + traceback.format_exc())
                tracer.stop('Stopping due to error')
                controller.stop()
        else:
            tracer.stop('Done')
            controller.stop()


# Miscellaneous utilities.
# .............................................................................

def print_version():
    print('{} version {}'.format(checkit.__title__, checkit.__version__))
    print('Author: {}'.format(checkit.__author__))
    print('URL: {}'.format(checkit.__url__))
    print('License: {}'.format(checkit.__license__))


# Main entry point.
# ......................................................................

# On windows, we want plac to use slash intead of hyphen for cmd-line options.
if sys.platform.startswith('win'):
    main.prefix_chars = '/'

# The following allows users to invoke this using "python3 -m handprint".
if __name__ == '__main__':
    plac.call(main)


# For Emacs users
# ......................................................................
# Local Variables:
# mode: python
# python-indent-offset: 4
# End:
