import os
import os.path as path
import sys
from   threading import Thread

from   pubsub import pub
import wx


from .debug import log
from .exceptions import *
from .files import readable, writable, file_in_use
from .network import network_available


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
            self.main_body()
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


    def main_body(self):
        '''The main body.'''

        # Set shortcut variables for better code readability below.
        infile     = self._infile
        outfile    = self._outfile
        controller = self._controller
        accessor   = self._accessor
        notifier   = self._notifier

        # Preliminary sanity checks -------------------------------------------

        notifier.info('Performing initial checks')

        if not network_available():
            notifier.fatal('No network connection.')
            return

        if not infile and controller.is_gui:
            notifier.info('Asking user for input file')
            infile = controller.open_file('Open barcode file', 'CSV file|*.csv|Any file|*.*')
        if not infile:
            notifier.warn('No input file -- nothing to do')
            return
        if not readable(infile):
            notifier.warn('Cannot read file: {}'.format(infile))
            return

        if not outfile and controller.is_gui:
            notifier.info('Asking user for output file')
            outfile = controller.save_file('Output destination file')
        if not outfile:
            notifier.info('No output file specified -- cannot continue')
            return
        if path.exists(outfile):
            if file_in_use(outfile):
                notifier.info('File is open by another application: {}'.format(outfile))
                return
            elif not writable(outfile):
                notifier.info('Unable to write to file: {}'.format(outfile))
                return
        else:
            dest_dir = path.dirname(outfile) or os.getcwd()
            if not writable(dest_dir):
                notifier.info('Cannot write to folder: {}'.format(dest_dir))
                return

        # Main work -----------------------------------------------------------
