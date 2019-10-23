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
from .ui import inform, warn, alert, alert_fatal, file_selection


# Global constants.
# .............................................................................

# This maps record fields to the columns we want to put them in the output CSV.
# If the field is not listed here, it's not written out

_COL_INDEX = {
    'item_barcode'         : 0,
    'item_loan_status'     : 1,
    'item_call_number'     : 2,
    'item_copy_number'     : 3,
    'item_location_code'   : 4,
    'item_location_name'   : 5,
    'item_tind_id'         : 6,
    'item_type'            : 7,
    'holdings_total'       : 8,
}


# Class definitions.
# .............................................................................

class MainBody(Thread):
    '''Main body of Check It! implemented as a Python thread.'''

    def __init__(self, infile, outfile, access):
        '''Initializes main body thread object but does not start the thread.'''
        Thread.__init__(self, name = "MainBody")

        # We expose one attribute, "exception", that callers can use to find
        # out if the thread finished normally or with an exception.
        self.exception = None

        # The rest of this sets internal variables used by other methods.
        self._infile  = infile
        self._outfile = outfile
        self._access  = access


    def run(self):
        '''Run the main body.'''
        # In normal operation, this method returns after things are done and
        # leaves it to the user to exit the application via the control GUI.
        # If exceptions occur, we capture the stack context for the caller.
        try:
            self._do_main_work()
        except (KeyboardInterrupt, UserCancelled) as ex:
            if __debug__: log('got {} exception', type(ex).__name__)
            inform('User cancelled operation -- stopping.')
            return
        except Exception as ex:
            if __debug__: log('exception in main body: {}', str(ex))
            self.exception = sys.exc_info()
            details = 'An exception occurred in {}: {}'.format(__package__, str(ex))
            alert_fatal('Error occurred during execution', details = details)
            return
        if __debug__: log('run() finished')


    def stop(self):
        '''Stop the main body thread.'''
        if __debug__: log('stopping main body thread')
        # Nothing to do for the current application.
        pass


    def _do_main_work(self):
        # Set shortcut variables for better code readability below.
        infile  = self._infile
        outfile = self._outfile

        # Do basic sanity checks ----------------------------------------------

        inform('Doing initial checks ...')
        if not network_available():
            raise NetworkFailure('No network connection.')

        # Read the input file -------------------------------------------------

        if not infile:
            inform('Asking user for input file ...')
            infile = file_selection('open', 'file of barcodes', 'CSV file|*.csv|Any file|*.*')
        if not infile:
            alert('No input file')
            return
        if not readable(infile):
            alert('Cannot read file: {}'.format(infile))
            return
        if not self._file_contains_barcodes(infile):
            details = 'File does not appear to contain barcodes: {}'.format(infile)
            alert('Bad input file', details = details)
            return

        barcode_list = []
        inform('Reading file {} ...', infile)
        with open(infile, mode="r") as f:
            barcode_list = [row[0] for row in csv.reader(f) if row and row[0].isdigit()]

        # Query TIND for the records matching the barcodes --------------------

        inform('Contacting TIND to get records ...')
        try:
            tind = Tind(self._access)
            records = tind.records(barcode_list)
        except (ServiceFailure, NetworkFailure) as ex:
            alert_fatal("Can't connect to TIND -- try later", details = str(ex))
            return

        # The results may not contain a record for all barcodes, and the input
        # list may have duplicates.  The following puts the records in the
        # same order as our original barcode_list & puts None for missing
        # records.  The loop is O(n^2), but our lists are short, so no biggie.

        records_sorted = []
        for barcode in barcode_list:
            # FIXME: will end up printing wrong barcode
            rec = next((r for r in records if barcode in r.holdings_barcodes), None)
            records_sorted.append(rec)

        # Write the output ----------------------------------------------------

        if not outfile:
            inform('Asking user for output file ...')
            outfile = file_selection('save', 'output file')
        if not outfile:
            alert('No output file specified')
            return
        if path.exists(outfile):
            rename_existing(outfile)
        if file_in_use(outfile):
            details = '{} appears to be open in another program'.format(outfile)
            alert('Cannot write output file', details = details)
            return
        if path.exists(outfile) and not writable(outfile):
            details = 'You may not have write permissions to {} '.format(outfile)
            alert('Cannot write output file', details = details)
            return

        if not outfile.endswith('.csv'):
            outfile += '.csv'

        inform('Writing file {} ...', outfile)
        with open(outfile, 'w') as f:
            writer = csv.writer(f, delimiter = ',')
            writer.writerow(self._column_headings_list())
            for idx, rec in enumerate(records_sorted):
                if rec is not None:
                    writer.writerow(self._row_for_record(rec))
                    if rec.holdings_total > 1:
                        for other_rec in (rec.copies_not_on_shelf or []):
                            if other_rec.item_barcode != rec.item_barcode:
                                writer.writerow(self._row_for_record(other_rec))
                else:
                    writer.writerow(self._blank_row_for_barcode(barcode_list[idx]))
        inform('Finished writing output.')


    def _column_headings_list(self):
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


    def _file_contains_barcodes(self, input_file):
        with open(input_file, 'r') as f:
            line = f.readline().strip().strip(',')
            # First line of a CSV file might be column headers, so skip it.
            if not line.isdigit() and not line.startswith('nobarcode'):
                line = f.readline().strip().strip(',')
            return line.isdigit() or line.startswith('nobarcode')
