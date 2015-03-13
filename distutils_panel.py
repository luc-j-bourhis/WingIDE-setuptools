"""
Distutils integration for Wing IDE.

Copyright (c) 2015, Luc J. Bourhis <luc_j_bourhis@mac.com>

All rights reserved.

Redistribution and use in source and binary forms, with or without
modification, are permitted provided that the following conditions are met:

1. Redistributions of source code must retain the above copyright notice, this
   list of conditions and the following disclaimer.
2. Redistributions in binary form must reproduce the above copyright notice,
   this list of conditions and the following disclaimer in the documentation
   and/or other materials provided with the distribution.

THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS AND CONTRIBUTORS "AS IS" AND
ANY EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT LIMITED TO, THE IMPLIED
WARRANTIES OF MERCHANTABILITY AND FITNESS FOR A PARTICULAR PURPOSE ARE
DISCLAIMED. IN NO EVENT SHALL THE COPYRIGHT OWNER OR CONTRIBUTORS BE LIABLE FOR
ANY DIRECT, INDIRECT, INCIDENTAL, SPECIAL, EXEMPLARY, OR CONSEQUENTIAL DAMAGES
(INCLUDING, BUT NOT LIMITED TO, PROCUREMENT OF SUBSTITUTE GOODS OR SERVICES;
LOSS OF USE, DATA, OR PROFITS; OR BUSINESS INTERRUPTION) HOWEVER CAUSED AND
ON ANY THEORY OF LIABILITY, WHETHER IN CONTRACT, STRICT LIABILITY, OR TORT
(INCLUDING NEGLIGENCE OR OTHERWISE) ARISING IN ANY WAY OUT OF THE USE OF THIS
SOFTWARE, EVEN IF ADVISED OF THE POSSIBILITY OF SUCH DAMAGE.
"""

import os, sys
import re
import wingapi
from wingutils import location
from wingutils import encoding_utils
from wingutils import spawn
from guiutils import wgtk
from guiutils import dockview
from guiutils import wingview
from guiutils import winmgr
import guimgr
from edit import cap_oscommands
from command import commandmgr

import re
_AI = wingapi.CArgInfo

# Write any text which may need to be translated as _("....")
import gettext
_ = gettext.translation('scripts_distutils_panel',
                        fallback = 1).ugettext

# This special attribute is used so that the script manager can also
# translate docstrings for the commands found here
_i18n_module = 'scripts_distutils_panel'

# Start of commands

def distutils_build_in_place():
    """ Build in-place using Distutils """
    view = wingapi.gApplication.fSingletons.fGuiMgr.ShowPanel(_kPanelID)
    view._Build()

# End of commands

# Note that panel IDs must be globally unique so all user-provided panels
# MUST add a random uniquifier after '#'.  The panel can still be referred
# to by the portion of the name before '#' and Wing will warn when there
# are multiple panel definitions with the same base name (in which case
# Wing-defined panels win over user-defined panels and otherwise the
# last user-defined panel type wins when referred to w/o the uniquifier).
_kPanelID = 'distutils_panel#02EFWRQK9X24'

class _CDistutilsPanelDefn(dockview.CPanelDefn):
    """Panel definition for the project manager"""

    def __init__(self, singletons):
        self.fSingletons = singletons
        dockview.CPanelDefn.__init__(self, self.fSingletons.fPanelMgr,
                                     _kPanelID, 'tall', 0)
        winmgr.CWindowConfig(self.fSingletons.fWinMgr, 'panel:%s' % _kPanelID,
                             size=(350, 1000))

    def _CreateView(self):
        return _CDistutilsView(self.fSingletons)

    def _GetLabel(self, panel_instance):
        """Get (label, prefix, suffix) for the display label to use for the
        given panel instance"""
        return _('Distutils'), '', ''

    def _GetTitle(self, panel_instance):
        """Get full title for the given panel instance"""
        return _('Distutils Panel')

class _CDistutilsViewCommands(commandmgr.CClassCommandMap):

    kDomain = 'user'
    kPackage = 'distutils_panel'

    def __init__(self, singletons, view):
        commandmgr.CClassCommandMap.__init__(self, i18n_module=_i18n_module)
        assert isinstance(view, _CDistutilsView)
        self.fSingletons = singletons
        self.__fView = view


class _CDistutilsView(wingview.CViewController):
    """ A panel to run Distutils setup.py and collect errors

        When the "Build" button is pressed, the following command is
        executed in the directory of the project file:

            python -u setup.py build_ext -i

        where "python" is the Python executable for the current project.
        It is therefore assumed that there is a project and that there is
        a suitable setup.py sitting in the directory of that project file.
        An error dialogue is displayed if it is not so.

        Build errors are then gathered and displayed in a list. The user can
        then click one of them to jump to the relevant source code in the
        editor.

        There is also a Log tab which displays the full text output by
        the build command.

        TODO: at the moment, only detect Cython errors; C/C++ compiler error
        patterns are different for different compilers but one can guess
        the compiler in use by looking at the output of the command above.
    """

    def __init__(self, singletons):
        """ Constructor """

        # Init inherited
        wingview.CViewController.__init__(self, ())

        # External managers
        self.fSingletons = singletons

        self.__fCmdMap = _CDistutilsViewCommands(self.fSingletons, self)

        self.__CreateGui()

    def _destroy_impl(self):
        wgtk.Destroy(self.fErrorList)

    ##########################################################################
    # Inherited calls from wingview.CViewController
    ##########################################################################

    def GetDisplayTitle(self):
        """ Returns the title of this view suitable for display. """
        return _("Distutils Panel")

    def GetCommandMap(self):
        """ Get the command map object for this view. """
        return self.__fCmdMap

    def BecomeActive(self):
        pass

    ##########################################################################
    # Popup menu and actions
    ##########################################################################

    def __CreateGui(self):
        self.fNotebook = wgtk.Notebook()

        self.fBuildButton = wgtk.IconButton(
            icon=wgtk.STOCK_EXECUTE, relief=wgtk.RELIEF_NONE,
            border_width=0, focus_on_click=False)
        wgtk.gui_connect(self.fBuildButton, 'clicked',
                         wgtk.NoObjCallback(self._Build))
        self.fBuildButton.set_tip(_('Build in-place'))

        self.fCleanButton = wgtk.IconButton(
            icon='wingide-trash', relief=wgtk.RELIEF_NONE,
            border_width=0, focus_on_click=False)
        wgtk.gui_connect(self.fCleanButton, 'clicked',
                         wgtk.NoObjCallback(self._Clean))
        self.fCleanButton.set_tip(_('Clean'))

        self.fTerminateButton = wgtk.IconButton(
            icon='wingide-os-commands-stop', relief=wgtk.RELIEF_NONE,
            border_width=0, focus_on_click=False)
        wgtk.gui_connect(self.fTerminateButton, 'clicked',
                         wgtk.NoObjCallback(self._Terminate))
        self.fTerminateButton.set_tip(_('Terminate build'))
        self.fTerminateButton.setEnabled(False)

        top_hbox = wgtk.HBox(visible=True)
        top_hbox.pack_start(self.fBuildButton, expand=False)
        top_hbox.pack_start(self.fCleanButton, expand=False)
        top_hbox.pack_start(self.fTerminateButton, expand=False)

        tree = wgtk.SimpleTree(
            [_("File"), _("Line"), _("Column"), _("Message")],
            plain_text=True)
        for i in (0, 1):
            tree.hideColumn(i)
        wgtk.gui_connect(
            tree, 'button-press-event', self._OnClickedErrorItem)
        wgtk.InitialShow(tree)
        self.fErrorList = tree

        self.fErrorTabLabel = wgtk.QLabel('Errors/Warnings')
        self.fErrorTabLabel.setToolTip('Build errors and warnings')
        self.fNotebook.append_page(self.fErrorList, self.fErrorTabLabel)

        self.fLog = cap_oscommands.CConsoleView(self.fSingletons)
        self.fLogTabLabel = wgtk.QLabel('   Log   ')
        self.fLog._fScint.set_wrap_mode(True)
        self.fLogTabLabel.setToolTip('Log of the last build')
        self.fNotebook.append_page(self.fLog.fGtkWidget, self.fLogTabLabel)

        self.fStatus = wgtk.Label()

        vbox = wgtk.VBox(visible=True)
        vbox.pack_start(top_hbox, expand=False)
        vbox.pack_start(self.fStatus, expand=False)
        vbox.pack_start(self.fNotebook, expand=True)

        self._SetGtkWidget(vbox)

    python_error_pattern = re.compile(
        r''' ^ Traceback .*? File \s+ " (?P<filename> [^"\n]+?) " , \s+
                line \s+ (?P<line>\d+) .*?
             ^ (?P<message> \w+ Error: .+?) $
        ''', flags=re.X|re.M|re.S)
    cython_error_pattern = re.compile(
        r''' ^ (?P<filename>[^:\n]+?) : (?P<line>\d+) : (?P<column>\d+)
                : [ ] (?P<message>.+?) $
        ''', flags=re.X|re.M|re.S)

    distutils_build_in_place_action = '{}()'.format(
        distutils_build_in_place.__name__)

    def _ProjectDir(self):
        my_proj = wingapi.gApplication.GetProject()
        if my_proj is None:
            wingapi.gApplication.ShowMessageDialog(
                title='Distutils Build',
                text='You need to open a project first.',
                sheet=True)
            return None
        return os.path.dirname(my_proj.GetFilename())

    def _Execute(self, setup_py_args, postprocess=None):
        """ Execute setup.py with the given command line arguments """
        import proj.project

        projectDir = self._ProjectDir()
        if projectDir is None:
            return
        my_proj = wingapi.gApplication.GetProject()

        setupDotPy = os.path.join(projectDir, 'setup.py')
        if not os.path.isfile(setupDotPy):
            wingapi.gApplication.ShowMessageDialog(
                title='Distutils Build',
                text='You need to create a file setup.py in your project '
                     'directory first.',
                sheet=True)
            return

        saveMgr = self.fSingletons.fGuiMgr.fSaveMgr
        savable_list = []
        for savable in saveMgr.GetItemsToSave():
            if isinstance(savable.fLocation, location.CUnknownLocation):
                continue # unsaved
            if isinstance(savable, proj.project.CProject):
                continue # .wpr itself
            if savable._fAutoSave is not None and not savable._fAutoSave:
                continue # looks like this one is marked for not auto-saving
            savable_list.append(savable)
        saveMgr.PromptForSave(
            savable_list, initial_prompt=False, can_cancel=False)

        encoding = encoding_utils.kDefaultConsoleOutputEncoding

        # buffer_size = 1 for for line mode
        cmd = (my_proj.GetPythonExecutable(setupDotPy), "-u", "setup.py")
        self.output = ""
        self.fLog._Clear()
        self.child_process = spawn.CChildProcess(
            cmd + setup_py_args,
            env=my_proj.GetEnvironment(setupDotPy),
            child_pwd=projectDir,
            io_encoding=encoding, buffer_size=1)
        self.fBuildButton.setEnabled(False)
        self.fCleanButton.setEnabled(False)
        self.fTerminateButton.setEnabled(True)
        self.fStatus.set_text("Running...")

        def received_output(child, text):
            self.output += text
            self.fLog.AppendOutput(text)
            self.fLogTabLabel.setStyleSheet("QLabel { color : red; }")

        def terminated(child_process):
            if postprocess is not None:
                postprocess()
            self.fLogTabLabel.setStyleSheet("QLabel { color : black; }")
            contents = []
            for m in self.python_error_pattern.finditer(self.output):
                contents.append(
                    m.group('filename', 'line') + ('', m.group('message')))
            for m in self.cython_error_pattern.finditer(self.output):
                contents.append(
                    m.group('filename', 'line', 'column', 'message'))
            self.fErrorList.set_contents(contents)
            self.fBuildButton.setEnabled(True)
            self.fCleanButton.setEnabled(True)
            self.fTerminateButton.setEnabled(False)
            self.fStatus.set_text('')

        def start_failed(child_process, exc):
            self.fTerminateButton.setEnabled(False)
            self.fStatus.set_text('')
            wingapi.gApplication.ShowMessageDialog(
                title='Distutils Build',
                text='Internal error: {}'.format(exc),
                sheet=True)

        self.child_process.connect_while_alive(
            'received-output', received_output, self)
        self.child_process.connect_while_alive(
            'terminated', terminated, self)
        self.child_process.connect_while_alive(
            'start-failed', start_failed, self)
        try:
            self.child_process.Start()
        except OSError:
            self.child_process.destroy()
            self.child_process = None

    def _Build(self):
        """ Build in-place """
        self.fErrorList.set_contents([])
        self._Execute(setup_py_args=("build_ext", "-i"))

    def _Clean(self):
        """ Remove all files produced by builds so far

            The command clean does remove files from the source directory:
            this is a known limitation of Distutils. Thus we roll our own
            hand-made heuristic.
        """
        self._Execute(setup_py_args=("clean", "-a"),
                      postprocess=self.clean_source_directory)

    def clean_source_directory(self):
        projectDir = self._ProjectDir()
        if projectDir is None:
            return
        cleanees = []
        for dirpath, dirnames, filenames in os.walk(projectDir):
            for f in filenames:
                full_path = os.path.join(dirpath, f)
                m = re.search(r'\.(?:(c|cpp)|(o|so|pyd|dll|dylib))$', f)
                if m:
                    if m.lastindex == 2:
                        cleanees.append(full_path)
                    else:
                        with open(full_path) as fo:
                            if re.search(r'generated [ ]+ by [ ]+ cython',
                                         fo.readline(), re.I|re.X):
                                cleanees.append(full_path)
        for f in cleanees:
            self.fLog.AppendOutput(
                "Removing %s\n" % os.path.relpath(f, projectDir))
            os.unlink(f)

    def _Terminate(self):
        """ Called when the terminate button is clicked """
        self.child_process.Kill()
        self.fTerminateButton.setEnabled(False)
        self.fStatus.set_text('')

    def _OnClickedErrorItem(self, tree, event):
        """ Called when the user clicks a line in the error list """
        app = wingapi.gApplication
        x, y, x_root, y_root, button, double = wgtk.GetButtonEventData(event)

        # Always select the row that the pointer is over
        tree.SelectAtClick(x, y)

        selected = tree.GetSelectedContent()
        if selected is not None and len(selected) != 0:
            filename = os.path.join(self._ProjectDir(), selected[0][0])
            line = int(selected[0][1])
            col_txt = selected[0][2]
            col = int(col_txt) if col_txt else 0
            if button == wgtk.kLeftButton and not double:
                doc = app.OpenEditor(filename)
                doc.ScrollToLine(lineno=line-1, pos='center', select=1)

# Register this panel type:  Note that this needs to be at the
# very end of the module so that all the classes defined here
# are already available
_CDistutilsPanelDefn(wingapi.gApplication.fSingletons)


