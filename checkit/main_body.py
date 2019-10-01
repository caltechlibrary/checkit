'''
main_body.py: main body logic for this application

Authors
-------

Michael Hucka <mhucka@caltech.edu> -- Caltech Library

Copyright
---------

Copyright (c) 2018-2019 by the California Institute of Technology.  This code
is open-source software released under a 3-clause BSD license.  Please see the
file "LICENSE" for more information.
'''

import csv
import os
import os.path as path
import sys
from   threading import Thread

from .debug import log
from .exceptions import *
from .files import readable, writable, file_in_use, rename_existing
from .network import network_available
from .tind import Tind, TindRecord


# Global constants.
# .............................................................................

# This maps record fields to the columns we want to put them in the output CSV.
# If the field is not listed here, it's not written out

_COL_INDEX = {
    'item_barcode'         : 0,
    'item_loan_status'     : 1,
    'item_call_number'     : 2,
    'item_copy_number'     : 3,
    'item_location_name'   : 4,
    'item_tind_id'         : 5,
    'item_type'            : 6,
    'item_location_code'   : 7,
}


# Class definitions.
# .............................................................................

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
            notifier.inform('Welcome to ' + controller.app_name)
            self._do_main_work()
            notifier.inform('Done.')
        except Exception as ex:
            if __debug__: log('exception in main body')
            self.exception = sys.exc_info()
            controller.quit()


    def stop(self):
        '''Stop the main body thread.'''
        if __debug__: log('stopping main body thread')
        # Nothing to do for the current application.
        pass


    def _do_main_work(self):
        # Set shortcut variables for better code readability below.
        infile     = self._infile
        outfile    = self._outfile
        accessor   = self._accessor
        controller = self._controller
        notifier   = self._notifier

        # Do basic sanity checks ----------------------------------------------

        self._notifier.inform('Doing initial checks')
        if not network_available():
            raise NetworkFailure('No network connection.')

        # Get input file ------------------------------------------

        if not infile and controller.is_gui:
            notifier.inform('Asking user for input file')
            infile = controller.open_file('Open barcode file', 'CSV file|*.csv|Any file|*.*')
        if not infile:
            notifier.alert('No input file')
            return
        if not readable(infile):
            notifier.alert('Cannot read file: {}'.format(infile))
            return

        # Read the input file and query TIND ----------------------------------

        notifier.inform('Reading file {}', infile)
        barcode_list = []
        with open(infile, mode="r") as f:
            barcode_list = [row[0] for row in csv.reader(f) if row]

        tind = Tind(accessor, notifier)
        records = tind.records(barcode_list)

        # Write the output ----------------------------------------------------

        if not outfile and controller.is_gui:
            notifier.inform('Asking user for output file')
            outfile = controller.save_file('Output destination file')
        if not outfile:
            notifier.alert('No output file specified')
            return
        if path.exists(outfile):
            rename_existing(outfile)
        if file_in_use(outfile):
            details = '{} appears to be open in another program'.format(outfile)
            notifier.alert('Cannot write output file', details = details)
            return
        if path.exists(outfile) and not writable(outfile):
            details = 'You may not have write permissions to {} '.format(outfile)
            notifier.alert('Cannot write output file', details = details)
            return

        if not outfile.endswith('.csv'):
            outfile += '.csv'

        notifier.inform('Writing file {}', outfile)
        found_barcodes = [r.item_barcode for r in records]
        with open(outfile, 'w') as f:
            writer = csv.writer(f, delimiter = ',')
            writer.writerow(self._column_titles_list())
            for rec in records:
                writer.writerow(self._row_for_record(rec))
            # Write markers for barcodes not returned by TIND.
            missing = [x for x in barcode_list if x not in found_barcodes]
            for barcode in missing:
                writer.writerow(self._blank_row_for_barcode(barcode))


    def _column_titles_list(self):
        # Need to be careful to put them in the order that is defined by the
        # values in _COL_INDEX.  Don't just do a simple list comprehension.
        titles_list = ['']*len(_COL_INDEX)
        for field in _COL_INDEX.keys():
            titles_list[_COL_INDEX[field]] = TindRecord.field_title(field)
        return titles_list


    def _row_for_record(self, record):
        row = ['']*len(_COL_INDEX)
        for field in _COL_INDEX.keys():
            row[_COL_INDEX[field]] = getattr(record, field)
        return row


    def _blank_row_for_barcode(self, barcode):
        row = [barcode] + ['n/a']*(len(_COL_INDEX) - 1)
        return row
