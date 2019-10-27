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

from   collections import namedtuple
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
from .record import ItemRecord
from .ui import inform, warn, alert, alert_fatal, yes_reply


# Helper data types.
# -----------------------------------------------------------------------------

Holding = namedtuple('Holding', 'barcode status location')
Holding.__doc__ ='''
Named tuple describing the status (as a string such as 'on shelf' or 'lost')
and expected location for a given barcode.
'''


# Global constants.
# .............................................................................

_USER_AGENT_STRING = 'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko)'
'''
Using a user-agent string that identifies a browser seems to be important
in order to make Shibboleth or TIND return results.
'''

_SHIBBED_TIND_URL = 'https://caltech.tind.io/youraccount/shibboleth?referer=https%3A//caltech.tind.io/%3F'
'''URL to start the Shibboleth authentication process for Caltech TIND.'''

_SSO_URL = 'https://idp.caltech.edu/idp/profile/SAML2/Redirect/SSO'
'''Root URL for the Caltech SAML steps.'''


# Class definitions.
# .............................................................................

class Tind(object):
    '''Class to interface to TIND.io.'''

    # Session created from the user log in.
    _session = None

    # Cache of record objects created, indexed by barcode.  We may end up
    # getting records in different ways, so we want to avoid recreating objects.
    _cache = {}

    # Track the holdings for a given item.  This is a dictionary indexed by
    # ItemRecord objects, and each value is a list of Holding named tuples,
    # one tuple for each copy of the item according to Caltech.tind.io.
    _holdings = {}


    def __init__(self, access):
        if __debug__: log('initializing Tind() object')
        self._session = self._tind_session(access)


    def records(self, barcode_list):
        records_list = []
        to_get = []
        for barcode in barcode_list:
            # Check the cache in case already have records from a previous call.
            if barcode in self._cache:
                if __debug__: log('reusing existing object for {}', barcode)
                records_list.append(self._cache[barcode])
            else:
                to_get.append(barcode)
        if to_get:
            if __debug__: log('will ask tind about {} barcodes', len(to_get))
            json_data = self._tind_json(self._session, to_get)
            if json_data:
                if __debug__: log('received {} records from tind.io', len(json_data))
                records_list += [self.filled_record(r) for r in json_data]
            else:
                # This means we have a problem.
                details = 'Caltech.tind.io returned an empty result for our query'
                alert_fatal('Empty result from TIND', details)
                raise ServiceFailure(details)
        if __debug__: log('returning {} records', len(records_list))
        return records_list


    def holdings(self, records_list):
        '''Takes a list of ItemRecords, and returns a dictionary where the keys
        are ItemRecords and the values are lists of Holding tuples.  The list
        thereby describes the status (on shelf, lost, etc.) and location of
        each copy of the item described by the ItemRecord.
        '''
        holdings_dict = {}
        to_get = []
        for record in records_list:
            # Check the cache in case already have holdings from a previous call.
            if record in self._holdings:
                if __debug__: log('returning stored holdings for {}', record)
                holdings_dict[record] = self._holdings[record]
            else:
                to_get.append(record)
        if to_get:
            if __debug__: log('will ask tind about {} holdings', len(to_get))
            for record in [r for r in to_get if r not in holdings_dict]:
                holdings_dict[record] = self._tind_holdings(self._session, record)
        if __debug__: log('returning {} records', len(holdings_dict))
        return holdings_dict


    def _tind_session(self, access_handler):
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
            user, pswd, cancel = access_handler.name_and_password('Caltech Access', user, pswd)
            if cancel:
                if __debug__: log('user cancelled out of login dialog')
                raise UserCancelled
            if not user or not pswd:
                if __debug__: log('empty values returned from login dialog')
                return None
            login = {'j_username': user, 'j_password': pswd, '_eventId_proceed': ''}

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
            res = session.post(next_url, data = saml_payload)
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
            req = access(url, data = data)
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
        '''Return the data obtained using AJAX to search tind.io's global lists.'''
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


    def _tind_holdings(self, session, record):
        '''Returns a list of Holding tuples.
        '''
        tind_id = record.item_tind_id
        url = 'https://caltech.tind.io/record/{}/holdings'.format(tind_id)
        holdings = []
        try:
            inform('Getting holdings info from TIND for {} ...'.format(tind_id))
            (resp, error) = net('get', url, session = session)
            if isinstance(error, NoContent):
                if __debug__: log('server returned a "no content" code')
                return []
            elif error:
                raise error
            elif resp == None:
                raise InternalError('Unexpected network return value')
            else:
                content = str(resp.content)
                if not content or content.find('This record has no copies.') >= 0:
                    warn('Unexpectedly empty holdings page for TIND id {}', tind_id)
                    return []
                soup = BeautifulSoup(content, features='lxml')
                tables = soup.body.find_all('table')
                if len(tables) >= 2:
                    rows = tables[1].find_all('tr')
                    for row in rows[1:]:        # Skip the heading row.
                        columns = row.find_all('td')
                        barcode = barcode_from_link(columns[0].input)
                        location = columns[3].text
                        status = columns[7].text
                        holdings.append(Holding(barcode, status, location))
                if __debug__: log('holdings for {} = {}', tind_id, holdings)
                return holdings
        except Exception as err:
            details = 'exception connecting to tind.io: {}'.format(err)
            alert_fatal('Failed to connect -- try again later', details)
            raise ServiceFailure(details)


    def filled_record(self, json_dict):
        '''Returns a new instance of ItemRecord filled out using the data in
        the JSON dictionary 'json_dict', which is assumed to contain the fields
        in the kind of JSON record returned by the TIND ajax calls we make.
        '''
        if __debug__: log('creating record for {}', json_dict['barcode'])
        (title, author)      = title_and_author(json_dict['title'])
        r                    = ItemRecord()
        r.item_title         = title
        r.item_author        = author
        r.item_barcode       = json_dict['barcode']
        r.item_tind_id       = json_dict['id_bibrec']
        r.item_call_number   = json_dict['call_no']
        r.item_copy_number   = json_dict['description']
        r.item_location_name = json_dict['location_name']
        r.item_location_code = json_dict['location_code']
        r.item_status        = json_dict['status']
        r.item_loan_period   = json_dict['loan_period']
        r.item_type          = json_dict['item_type']
        r.holds_count        = json_dict['number_of_requests']
        r.date_created       = json_dict['creation_date']
        r.date_modified      = json_dict['modification_date']
        r.item_record_url    = 'https://caltech.tind.io/record/' + str(r.item_tind_id)
        # Note: the value of ['links']['barcode'] is not the same as barcode
        r.item_details_url   = 'https://caltech.tind.io' + json_dict['links']['barcode']
        # Save the data we used in an extra field, in case it's useful.
        r._orig_data = json_dict
        return r


# Miscellaneous utilities.
# .............................................................................

def title_and_author(title_string):
    '''Return a tuple of (title, author) extracted from the single string
    'title_string', which is assumed to be the value of the 'title' field from
    a TIND json record for an item.'''
    author_text = ''
    item_title = ''
    if title_string.find(' / ') > 0:
        start = title_string.find(' / ')
        item_title = title_string[:start].strip()
        author_text = title_string[start + 3:].strip()
    elif title_string.find('[by]') > 0:
        start = title_string.find('[by]')
        item_title = title_string[:start].strip()
        author_text = title_string[start + 5:].strip()
    elif title_string.rfind(', by') > 0:
        start = title_string.rfind(', by')
        item_title = title_string[:start].strip()
        author_text = title_string[start + 5:].strip()
    else:
        item_title = title_string
    return (item_title, first_author(author_text))


def first_author(author_text):
    # Preprocessing for some inconsistent cases.
    if author_text == '':
        return ''
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
