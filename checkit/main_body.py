import csv
import os
import os.path as path
import sys
from   threading import Thread

from   pubsub import pub
import wx


from .debug import log
from .exceptions import *
from .files import readable, writable, file_in_use, rename_existing
from .network import network_available
from .tind import Tind


class MainBody(Thread):
    '''Main body of Check It! implemented as a Python thread.'''

    def __init__(self, infile, outfile, controller, accessor, notifier):
        '''Initializes main body thread object but does not start the thread.'''
        Thread.__init__(self, name = "MainBody")

        # Make this a daemon thread, but only when using the GUI; for CLI, it
        # must not be a daemon thread or else the program exits immediately.
        if controller.is_gui:
            self.daemon = True

        # We expose one attribute, "exception", that callers can use to find
        # out if the thread finished normally or with an exception.
        self.exception = None

        # The rest of this sets internal variables used by other methods.
        self._infile      = infile
        self._outfile     = outfile
        self._controller  = controller
        self._accessor    = accessor
        self._notifier    = notifier


    def run(self):
        '''Run the main body.'''
        # Set shortcut variables for better code readability below.
        controller = self._controller
        notifier   = self._notifier

        # In normal operation, this method returns after things are done and
        # leaves it to the user to exit the application via the control GUI.
        # If exceptions occur, we capture the stack context for the caller
        # to interpret, and force the controller to quit.
        try:
            notifier.info('Welcome to ' + controller.app_name)
            self._run()
            notifier.info('Done.')
        except Exception as ex:
            if __debug__: log('exception in main body')
            self.exception = sys.exc_info()
            controller.quit()


    def stop(self):
        '''Stop the main body thread.'''
        if __debug__: log('stopping main body thread')
        # Nothing to do for the current application.
        pass


    def _run(self):
        # Set shortcut variables for better code readability below.
        infile     = self._infile
        outfile    = self._outfile
        accessor   = self._accessor
        controller = self._controller
        notifier   = self._notifier

        # Do basic sanity checks ----------------------------------------------

        self._notifier.info('Performing initial checks')
        if not network_available():
            self._notifier.fatal('No network connection.')

        # Get input file ------------------------------------------

        if not infile and controller.is_gui:
            notifier.info('Asking user for input file')
            infile = controller.open_file('Open barcode file', 'CSV file|*.csv|Any file|*.*')
        if not infile:
            notifier.error('No input file')
            return
        if not readable(infile):
            notifier.error('Cannot read file: {}'.format(infile))
            return

        # Read the input file and query TIND ----------------------------------

        notifier.info('Reading file {}', infile)
        barcode_list = []
        with open(infile, mode="r") as f:
            barcode_list = [row[0] for row in csv.reader(f)]

        tind = Tind(accessor, notifier)
        records = tind.records(barcode_list)

        # Write the output ----------------------------------------------------

        if not outfile and controller.is_gui:
            notifier.info('Asking user for output file')
            outfile = controller.save_file('Output destination file')
        if not outfile:
            notifier.error('No output file specified')
            return
        if path.exists(outfile):
            rename_existing(outfile)
        if file_in_use(outfile):
            details = '{} appears to be open in another program'.format(outfile)
            notifier.error('Cannot write output file', details = details)
            return
        if path.exists(outfile) and not writable(outfile):
            details = 'You may not have write permissions to {} '.format(outfile)
            notifier.error('Cannot write output file', details = details)
            return

        if not outfile.endswith('.csv'):
            outfile += '.csv'

        import pdb; pdb.set_trace()
        with open(outfile, 'wb') as f:
            writer = csv.writer(f, delimiter = ',')
            for rec in records:
                writer.writerow(...)
