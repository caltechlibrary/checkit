'''
messages: message-printing utilities for Check It!

Authors
-------

Michael Hucka <mhucka@caltech.edu> -- Caltech Library

Copyright
---------

Copyright (c) 2019 by the California Institute of Technology.  This code is
open-source software released under a 3-clause BSD license.  Please see the
file "LICENSE" for more information.
'''


import colorful
colorful.use_256_ansi_colors()

from   pubsub import pub
import queue
import sys
import wx
import wx.lib.dialogs

from .debug import log
from .exceptions import *


# Exported classes.
# .............................................................................
# The basic principle of writing the classes (like this one) that get used in
# MainBody is that they should take the information they need, rather than
# putting the info into the controller object (i.e., ControlGUI or
# ControlCLI).  This means, for example, that 'use_color' is handed to the
# CLI version of this object, not to the base class or the Control* classes,
# even though use_color is something that may be relevant to more than one of
# the main classes.  This is a matter of separation of concerns and
# information hiding.

class MessageHandlerBase():
    '''Base class for message-printing classes in Check It!'''

    def __init__(self):
        self._colorize = False
        pass


    def info_text(self, text, *args):
        '''Prints an informational message.'''
        return styled(text.format(*args), 'info', self._colorize)


    def warn_text(self, text, *args):
        '''Prints a nonfatal, noncritical warning message.'''
        return styled(text.format(*args), 'warn', self._colorize)


    def error_text(self, text, *args):
        '''Prints a message reporting a critical error.'''
        return styled(text.format(*args), 'error', self._colorize)


    def fatal_text(self, text, *args):
        '''Prints a message reporting a fatal error.  This method does not
        exit the program; it leaves that to the caller in case the caller
        needs to perform additional tasks before exiting.
        '''
        return styled('FATAL: ' + text.format(*args), ['error', 'bold'], self._colorize)


class MessageHandlerCLI(MessageHandlerBase):
    '''Class for printing console messages and asking the user questions.'''

    def __init__(self, use_color, quiet = False):
        super().__init__()
        self._colorize = use_color
        self._quiet = quiet


    def use_color(self):
        return self._colorize


    def be_quiet(self):
        return self._quiet


    def info(self, text, *args):
        '''Prints an informational message.'''
        if __debug__: log(text, *args)
        if not self._quiet:
            print(self.info_text(text, *args), flush = True)


    def warn(self, text, *args):
        '''Prints a nonfatal, noncritical warning message.'''
        if __debug__: log(text, *args)
        print(self.warn_text(text, *args), flush = True)


    def error(self, text, *args):
        '''Prints a message reporting a critical error.'''
        if __debug__: log(text, *args)
        print(self.error_text(text, *args), flush = True)


    def fatal(self, text, *args):
        '''Prints a message reporting a fatal error.  This method does not
        exit the program; it leaves that to the caller in case the caller
        needs to perform additional tasks before exiting.
        '''
        if __debug__: log(text, *args)
        print(self.fatal_text(text, *args), flush = True)


    def yes_no(self, question):
        '''Asks a yes/no question of the user, on the command line.'''
        return input("{} (y/n) ".format(question)).startswith(('y', 'Y'))


class MessageHandlerGUI(MessageHandlerBase):
    '''Class for GUI-based user messages and asking the user questions.'''

    def __init__(self):
        super().__init__()
        self._queue = queue.Queue()
        self._response = None


    def info(self, text, *args):
        '''Prints an informational message.'''
        if __debug__: log('generating info notice')
        wx.CallAfter(pub.sendMessage, "progress_message",
                     message = text.format(*args))


    def warn(self, text, *args):
        '''Prints a nonfatal, noncritical warning message.'''
        if __debug__: log('generating warning notice')
        wx.CallAfter(pub.sendMessage, "progress_message",
                     message = 'Warning: ' + text.format(*args))


    def error(self, text, *args):
        '''Prints a message reporting a critical error.'''
        if __debug__: log('generating error notice')
        if wx.GetApp().TopWindow:
            wx.CallAfter(self._show_dialog, text.format(*args), 'error')
        else:
            # The app window is gone, so wx.CallAfter won't work.
            self._show_dialog(text.format(*args), 'error')
        self._wait()


    def fatal(self, text, *args, **kwargs):
        '''Prints a message reporting a fatal error.  The keyword argument
        'details' can be supplied to pass a longer explanation that will be
        displayed if the user presses the 'Help' button in the dialog.

        Note that this method does not exit the program; it leaves that to
        the caller in case the caller needs to perform additional tasks
        before exiting.
        '''
        if __debug__: log('generating fatal error notice')
        if wx.GetApp().TopWindow:
            wx.CallAfter(self._show_dialog, text.format(*args),
                         kwargs['details'] if 'details' in kwargs else '',
                         severity = 'fatal')
        else:
            # The app window is gone, so wx.CallAfter won't work.
            self._show_dialog(text.format(*args),
                              kwargs['details'] if 'details' in kwargs else '',
                              severity = 'fatal')
        self._wait()


    def yes_no(self, question):
        '''Asks the user a yes/no question using a GUI dialog.'''
        if __debug__: log('generating yes/no dialog')
        wx.CallAfter(self._yes_no, question)
        self._wait()
        if __debug__: log('got response: {}', self._response)
        return self._response


    def _show_note(self, text, *args, severity = 'info'):
        '''Displays a simple notice with a single OK button.'''
        frame = self._current_frame()
        icon = wx.ICON_WARNING if severity == 'warn' else wx.ICON_INFORMATION
        if __debug__: log('showing note dialog')
        dlg = wx.GenericMessageDialog(frame, text.format(*args),
                                      caption = "Check It!", style = wx.OK | icon)
        clicked = dlg.ShowModal()
        dlg.Destroy()
        frame.Destroy()
        self._queue.put(True)


    def _show_dialog(self, text, details, severity = 'error'):
        frame = self._current_frame()
        if 'fatal' in severity:
            short = text
            style = wx.OK | wx.HELP | wx.ICON_ERROR
        else:
            short = text + '\n\nWould you like to try to continue?\n(Click "no" to quit now.)'
            style = wx.YES_NO | wx.YES_DEFAULT | wx.HELP | wx.ICON_EXCLAMATION
        if __debug__: log('showing message dialog')
        dlg = wx.MessageDialog(frame, message = short, style = style,
                               caption = "Check It! has encountered a problem")
        clicked = dlg.ShowModal()
        if clicked == wx.ID_HELP:
            body = ("Check It! has encountered a problem:\n"
                    + "─"*30
                    + "\n{}\n".format(details or text)
                    + "─"*30
                    + "\nIf the problem is due to a network timeout or "
                    + "similar transient error, then please quit and try again "
                    + "later. If you don't know why the error occurred or "
                    + "if it is beyond your control, please also notify the "
                    + "developers. You can reach the developers via email:\n\n"
                    + "    Email: mhucka@library.caltech.edu\n")
            info = wx.lib.dialogs.ScrolledMessageDialog(frame, body, "Error")
            info.ShowModal()
            info.Destroy()
            frame.Destroy()
            self._queue.put(True)
        elif clicked in [wx.ID_NO, wx.ID_OK]:
            dlg.Destroy()
            frame.Destroy()
            self._queue.put(True)
        else:
            dlg.Destroy()
            self._queue.put(True)


    def _yes_no(self, question):
        frame = self._current_frame()
        dlg = wx.GenericMessageDialog(frame, question, caption = "Check It!",
                                      style = wx.YES_NO | wx.ICON_QUESTION)
        clicked = dlg.ShowModal()
        dlg.Destroy()
        frame.Destroy()
        self._response = (clicked == wx.ID_YES)
        self._queue.put(True)


    def _wait(self):
        self._queue.get()


    def _current_frame(self):
        if wx.GetApp():
            if __debug__: log('app window exists; building frame for dialog')
            app = wx.GetApp()
            frame = wx.Frame(app.TopWindow)
        else:
            if __debug__: log("app window doesn't exist; creating one for dialog")
            app = wx.App(False)
            frame = wx.Frame(None, -1, __package__)
        frame.Center()
        return frame


# Message utility funcions.
# .............................................................................

_STYLES_INITIALIZED = False

def styled(text, flags = None, colorize = True):
    '''Style the 'text' according to 'flags' if 'colorize' is True.
    'flags' can be a single string or a list of strings, as follows.
    Explicit colors (when not using a severity color code):
       Colors like 'white', 'blue', 'grey', 'cyan', 'magenta', or other colors
       defined in our messages_styles.py
    Additional color flags reserved for message severities:
       'info'  = informational (green)
       'warn'  = warning (yellow)
       'error' = severe error (red)
       'fatal' = really severe error (red, bold, underlined)
    Optional style additions:
       'bold', 'underlined', 'italic', 'blink', 'struckthrough'
    '''
    # Fail early if we're not colorizing.
    if not colorize:
        return text

    # Lazy-load the style definitions if needed.
    global _STYLES_INITIALIZED
    if not _STYLES_INITIALIZED:
        import microarchiver.messages_styles
        _STYLES_INITIALIZED = True
    from microarchiver.messages_styles import _STYLES
    if type(flags) is not list:
        flags = [flags]

    # Use colorful's clever and-or overloading mechanism to concatenate the
    # style definition, apply it to the text, and return the result.
    attribs = colorful.reset
    for c in flags:
        if c == 'reset':
            attribs &= colorful.reset
        elif c in _STYLES:
            attribs &= _STYLES[c]
        else:
            # Color names for colorful have to start with a lower case letter,
            # which is really easy to screw up.  Let's help ourselves.
            c = c[:1].lower() + c[1:]
            try:
                attribs &= getattr(colorful, c)
            except Exception:
                if __debug__: log('colorful does not recognize color {}', c)
    return attribs | text
