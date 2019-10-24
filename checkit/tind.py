'''
tind.py: code for interacting with Caltech.TIND.io

Authors
-------

Michael Hucka <mhucka@caltech.edu> -- Caltech Library

Copyright
---------

Copyright (c) 2018-2019 by the California Institute of Technology.  This code
is open-source software released under a 3-clause BSD license.  Please see the
file "LICENSE" for more information.
'''

from   iteration_utilities import grouper
import json
from   nameparser import HumanName
import re
import requests
from lxml import html
from bs4 import BeautifulSoup

from .debug import log
from .exceptions import *
from .network import net
from .records import BaseRecord
from .ui import inform, warn, alert, alert_fatal, yes_reply


# Global constants.
# .............................................................................

_USER_AGENT_STRING = 'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko)'
'''
Using a user-agent string that identifies a browser seems to be important
in order to make Shibboleth or TIND return results.
'''

_SHIBBED_TIND_URL = 'https://caltech.tind.io/youraccount/shibboleth?referer=https%3A//caltech.tind.io/%3F'
'''
URL to start the Shibboleth authentication process for the Caltech TIND page.
'''

_SSO_URL = 'https://idp.caltech.edu/idp/profile/SAML2/Redirect/SSO'
'''
Root URL for the Caltech SAML steps.
'''

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
descriptive titles for the attributes.  This is used for things like writing
spreadsheet column titles.'''


# Class definitions.
# .............................................................................

class TindRecord(BaseRecord):
    '''Class to store structured representations of a TIND request.'''

    # Cache of objects created, indexed by tind id.  Useful because we may
    # end up trying to get the same record in different ways. This is a
    # class-level variable so that the data is shared across records.
    _cache = {}

    # Dictionary mapping holdings info to tind id's.  Useful because our inputs
    # are barcodes, and multiple barcodes may represent copies of the same tind
    # item, which can lead to trying to look up the same info more than once.
    # This is a class-level variable so that the data is shared across records.
    _holdings_data = {}


    def __new__(cls, json_dict, tind_interface, session):
        '''json_record = single 'data' record from the raw json returned by
        the TIND.io ajax call.  tind_interface = an instance of the Tind
        class.  session = a requests session object.
        '''
        tind_id = json_dict['id_bibrec']
        if tind_id not in cls._cache:
            if __debug__: log('creating new TindRecord for {}', tind_id)
            cls._cache[tind_id] = super(TindRecord, cls).__new__(cls)
        else:
            if __debug__: log('returning cached object for {}', tind_id)
        return cls._cache[tind_id]


    def __init__(self, json_dict, tind_interface, session):
        tind_id = json_dict['id_bibrec']
        if tind_id in self._cache and hasattr(self._cache[tind_id], '_initialized'):
            return

        if __debug__: log('initializing TindRecord for {}', tind_id)
        super().__init__()
        self._initialized = True

        # We add some additional attributes on demand.  They're obtained via
        # HTML scraping of TIND pages.  Setting a field here initially to None
        # (as opposed to '') is used as a marker that it hasn't been set.
        self._requester_name      = None
        self._requester_email     = None
        self._requester_type      = None
        self._requester_url       = None
        self._date_requested      = None

        # The following hold data or are additional attributes
        self._orig_data           = json_dict
        self._tind                = tind_interface
        self._session             = session
        self._loan_data           = None
        self._patron_data         = None
        self._filled              = False
        self._copies_not_on_shelf = None

        # The rest is initialization of values for a record.
        self.item_tind_id       = tind_id
        self.item_call_number   = json_dict['call_no']
        self.item_copy_number   = json_dict['description']
        self.item_location_name = json_dict['location_name']
        self.item_location_code = json_dict['location_code']
        self.item_loan_status   = json_dict['status']
        self.item_loan_period   = json_dict['loan_period']
        self.item_barcode       = json_dict['barcode']
        self.item_type          = json_dict['item_type']
        self.holds_count        = json_dict['number_of_requests']
        self.date_created       = json_dict['creation_date']
        self.date_modified      = json_dict['modification_date']

        # Additional attributes
        self.holdings_total     = 1
        self.holdings_barcodes  = []

        # The 'title' field actually contains author too, so pull it all out.
        title_text = json_dict['title']
        author_text = ''
        if title_text.find(' / ') > 0:
            start = title_text.find(' / ')
            self.item_title = title_text[:start].strip()
            author_text = title_text[start + 3:].strip()
        elif title_text.find('[by]') > 0:
            start = title_text.find('[by]')
            self.item_title = title_text[:start].strip()
            author_text = title_text[start + 5:].strip()
        elif title_text.rfind(', by') > 0:
            start = title_text.rfind(', by')
            self.item_title = title_text[:start].strip()
            author_text = title_text[start + 5:].strip()
        else:
            self.item_title = title_text
        if author_text:
            self.item_author = first_author(author_text)

        self.item_record_url    = 'https://caltech.tind.io/record/' + str(tind_id)
        self.item_details_url   = 'https://caltech.tind.io' + json_dict['links']['barcode']

        # We always write total holdings for each item, so we may as well
        # get the data now.
        if tind_id in self._holdings_data:
            data = self._holdings_data[tind_id]
        else:
            self._holdings_data[tind_id] = self._tind.holdings(tind_id, session)
            data = self._holdings_data[tind_id]
        soup = BeautifulSoup(data or '', features='lxml')
        tables = soup.body.find_all('table')
        if len(tables) >= 2:
            rows = tables[1].find_all('tr')
            # Subtract one because of the heading row.
            self.holdings_total = len(rows) - 1 if rows else 0
            for row in rows[1:]:
                columns = row.find_all('td')
                self.holdings_barcodes.append(barcode_from_link(columns[0].input))
        if __debug__: log('total holdings for {} = {}', tind_id, self.holdings_total)


    # Note: in the following property handlers setters, the stored value has
    # to be in a property with a DIFFERENT NAME (here, with a leading
    # underscore) to avoid infinite recursion.

    @property
    def copies_not_on_shelf(self):
        # Nos = "not on shelf" (lost or on loan)
        if self._copies_not_on_shelf == None:
            self._fill_copies_not_on_shelf()
        return self._copies_not_on_shelf


    @copies_not_on_shelf.setter
    def copies_not_on_shelf(self, value):
        self._copies_not_on_shelf = value


    @property
    def requester_name(self):
        if self._requester_name == None:
            self._fill_requester_info()
        return self._requester_name


    @requester_name.setter
    def requester_name(self, value):
        self._requester_name = value


    @property
    def requester_email(self):
        if self._requester_email == None:
            self._fill_requester_info()
        return self._requester_email


    @requester_email.setter
    def requester_email(self, value):
        self._requester_email = value


    @property
    def requester_url(self):
        if self._requester_url == None:
            self._fill_requester_info()
        return self._requester_url


    @requester_url.setter
    def requester_url(self, value):
        self._requester_url = value


    @property
    def requester_type(self):
        if self._requester_type == None:
            self._fill_requester_info()
        return self._requester_type


    @requester_type.setter
    def requester_type(self, value):
        self._requester_type = value


    @property
    def date_requested(self):
        if self._date_requested == None:
            self._fill_requester_info()
        return self._date_requested


    @date_requested.setter
    def date_requested(self, value):
        self._date_requested = value


    def as_string(self):
        attr_value_pairs = []
        for attr in dir(self):
            if attr.startswith('item_') or attr.startswith('date_'):
                attr_value_pairs.append(attr + '="' + str(getattr(self, attr)) + '"')
        c_name = self.__class__.__name__
        this_id = str(self.item_tind_id)
        return '<{} {} {}>'.format(c_name, this_id, ' '.join(attr_value_pairs))


    def _fill_requester_info(self):
        if self._filled:
            return
        # Though we haven't done anything yet, we have to prevent loops due
        # to incomplete data, so we don't wait until the end to set this.
        self._filled = True

        # Get what we can from the loan details page.
        loans = self._tind.loan_details(self.item_tind_id, self._session)
        self._fill_loan_details(loans)

        # Get what we can from the loan details page.
        if self._requester_name:
            patron = self._tind.patron_details(self._requester_name,
                                               self._requester_url, self._session)
            self._fill_patron_details(patron)
        else:
            if __debug__: log('no requester for {}', self.item_tind_id)


    def _fill_loan_details(self, loans):
        # If we can't find values, then we leave the following.
        self._requester_name = ''
        self._requester_url = ''
        self._date_requested = ''

        if loans:
            # Save the loans page in case we need it later.
            self._loan_data = loans
            # Parse it and pull out what we can.
            soup = BeautifulSoup(loans, features='lxml')
            tables = soup.body.find_all('table')
            if len(tables) < 2:
                if __debug__: log('no loan details => no requests')
                return

            # After the header row, the table contains a list of borrowers for
            # the item.  Since a given item may have multiple copies, it's
            # possible for a copy other than the lost one to have a loan on it.
            # Therefore, we start from the bottom of the table and work our
            # way backwards, comparing bar codes, to see if the lost copy has
            # a loan request on it.
            borrower_table = tables[1]
            for row in borrower_table.find_all('tr')[1:]:
                cells = row.find_all('td')
                if len(cells) < 10:
                    if __debug__: log('loan details missing expected table cells')
                    return
                barcode = cells[5].get_text()
                if barcode != self.item_barcode:
                    continue
                # If we get this far, we found a hold request.
                self._requester_name = cells[0].get_text()
                self._requester_url = cells[0].a['href']
                self._date_requested = cells[9].get_text()
                # Date is actually date + time, so strip the time part.
                end = self._date_requested.find(' ')
                self._date_requested = self._date_requested[:end]
                # We're done -- don't need to go further.
                if __debug__: log("hold by {} on {}", self._requester_name,
                                  self._date_requested)
                break
        else:
            if __debug__: log('no loans for {}', self.item_tind_id)


    def _fill_patron_details(self, patron):
        # If we can't find values, then we leave the following.
        self._requester_email = ''
        self._requester_type = ''

        if patron:
            # Save the patron page in case we need it later.
            self._patron_data = patron
            soup = BeautifulSoup(patron, features='lxml')
            tables = soup.body.find_all('table')
            if len(tables) < 2:
                if __debug__: log('patron data missing expected table')
                return
            personal_table_rows = tables[1].find_all('tr')
            if len(personal_table_rows) < 9:
                if __debug__: log('patron data missing expected table cells')
                return
            self._requester_email = personal_table_rows[6].find('td').get_text()
            self._requester_type = personal_table_rows[8].find('td').get_text()
        else:
            if __debug__: log('no patron for {}', self.item_tind_id)


    def _fill_copies_not_on_shelf(self):
        '''not on shelf, in this case meaning lost or loaned out'''
        self._copies_not_on_shelf = []
        tind_id = self.item_tind_id
        if tind_id in self._holdings_data:
            if __debug__: log('looking in holdings of {} for n.o.s.', tind_id)
            soup = BeautifulSoup(self._holdings_data[tind_id], features='lxml')
            tables = soup.body.find_all('table')
            rows = tables[1].find_all('tr')
            to_get = []
            for row in rows:
                text = row.text.lower()
                if text.find('on loan') > 0 or text.find('lost') > 0:
                    columns = row.find_all('td')
                    to_get.append(barcode_from_link(columns[0].input))
            self._copies_not_on_shelf = self._tind.records(to_get, self._session)
        else:
            if __debug__: log('no holdings data for {}', tind_id)


    @classmethod
    def field_title(cls, name):
        '''Given the name of a field, return a short human-readable title that
        describes its meaning.'''
        if name in _ATTRIBUTE_TITLES:
            return _ATTRIBUTE_TITLES[name]



# Tind interface class
# .............................................................................

class Tind(object):
    '''Class to interface to TIND.io.'''

    # Cache of record objects created, indexed by barcode.  We may end up
    # getting records in different ways, so we want to avoid recreating objects.
    _barcodes_cache = {}


    def __init__(self, access):
        self._access = access


    def records(self, barcode_list, session = None):
        if barcode_list is None or len(barcode_list) == 0:
            if __debug__: log('empty barcode list => nothing to do')
            return []
        records_list = []
        barcodes_to_get = []
        for barcode in barcode_list:
            if barcode in self._barcodes_cache:
                if __debug__: log('reusing existing object for {}', barcode)
                records_list.append(self._barcodes_cache[barcode])
            else:
                barcodes_to_get.append(barcode)
        if barcodes_to_get:
            if __debug__: log('starting procedure for connecting to tind.io')
            if session is None:
                session = self._tind_session()
            if __debug__: log('will ask tind about {} barcodes', len(barcodes_to_get))
            json_data = self._tind_json(session, barcodes_to_get)
            if json_data:
                if __debug__: log('received {} records from tind.io', len(json_data))
                records_list += [TindRecord(r, self, session) for r in json_data]
            else:
                # This means we have a problem.
                details = 'Caltech.tind.io returned an empty result for our query'
                alert_fatal('Empty result from TIND', details)
                raise ServiceFailure(details)
        if __debug__: log('returning {} records', len(records_list))
        return records_list


    def _tind_session(self):
        '''Connects to TIND.io using Shibboleth and returns a session object.
        '''
        inform('Authenticating user to TIND ...')
        session = None
        logged_in = False
        user = pswd = None
        # Loop the login part in case the user enters the wrong password.
        while not logged_in:
            # Create a blank session and hack the user agent string.
            session = requests.Session()
            session.trust_env = False
            session.headers.update( { 'user-agent': _USER_AGENT_STRING } )

            # Access the first page to get the session data, and do it before
            # asking the user for credentials in case this fails.
            self._tind_request(session, 'get', _SHIBBED_TIND_URL, None, 'Shib login page')
            sessionid = session.cookies.get('JSESSIONID')

            # Get the credentials.  The initial values of None for user & pswd
            # will make AccessHandler use keyring values if they exist.
            user, pswd, cancel = self._access.name_and_password('Caltech Access', user, pswd)
            if cancel:
                if __debug__: log('user cancelled out of login dialog')
                raise UserCancelled
            if not user or not pswd:
                if __debug__: log('empty values returned from login dialog')
                return None
            login = {'j_username'       : user,
                     'j_password'       : pswd,
                     '_eventId_proceed' : ''}

            # SAML step 1
            next_url = '{};jsessionid={}?execution=e1s1'.format(_SSO_URL, sessionid)
            self._tind_request(session, 'post', next_url, login, 'e1s1')

            # SAML step 2.  Store the content for use later below.
            next_url = '{};jsessionid={}?execution=e1s2'.format(_SSO_URL, sessionid)
            content = self._tind_request(session, 'post', next_url, login, 'e1s2')

            # Did we succeed?
            logged_in = bool(str(content).find('Forgot your password') <= 0)
            if not logged_in:
                if yes_reply('Incorrect login. Try again?'):
                    # Don't supply same values to the dialog if they were wrong.
                    user = pswd = None
                else:
                    if __debug__: log('user cancelled access login')
                    raise UserCancelled

        # Extract the SAML data and follow through with the action url.
        # This is needed to get the necessary cookies into the session object.
        if __debug__: log('data received from idp.caltech.edu')
        tree = html.fromstring(content)
        if tree is None or tree.xpath('//form[@action]') is None:
            details = 'Caltech Shib access result does not have expected form'
            alert_fatal('Unexpected TIND result -- please inform developers', details)
            raise ServiceFailure(details)
        next_url = tree.xpath('//form[@action]')[0].action
        SAMLResponse = tree.xpath('//input[@name="SAMLResponse"]')[0].value
        RelayState = tree.xpath('//input[@name="RelayState"]')[0].value
        saml_payload = {'SAMLResponse': SAMLResponse, 'RelayState': RelayState}
        try:
            if __debug__: log('issuing network post to {}', next_url)
            res = session.post(next_url, data = saml_payload, allow_redirects = True)
        except Exception as err:
            details = 'exception connecting to TIND: {}'.format(err)
            alert_fatal('Server problem -- try again later', details)
            raise ServiceFailure(details)
        if res.status_code != 200:
            details = 'TIND network post returned status {}'.format(res.status_code)
            alert_fatal('Caltech.tind.io circulation page failed to respond', details)
            raise ServiceFailure(details)
        if __debug__: log('successfully created session with caltech.tind.io')
        return session


    def _tind_request(self, session, get_or_post, url, data, purpose):
        '''Issue the network request to TIND.'''
        access = session.get if get_or_post == 'get' else session.post
        try:
            if __debug__: log('issuing network {} for {}', get_or_post, purpose)
            req = access(url, data = data, allow_redirects = True)
        except Exception as err:
            details = 'exception connecting to TIND: {}'.format(err)
            alert_fatal('Unable to connect to TIND -- try later', details)
            raise ServiceFailure(details)
        if req.status_code >= 300:
            details = 'Shibboleth returned status {}'.format(req.status_code)
            alert_fatal('Service failure -- please inform developers', details)
            raise ServiceFailure(details)
        return req.content


    def _tind_json(self, session, barcode_list):
        '''Return the data from using AJAX to search tind.io's global lists.'''
        # Trial and error testing revealed that if the "OR" expression has
        # more than about 1024 barcodes, TIND returns http code 400.  So, we
        # break up our search into chunks of 1000 (a nice round number).
        data = []
        for codes in grouper(barcode_list, 1000):
            search_expr = codes[0] if len(codes) == 1 else '(' + ' OR '.join(codes) + ')'
            payload = self._tind_ajax_payload('barcode', search_expr)
            data += self._tind_ajax(session, payload)
        return data


    def _tind_ajax_payload(self, field, search_expr):
        # About the fields in 'data': I found the value of the payload data
        # by the following procedure:
        #
        #  1. Run Google Chrome
        #  2. Visit https://caltech.tind.io/lists/
        #  3. Turn on dev tools in Chrome
        #  4. Go to the "Network" tab in dev tools
        #  5. Click on the XHR subpanel
        #  6. On the Tind page, type barcode:NNN in the search box & hit return
        #      (note: find a real barcode for NNN)
        #  7. Look in the XHR output, in the "Request Payload" portion
        #  8. Copy that whole payload string to your computer's clipboard
        #  9. Start a python3 console
        #  10. import json as jsonlib
        #  11. jsonlib.loads('... paste the clipboard ...')
        #
        # Be sure to use single quotes to surround the request payload value
        # when pasting it into jsonlib.loads().
        #
        # The value you get back will have a field named 'columns' with a
        # very long list of items in it.  By trial and error, I discovered
        # you don't need to use all of them in the list submitted as the data
        # in the ajax call: you only need as many as you use in the 'order'
        # directive -- which makes sense, since if you're telling it to order
        # the output by a given column, the column needs to be identified.
        #
        # The 'length' field needs to be set to something, because otherwise
        # it defaults to 25.  It turns out you can set it to a higher number
        # than the number of items in the actual search result, and it will
        # return only the number found.

        return {'columns': [{'data': field, 'name': field,
                             'searchable': True, 'orderable': True,
                             'search': {'value': '', 'regex': False}}],
                'order': [{'column': 0, 'dir': 'asc'}],
                'search': {'regex': False, 'value': field + ':' + search_expr},
                'length': 1000, 'draw': 1, 'start': 0, 'table_name': 'crcITEM'}


    def _tind_ajax(self, session, payload):
        # The session object has Invenio session cookies and Shibboleth IDP
        # session data.  Now we have to invoke the Ajax call that would be
        # triggered by typing in the search box and clicking "Search" at
        # https://caltech.tind.io/lists/.  To figure out the parameters and
        # data needed, I used the data inspectors in a browser to look at the
        # JS script libraries loaded by the page, especially globaleditor.js,
        # to find the Ajax invocation code and figure out the URL.
        ajax_url     = 'https://caltech.tind.io/lists/dt_api'
        ajax_headers = {'X-Requested-With' : 'XMLHttpRequest',
                        "Content-Type"     : "application/json",
                        'User-Agent'       : _USER_AGENT_STRING}
        try:
            if __debug__: log('posting ajax call to tind.io')
            resp = session.post(ajax_url, headers = ajax_headers, json = payload)
        except Exception as err:
            details = 'exception doing AJAX call {}'.format(err)
            alert_fatal('Unable to get data from TIND', details)
            raise ServiceFailure(details)
        if resp.status_code != 200:
            details = 'tind.io AJAX returned status {}'.format(resp.status_code)
            alert_fatal('TIND failed to return data', details)
            raise ServiceFailure(details)
        results = resp.json()
        if 'recordsTotal' not in results or 'data' not in results:
            alert_fatal('Unexpected result from TIND AJAX call')
            raise InternalError('Unexpected result from TIND AJAX call')
        total_records = results['recordsTotal']
        if __debug__: log('TIND says there are {} records', total_records)
        if len(results['data']) != total_records:
            details = 'Expected {} records but received {}'.format(
                total_records, len(results['data']))
            alert_fatal('TIND returned unexpected number of items',
                                 details = details)
            raise ServiceFailure('TIND returned unexpected number of items')
        if __debug__: log('succeeded in getting data via ajax')
        return results['data']


    def loan_details(self, tind_id, session):
        '''Get the HTML of a loans detail page from TIND.io.'''
        url = 'https://caltech.tind.io/admin2/bibcirculation/get_item_requests_details?ln=en&recid=' + str(tind_id)
        try:
            inform('Getting details from TIND for {} ...'.format(tind_id))
            (resp, error) = net('get', url, session = session, allow_redirects = True)
            if isinstance(error, NoContent):
                if __debug__: log('server returned a "no content" code')
                return ''
            elif error:
                raise error
            elif resp == None:
                raise InternalError('Unexpected network return value')
            else:
                content = str(resp.content)
                return content if content.find('There are no loans') < 0 else ''
        except Exception as err:
            details = 'exception connecting to tind.io: {}'.format(err)
            alert_fatal('Failed to connect -- try again later', details)
            raise ServiceFailure(details)


    def patron_details(self, patron_name, patron_url, session):
        '''Get the HTML of a loans detail page from TIND.io.'''
        if not patron_name or not patron_url:
            if __debug__: log('no patron => no patron details to get')
            return ''
        try:
            inform('Getting patron details for {} ...'.format(patron_name))
            (resp, error) = net('get', patron_url, session = session, allow_redirects = True)
            if isinstance(error, NoContent):
                if __debug__: log('server returned a "no content" code')
                return ''
            elif error:
                raise error
            elif resp == None:
                raise InternalError('Unexpected network return value')
            else:
                return str(resp.content)
        except Exception as err:
            details = 'exception connecting to tind.io: {}'.format(err)
            alert_fatal('Failed to connect -- try again later', details)
            raise ServiceFailure(details)


    def holdings(self, tind_id, session):
        '''Get the HTML of a loans detail page from TIND.io.'''
        url = 'https://caltech.tind.io/record/{}/holdings'.format(tind_id)
        try:
            inform('Getting holdings info from TIND for {} ...'.format(tind_id))
            (resp, error) = net('get', url, session = session, allow_redirects = True)
            if isinstance(error, NoContent):
                if __debug__: log('server returned a "no content" code')
                return ''
            elif error:
                raise error
            elif resp == None:
                raise InternalError('Unexpected network return value')
            else:
                content = str(resp.content)
                return content if content.find('This record has no copies.') < 0 else ''
        except Exception as err:
            details = 'exception connecting to tind.io: {}'.format(err)
            alert_fatal('Failed to connect -- try again later', details)
            raise ServiceFailure(details)


# Miscellaneous utilities.
# .............................................................................

def first_author(author_text):
    # Preprocessing for some inconsistent cases.
    if author_text.endswith('.'):
        author_text = author_text[:-1]
    if author_text.startswith('by'):
        author_text = author_text[3:]

    # Find the first author or editor.
    if author_text.startswith('edited by'):
        fragment = author_text[10:]
        if fragment.find('and') > 0:
            start = fragment.find('and')
            first_author = fragment[:start].strip()
        elif fragment.find('...') > 0:
            start = fragment.find('...')
            first_author = fragment[:start].strip()
        else:
            first_author = fragment
    else:
        author_list = re.split('\s\[?and\]?\s|,|\.\.\.|;', author_text)
        first_author = author_list[0].strip()

    # Extract the last name if possible and return it.
    try:
        return HumanName(first_author).last
    except:
        return first_author


def barcode_from_link(td):
    # This expects an element from a Tind holdings table that looks like this:
    # <input class="bibcircbutton" onmouseout="this.className=\'bibcircbutton\'"
    #        onclick="location.href=\'https://caltech.tind.io/record/750529/holdings/request?barcode=35047019258938&amp;ln=en\'" 
    #        ... />
    onclick = td['onclick']
    start = onclick.find('barcode=')
    if start < 0:
        return ''
    start += 8
    end = onclick.find('&', start)
    end = len(onclick) if end < 1 else end
    return onclick[start:end]
