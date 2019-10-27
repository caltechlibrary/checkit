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

from   collections import OrderedDict
from   copy import deepcopy
import csv
import os
import os.path as path
import sys
from   threading import Thread

from .debug import log
from .exceptions import *
from .files import readable, writable, file_in_use, rename_existing
from .network import network_available
from .record import ItemRecord
from .tind import Tind
from .ui import inform, warn, alert, alert_fatal, file_selection


# Global constants.
# .............................................................................
# The order of the list of output columns in _OUTPUT_COLUMNS determines the
# order of the columns written in the output spreadsheet.

OUTPUT_COLUMNS = OrderedDict([
    ('Barcode',        lambda record, copies: record.item_barcode),
    ('Status',         lambda record, copies: record.item_status),
    ('Call number',    lambda record, copies: record.item_call_number),
    ('Copy number',    lambda record, copies: record.item_copy_number),
    ('Location code',  lambda record, copies: record.item_location_code),
    ('Location name',  lambda record, copies: record.item_location_name),
    ('TIND id',        lambda record, copies: record.item_tind_id),
    ('Item type',      lambda record, copies: record.item_type),
    ('Holdings total', lambda record, copies: len(copies))
])
'''
Ordered dictionary of the fields to write out in the CSV output file.
The keys are the column titles, and the values are functions that are
handed two arguments: the current record, and a dictionary of Holding items
representing the copies of that item held in the Caltech Libraries.
'''


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
        if not file_contains_barcodes(infile):
            details = 'File does not appear to contain barcodes: {}'.format(infile)
            alert('Bad input file', details = details)
            return

        barcode_list = []
        inform('Reading file {} ...', infile)
        with open(infile, mode="r") as f:
            barcode_list = [row[0] for row in csv.reader(f) if is_barcode(row[0])]

        # Query TIND for the records matching the barcodes --------------------

        inform('Contacting TIND to get records ...')
        try:
            tind = Tind(self._access)
            records = tind.records(barcode_list)
            holdings = tind.holdings(records)
        except (ServiceFailure, NetworkFailure) as ex:
            alert_fatal("Can't connect to TIND -- try later", details = str(ex))
            return

        # The results may not contain a record for all barcodes, and the input
        # list may have duplicates.  The following puts the records in the
        # same order as our original barcode_list & puts None for missing
        # records.  The loop is O(n^2), but our lists are short, so no biggie.
        records_sorted = []
        for barcode in barcode_list:
            rec = next((r for r in records if r.item_barcode == barcode), None)
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
            sheet = csv.writer(f, delimiter = ',')
            sheet.writerow(OUTPUT_COLUMNS.keys())
            for idx, rec in enumerate(records_sorted):
                if rec is None:
                    sheet.writerow(row_for_missing(barcode_list[idx]))
                    continue
                copies = holdings.get(rec, [])
                sheet.writerow(row_for_record(rec, copies))
                others = [c for c in copies if c.location == rec.item_location_name
                          and c.barcode != rec.item_barcode and c.status != 'on shelf']
                for held in others:
                    other = deepcopy(rec)
                    other.item_barcode = held.barcode
                    other.status = held.status
                    sheet.writerow(row_for_record(other, copies))
        inform('Finished writing output.')


# Miscellaneous utility functions
# .............................................................................

def is_barcode(text):
    return text and (text.isdigit() or text.startswith('nobarcode'))


def file_contains_barcodes(input_file):
    with open(input_file, 'r') as f:
        line = f.readline().strip().strip(',')
        # First line of a CSV file might be column headers, so skip it.
        if not line.isdigit() and not line.startswith('nobarcode'):
            line = f.readline().strip().strip(',')
        return is_barcode(line)


def row_for_record(record, copies):
    return [value(record, copies) for value in OUTPUT_COLUMNS.values()]


def row_for_missing(barcode):
    '''Returns a list with the barcode and 'n/a' for all the columns.'''
    return [barcode] + ['n/a']*(len(OUTPUT_COLUMNS) - 1)
