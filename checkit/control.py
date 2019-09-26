'''
control.py: human interface controller

After trying alternatives and failing to get things to work, I settled on the
following approach that works on both Mac and Windows 10 in my testing.

The constrol structure of this program is somewhat inverted from a typical
WxPython application.  The typical application would be purely event-driven:
it would be implemented as an object derived from wx.Frame with methods for
different kinds of actions that the user can trigger by interacting with
controls in the GUI.  Once the WxPython app.MainLoop() function is called,
nothing happens until the user does something to trigger an activitiy.
Conversely, in this program, I not only wanted to allow command-line based
interaction, but also wanted the entire process to be started as soon as the
user starts the application.  This is incompatible with the typical
event-driven application structure because there's an explicit sequential
driver and it needs to be kicked off automatically after app.MainLoop() is
called.

The approach taken here has two main features.

* First, there are two threads running: one for the WxPython GUI MainLoop()
  code and all GUI objects (like MainFrame and UserDialog in this file), and
  another thread for the real main body that implements the program's sequence
  of operations.  The main thread is kicked off by the GUI class start()
  method right before calling app.MainLoop().

* Second, the main body thread invokes GUI operations using a combination of
  in-application message passing (using a publish-and-subscribe scheme from
  PyPubsub) and the use of wx.CallAfter().  The MainFrame objects implement
  some methods that can be invoked by other classes, and MainFrame defines
  subscriptions for messages to invoke those methods.  Callers then have to
  use the following idiom to invoke the methods:

    wx.CallAfter(pub.sendMessage, "name", arg1 = "value1", arg2 = "value2")

  The need for this steps from the fact that in WxPython, if you attempt to
  invoke a GUI method from outside the main thread, it will either generate
  an exception or (what I often saw on Windows) simply hang the application.
  wx.CallAfter places the execution into the thread that's running
  MainLoop(), thus solving the problem.

Splitting up the GUI and CLI schemes into separate objects is for the sake of
code modularity and conceptual clarity.

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
import os.path as path
from   pubsub import pub
from   queue import Queue
import wx
import wx.adv
import wx.richtext
import sys
import textwrap
from   threading import Thread
from   time import sleep
import webbrowser

from .files import datadir_path, readable
from .exceptions import *
from .debug import log
from .logo import getLogoIcon


# Exported classes.
# .............................................................................

class ControlBase():
    '''User interface controller base class.'''

    def __init__(self, app_name, byline = None, debugging = False):
        self._name = app_name
        self._byline = byline
        self._debugging = debugging


    @property
    def app_name(self):
        return self._name


    @property
    def is_gui(self):
        '''Returns True if the GUI version of the interface is being used.'''
        return False


    @property
    def debugging(self):
        '''Returns True if debug mode has been turned on.'''
        return self._debugging


class ControlCLI(ControlBase):
    '''User interface controller in command-line interface mode.'''

    def __init__(self, name, byline = None, debugging = False):
        super().__init__(name, byline, debugging)


    def run(self, worker):
        self._worker = worker
        if __debug__: log('calling start() on worker')
        worker.start()
        if __debug__: log('waiting for worker to finish')
        worker.join()
        if __debug__: log('calling stop() on worker')
        worker.stop()


    def quit(self):
        if self._worker:
            if __debug__: log('calling stop() on worker')
            self._worker.stop()
        if __debug__: log('exiting')
        sys.exit()


class ControlGUI(ControlBase):
    '''User interface controller in GUI mode.'''

    def __init__(self, name, byline = None, debugging = False):
        super().__init__(name, byline, debugging)
        self._app = wx.App()
        self._frame = MainFrame(name, byline, None, wx.ID_ANY)
        self._app.SetTopWindow(self._frame)
        self._frame.Center()
        self._frame.Show(True)
        pub.subscribe(self.quit, "quit")


    @property
    def is_gui(self):
        '''Returns True if the GUI version of the interface is being used.'''
        return True


    def run(self, worker):
        self._worker = worker
        if __debug__: log('calling start() on worker')
        worker.start()
        if __debug__: log('starting main GUI loop')
        self._app.MainLoop()
        if __debug__: log('waiting for worker to finish')
        worker.join()
        if __debug__: log('calling stop() on worker')
        worker.stop()


    def quit(self):
        if __debug__: log('quitting')
        if self._worker:
            if __debug__: log('calling stop() on worker')
            self._worker.stop()
        if __debug__: log('destroying control GUI')
        wx.CallAfter(self._frame.Destroy)


    def open_file(self, message, file_pattern):
        return_queue = Queue()
        if __debug__: log('sending message to open_file')
        wx.CallAfter(pub.sendMessage, "open_file", return_queue = return_queue,
                     message = message, file_pattern = file_pattern)
        if __debug__: log('blocking to get results')
        return_queue = return_queue.get()
        if __debug__: log('got results')
        return return_queue


    def save_file(self, message):
        return_queue = Queue()
        if __debug__: log('sending message to save_file')
        wx.CallAfter(pub.sendMessage, "save_file", return_queue = return_queue,
                     message = message)
        if __debug__: log('blocking to get results')
        return_queue = return_queue.get()
        if __debug__: log('got results')
        return return_queue


# Internal implementation classes.
# .............................................................................

class MainFrame(wx.Frame):
    '''Defines the main application GUI frame.'''

    def __init__(self, name, byline, *args, **kwds):
        self._name = name
        self._byline = byline
        self._cancel = False
        self._height = 330 if sys.platform.startswith('win') else 300
        self._width  = 500

        kwds["style"] = kwds.get("style", 0) | wx.DEFAULT_FRAME_STYLE | wx.TAB_TRAVERSAL
        wx.Frame.__init__(self, *args, **kwds)
        self.panel = wx.Panel(self)
        headline = self._name + ((' — ' + self._byline) if self._byline else '')
        self.headline = wx.StaticText(self.panel, wx.ID_ANY, headline, style = wx.ALIGN_CENTER)
        self.headline.SetFont(wx.Font(14, wx.FONTFAMILY_DEFAULT, wx.FONTSTYLE_ITALIC,
                                      wx.FONTWEIGHT_BOLD, 0, "Arial"))

        # For macos, I figured out how to make the background color of the text
        # box be the same as the rest of the UI elements.  That looks nicer for
        # our purposes (IMHO) than the default (which would be white), but then
        # we need a divider to separate the headline from the text area.
        if not sys.platform.startswith('win'):
            self.divider1 = wx.StaticLine(self.panel, wx.ID_ANY)
            self.divider1.SetMinSize((self._width, 2))

        self.text_area = wx.richtext.RichTextCtrl(self.panel, wx.ID_ANY,
                                                  size = (self._width, 200),
                                                  style = wx.TE_MULTILINE | wx.TE_READONLY)

        # Quit button on the bottom.
        if not sys.platform.startswith('win'):
            self.divider2 = wx.StaticLine(self.panel, wx.ID_ANY)
        self.quit_button = wx.Button(self.panel, label = "Quit")
        self.quit_button.Bind(wx.EVT_KEY_DOWN, self.on_cancel_or_quit)

        # On macos, the color of the text background is set to the same as the
        # rest of the UI panel.  I haven't figured out how to do it on Windows.
        if not sys.platform.startswith('win'):
            gray = wx.SystemSettings.GetColour(wx.SYS_COLOUR_BACKGROUND)
            self.text_area.SetBackgroundColour(gray)

        # Create a simple menu bar.
        self.menuBar = wx.MenuBar(0)

        # Add a "File" menu with a quit item.
        self.fileMenu = wx.Menu()
        self.exitItem = wx.MenuItem(self.fileMenu, wx.ID_EXIT, "&Exit",
                                    wx.EmptyString, wx.ITEM_NORMAL)
        self.fileMenu.Append(self.exitItem)
        if sys.platform.startswith('win'):
            # Only need to add a File menu on Windows.  On Macs, wxPython
            # automatically puts the wx.ID_EXIT item under the app menu.
            self.menuBar.Append(self.fileMenu, "&File")

        # Add a "help" menu bar item.
        self.helpMenu = wx.Menu()
        self.helpItem = wx.MenuItem(self.helpMenu, wx.ID_HELP, "&Help",
                                    wx.EmptyString, wx.ITEM_NORMAL)
        self.helpMenu.Append(self.helpItem)
        self.helpMenu.AppendSeparator()
        self.aboutItem = wx.MenuItem(self.helpMenu, wx.ID_ABOUT,
                                     "&About " + self._name,
                                     wx.EmptyString, wx.ITEM_NORMAL)
        self.helpMenu.Append(self.aboutItem)
        self.menuBar.Append(self.helpMenu, "Help")

        # Put everything together and bind some keystrokes to events.
        self.SetMenuBar(self.menuBar)
        self.Bind(wx.EVT_MENU, self.on_cancel_or_quit, id = self.exitItem.GetId())
        self.Bind(wx.EVT_MENU, self.on_help, id = self.helpItem.GetId())
        self.Bind(wx.EVT_MENU, self.on_about, id = self.aboutItem.GetId())
        self.Bind(wx.EVT_CLOSE, self.on_cancel_or_quit)
        self.Bind(wx.EVT_BUTTON, self.on_cancel_or_quit, self.quit_button)

        close_id = wx.NewId()
        self.Bind(wx.EVT_MENU, self.on_cancel_or_quit, id = close_id)
        accel_tbl = wx.AcceleratorTable([(wx.ACCEL_CTRL, ord('W'), close_id )])
        self.SetAcceleratorTable(accel_tbl)

        # Now that we created all the elements, set layout and placement.
        self.SetSize((self._width, self._height))
        self.SetTitle(self._name)
        self.outermost_sizer = wx.BoxSizer(wx.VERTICAL)
        self.outermost_sizer.AddSpacer(5)
        self.outermost_sizer.Add(self.headline, 0, wx.ALIGN_CENTER, 0)
        self.outermost_sizer.AddSpacer(5)
        if not sys.platform.startswith('win'):
            self.outermost_sizer.Add(self.divider1, 0, wx.EXPAND | wx.ALIGN_CENTER_VERTICAL, 0)
            self.outermost_sizer.AddSpacer(5)
        self.outermost_sizer.Add(self.text_area, 0, wx.EXPAND, 0)
        self.outermost_sizer.AddSpacer(5)
        if not sys.platform.startswith('win'):
            self.outermost_sizer.Add(self.divider2, 0, wx.EXPAND | wx.ALIGN_CENTER_VERTICAL, 0)
            self.outermost_sizer.AddSpacer(5)
        self.outermost_sizer.Add(self.quit_button, 0, wx.BOTTOM | wx.CENTER, 0)
        self.outermost_sizer.AddSpacer(5)
        self.SetSizer(self.outermost_sizer)
        self.Layout()
        self.Centre()

        # Finally, hook in message-passing interface.
        pub.subscribe(self.progress_message, "progress_message")
        pub.subscribe(self.open_file, "open_file")
        pub.subscribe(self.save_file, "save_file")


    def on_cancel_or_quit(self, event):
        if __debug__: log('got Exit/Cancel')
        self._cancel = True
        wx.BeginBusyCursor()
        self.progress_message('')
        self.progress_message('Stopping work – this may take a few moments')

        # We can't call pub.sendMessage from this function, nor does it work
        # to call it using wx.CallAfter directly from this function: both
        # methods hang the GUI and the progress message is never printed.
        # Calling it from a separate thread works.  The sleep is to make sure
        # this calling function returns before the thread calls 'quit'.

        def quitter():
            sleep(1)
            if __debug__: log('sending message to quit')
            wx.CallAfter(pub.sendMessage, 'quit')

        subthread = Thread(target = quitter)
        subthread.start()
        return True


    def on_escape(self, event):
        if __debug__: log('got Escape')
        keycode = event.GetKeyCode()
        if keycode == wx.WXK_ESCAPE:
            self.on_cancel_or_quit(event)
        else:
            event.Skip()
        return True


    def on_about(self, event):
        if __debug__: log('opening About window')
        dlg = wx.adv.AboutDialogInfo()
        dlg.SetName(self._name)
        this_module = sys.modules[__package__]
        dlg.SetVersion(this_module.__version__)
        dlg.SetLicense(this_module.__license__)
        dlg.SetDescription('\n'.join(textwrap.wrap(this_module.__description__, 81)))
        dlg.SetWebSite(this_module.__url__)
        dlg.AddDeveloper(this_module.__author__)
        dlg.SetIcon(getLogoIcon())
        wx.adv.AboutBox(dlg)
        return True


    def on_help(self, event):
        if __debug__: log('opening Help window')
        wx.BeginBusyCursor()
        help_file = path.join(datadir_path(), "help.html")
        if readable(help_file):
            webbrowser.open_new("file://" + help_file)
        wx.EndBusyCursor()
        return True


    def progress_message(self, message):
        self.text_area.SetInsertionPointEnd()
        self.text_area.AppendText(message + (' ...\n' if message else ''))
        self.text_area.ShowPosition(self.text_area.GetLastPosition())
        return True


    def open_file(self, return_queue, message, file_pattern = '*.*'):
        if __debug__: log('creating and showing open file dialog')
        fd = wx.FileDialog(self, message, defaultDir = os.getcwd(),
                           wildcard = file_pattern,
                           style = wx.FD_OPEN | wx.FD_FILE_MUST_EXIST)
        cancelled = (fd.ShowModal() == wx.ID_CANCEL)
        file_path = None if cancelled else fd.GetPath()
        if cancelled:
            if __debug__: log('user cancelled dialog')
        else:
            if __debug__: log('file path from user: {}', file_path)
        return_queue.put(file_path)


    def save_file(self, return_queue, message):
        if __debug__: log('creating and showing save file dialog')
        fd = wx.FileDialog(self, message, defaultDir = os.getcwd(),
                           style = wx.FD_SAVE | wx.FD_OVERWRITE_PROMPT)
        cancelled = (fd.ShowModal() == wx.ID_CANCEL)
        file_path = None if cancelled else fd.GetPath()
        if cancelled:
            if __debug__: log('user cancelled dialog')
        else:
            if __debug__: log('file path from user: {}', file_path)
        return_queue.put(file_path)
