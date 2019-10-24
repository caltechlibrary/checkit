'''
records.py: base record class for holding data from TIND

Authors
-------

Michael Hucka <mhucka@caltech.edu> -- Caltech Library

Copyright
---------

Copyright (c) 2018-2019 by the California Institute of Technology.  This code
is open-source software released under a 3-clause BSD license.  Please see the
file "LICENSE" for more information.
'''

from datetime import datetime

from .debug import log


# Global constants.
# .............................................................................

_ATTRIBUTE_TITLES = {
    'item_title'         : 'Title',
    'item_author'        : 'Author',
    'item_type'          : 'Item type',
    'item_call_number'   : 'Call number',
    'item_copy_number'   : 'Copy number',
    'item_tind_id'       : 'TIND id',
    'item_barcode'       : 'Barcode',
    'item_details_url'   : 'Details page',
    'item_record_url'    : 'Item record page',
    'item_location_name' : 'Location name',
    'item_location_code' : 'Location code',
    'item_holds_count'   : 'Hold requests',
    'item_loan_status'   : 'Loan status',
    'item_loan_period'   : 'Loan period',
    'date_created'       : 'Date created',
    'date_modified'      : 'Date modified',
    'requester_name'     : 'Requester name',
    'requester_email'    : 'Requester email',
    'requester_type'     : 'Patron type',
    'requester_url'      : 'Requester details page',
    'date_requested'     : 'Date requested',
    'holdings_total'     : 'Total holdings'
}
'''Mapping of Python record object attributes to human-readable short
descriptive titles for the attributes.'''



# Class definitions.
# .............................................................................

class BaseRecord(object):
    '''Base class for records describing an item in TIND.io.  Note that the
    field names in this record object do not match exactly the field names in
    TIND; the reasons include (1) we add some additional non-item info to these
    records in subclasses, so naming the fields more clearly here makes coding
    easier later, and (2) some of the TIND field names are IMHO ambiguous, so
    I tried to name things in a way that made meaning more clear.  Also, not
    all the fields available in TIND are represented here because Caltech
    Library either doesn't use them or they always seem to be blank.'''

    def __init__(self):
        # The following map to the json objects returned by TIND ajax calls.
        self.item_title = ''                   # title
        self.item_author = ''                  # extracted from title field
        self.item_type = ''                    # item_type
        self.item_call_number = ''             # call_no
        self.item_copy_number = ''             # description
        self.item_tind_id = ''                 # id_bibrec
        self.item_barcode = ''                 # barcode
        self.item_details_url = ''             # links.barcode
        self.item_record_url = ''              # links.title
        self.item_location_name = ''           # location_name
        self.item_location_code = ''           # location_code
        self.item_holds_count = ''             # number_of_requests
        self.item_loan_status = ''             # status
        self.item_loan_period = ''             # loan_period

        self.date_created = ''                 # creation_date
        self.date_modified = ''                # modification_date


    def __repr__(self):
        return '<{} {}>'.format(self.__class__.__name__, self.item_tind_id)


    def __hash__(self):
        return hash(self.item_barcode + self.requester_name + self.date_requested)


    def __eq__(self, other):
        return (self.item_barcode == other.item_barcode
                and self.requester_name == other.requester_name
                and self.date_requested == other.date_requested)


    def __ne__(self, other):
        return not self.__eq__(other)


    def __gt__(self, other):
        return not __le__(self, other)


    def __le__(self, other):
        return repr(self) <= repr(other)


    def __ge__(self, other):
        return not __lt__(self, other)


    def __lt__(self, other):
        return repr(self) < repr(other)


    @classmethod
    def field_title(cls, name):
        '''Given the name of a field, return a short human-readable title that
        describes its meaning.'''
        if name in _ATTRIBUTE_TITLES:
            return _ATTRIBUTE_TITLES[name]
