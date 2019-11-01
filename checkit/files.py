'''
files.py: utilities for working with files.

Authors
-------

Michael Hucka <mhucka@caltech.edu> -- Caltech Library

Copyright
---------

Copyright (c) 2019 by the California Institute of Technology.  This code is
open-source software released under a 3-clause BSD license.  Please see the
file "LICENSE" for more information.
'''

import os
from   os import path
import shutil
import string
import subprocess
import sys
import tempfile
import webbrowser

import checkit
from checkit.debug import log


# Constants.
# .............................................................................

_APP_NAME = __package__
'''The human name of this application for human consumption.'''

_APP_REG_PATH = r'Software\Caltech Library\{}\Settings'.format(_APP_NAME)
'''The Windows registry path for this application.'''


# Main functions.
# .............................................................................

def readable(dest):
    '''Returns True if the given 'dest' is accessible and readable.'''
    return os.access(dest, os.F_OK | os.R_OK)


def writable(dest):
    '''Returns True if the destination is writable.'''

    # Helper function to test if a directory is writable.
    def dir_writable(dir):
        # This is based on the following Stack Overflow answer by user "zak":
        # https://stackoverflow.com/a/25868839/743730
        try:
            testfile = tempfile.TemporaryFile(dir = dir)
            testfile.close()
        except (OSError, IOError) as e:
            return False
        return True

    if path.exists(dest) and not path.isdir(dest):
        # Path is an existing file.
        return os.access(dest, os.F_OK | os.W_OK)
    elif path.isdir(dest):
        # Path itself is an existing directory.  Is it writable?
        return dir_writable(dest)
    else:
        # Path is a file but doesn't exist yet. Can we write to the parent dir?
        return dir_writable(path.dirname(dest))


def module_path():
    '''Returns the absolute path to our module installation directory.'''
    # The path returned by module.__path__ is to the directory containing
    # the __init__.py file.
    this_module = sys.modules[__package__]
    return path.abspath(this_module.__path__[0])


def installation_path():
    '''Returns the path to where the application is installed.'''
    # The path returned by module.__path__ is to the directory containing
    # the __init__.py file.  What we want here is the path to the installation
    # of the application binary.
    if sys.platform.startswith('win'):
        from winreg import OpenKey, CloseKey, QueryValueEx, HKEY_LOCAL_MACHINE, KEY_READ
        try:
            if __debug__: log('reading Windows registry entry')
            key = OpenKey(HKEY_LOCAL_MACHINE, _APP_REG_PATH)
            value, regtype = QueryValueEx(key, 'Path')
            CloseKey(key)
            if __debug__: log('path to windows installation: {}'.format(value))
            return value
        except WindowsError:
            # Kind of a problem. Punt and return a default value.
            return path.abspath('C:\Program Files\{}'.format(_APP_NAME))
    else:
        return path.abspath(path.join(module_path(), '..'))


def desktop_path():
    '''Returns the path to the user's desktop directory.'''
    if sys.platform.startswith('win'):
        return path.join(os.environ['USERPROFILE'], 'Desktop')
    else:
        return path.join(path.expanduser('~'), 'Desktop')


def datadir_path():
    '''Returns the path to Lost It's internal data directory.'''
    return path.join(module_path(), 'data')


def files_in_directory(dir, extensions = None):
    '''Returns a list of the files in the directory 'dir'.'''
    if not path.isdir(dir):
        return []
    if not readable(dir):
        return []
    files = []
    for item in os.listdir(dir):
        full_path = path.join(dir, item)
        if path.isfile(full_path) and readable(full_path):
            if extensions and filename_extension(item) in extensions:
                files.append(full_path)
    return sorted(files)


def filename_basename(file):
    '''Returns the basename of 'file' (meaning the portion up to the period
    preceding the extension).
    '''
    parts = file.rpartition('.')
    if len(parts) > 1:
        return ''.join(parts[:-1]).rstrip('.')
    else:
        return file


def filename_extension(file):
    '''Returns the filename extension part of 'file'.'''
    parts = file.rpartition('.')
    if len(parts) > 1:
        return parts[-1].lower()
    else:
        return ''


def alt_extension(filepath, ext):
    '''Returns the 'filepath' with the extension replaced by 'ext'.  The
    extension given in 'ext' should NOT have a leading period: that is, it
    should be "foo", not ".foo".'''
    return path.splitext(filepath)[0] + '.' + ext


def filter_by_extensions(item_list, endings):
    '''Returns a list of those strings in 'item_list' whose endings are one
    of the endings in the list 'endings'.
    '''
    if not item_list:
        return []
    if not endings:
        return item_list
    results = item_list
    for ending in endings:
        results = list(filter(lambda name: ending not in name.lower(), results))
    return results


# The following originally came from an answer posted by user "domenukk"
# to Stack Overflow: https://stackoverflow.com/a/54564813/743730

def is_csv(infile):
    '''Return True if the given file is probably a CSV file.'''
    try:
        with open(infile, newline='') as csvfile:
            start = csvfile.read(4096)
            # isprintable does not allow newlines, printable does not allow umlauts...
            if not all([c in string.printable or c.isprintable() for c in start]):
                return False
            dialect = csv.Sniffer().sniff(start)
            return True
    except csv.Error:
        # Could not get a csv dialect -> probably not a csv.
        return False


def relative(file):
    '''Returns a path that is relative to the current directory.  If the
    relative path would require more than one parent step (i.e., ../../*
    instead of ../*) then it will return an absolute path instead.  If the
    argument is actuall a file path, it will return it unchanged.'''
    if is_url(file):
        return file
    candidate = path.relpath(file, os.getcwd())
    if not candidate.startswith('../..'):
        return candidate
    else:
        return path.realpath(candidate)


def rename_existing(file):
    '''Renames 'file' to 'file.bak'.'''

    def rename(f):
        backup = f + '.bak'
        # If we fail, we just give up instead of throwing an exception.
        try:
            os.rename(f, backup)
            if __debug__: log('renamed {} to {}', file, backup)
        except:
            try:
                delete_existing(backup)
                os.rename(f, backup)
            except:
                if __debug__: log('failed to delete {}', backup)
                if __debug__: log('failed to rename {} to {}', file, backup)

    if path.exists(file):
        rename(file)
        return
    full_path = path.join(os.getcwd(), file)
    if path.exists(full_path):
        rename(full_path)
        return


def delete_existing(file):
    '''Delete the given file.'''
    # Check if it's actually a directory.
    if path.isdir(file):
        if __debug__: log('doing rmtree on directory {}', file)
        try:
            shutil.rmtree(file)
        except:
            if __debug__: log('unable to rmtree {}; will try renaming', file)
            try:
                rename_existing(file)
            except:
                if __debug__: log('unable to rmtree or rename {}', file)
    else:
        if __debug__: log('doing os.remove on file {}', file)
        os.remove(file)


def file_in_use(file):
    '''Returns True if the given 'file' appears to be in use.  Note: this only
    works on Windows, currently.
    '''
    if not path.exists(file):
        return False
    if sys.platform.startswith('win'):
        # This is a hack, and it really only works for this purpose on Windows.
        try:
            os.rename(file, file)
            return False
        except:
            return True
    return False


def copy_file(src, dst):
    '''Copies a file from "src" to "dst".'''
    if __debug__: log('copying file {} to {}', src, dst)
    shutil.copy2(src, dst, follow_symlinks = True)


def open_file(file):
    '''Opens document with default application in Python.'''
    # Code originally from https://stackoverflow.com/a/435669/743730
    if __debug__: log('opening file {}', file)
    if sys.platform.startswith('darwin'):
        subprocess.call(('open', file))
    elif os.name == 'nt':
        os.startfile(file)
    elif os.name == 'posix':
        subprocess.call(('xdg-open', file))


def open_url(url):
    '''Opens the given 'url' in a web browser using the current platform's
    default approach.'''
    if __debug__: log('opening url {}', url)
    webbrowser.open(url)
