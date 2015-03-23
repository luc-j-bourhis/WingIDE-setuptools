"""
Setuptools integration for Wing IDE.

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
_ = gettext.translation('scripts_setuptools_panel',
                        fallback = 1).ugettext

# This special attribute is used so that the script manager can also
# translate docstrings for the commands found here
_i18n_module = 'scripts_setuptools_panel'

# Start of commands

def setuptools_build_in_place():
    """ Build in-place using Setuptools """
    view = wingapi.gApplication.fSingletons.fGuiMgr.ShowPanel(_kPanelID)
    view.build()

def setuptools_clean_all():
    """ Clean all files produced by `setuptools_build_in_place` """
    view = wingapi.gApplication.fSingletons.fGuiMgr.ShowPanel(_kPanelID)
    view.clean()

# End of commands

# Note that panel IDs must be globally unique so all user-provided panels
# MUST add a random uniquifier after '#'.  The panel can still be referred
# to by the portion of the name before '#' and Wing will warn when there
# are multiple panel definitions with the same base name (in which case
# Wing-defined panels win over user-defined panels and otherwise the
# last user-defined panel type wins when referred to w/o the uniquifier).
_kPanelID = 'setuptools_panel#02EFWRQK9X24'

class _CSetuptoolsPanelDefn(dockview.CPanelDefn):
    """Panel definition for the project manager"""

    def __init__(self, singletons):
        self.fSingletons = singletons
        dockview.CPanelDefn.__init__(self, self.fSingletons.fPanelMgr,
                                     _kPanelID, 'tall', 0)
        winmgr.CWindowConfig(self.fSingletons.fWinMgr, 'panel:%s' % _kPanelID,
                             size=(350, 1000))

    def _CreateView(self):
        """Create a new view for this panel type

           Implement parent abstract method.
        """
        return _CSetuptoolsView(self.fSingletons)

    def _GetLabel(self, panel_instance):
        """ Get (label, prefix, suffix) for the display label to use
            for the given panel instance

            Implement parent abstract method.
        """
        return _('Setuptools'), '', ''

    def _GetTitle(self, panel_instance):
        """ Get full title for the given panel instance

            Implement parent abstract method.
        """
        return _('Setuptools Panel')


class _CSetuptoolsViewCommands(commandmgr.CClassCommandMap):

    kDomain = 'user'
    kPackage = 'setuptools_panel'

    def __init__(self, singletons, view):
        commandmgr.CClassCommandMap.__init__(self, i18n_module=_i18n_module)
        assert isinstance(view, _CSetuptoolsView)
        self.fSingletons = singletons
        self.__fView = view


class _CSetuptoolsView(wingview.CViewController):
    """ A panel to run Setuptools setup.py and collect errors

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
    """

    def __init__(self, singletons):
        """ Constructor """

        # Init inherited
        wingview.CViewController.__init__(self, ())

        # External managers
        self.fSingletons = singletons

        self.__fCmdMap = _CSetuptoolsViewCommands(self.fSingletons, self)

        self.__CreateGui()

    def _destroy_impl(self):
        wgtk.Destroy(self._error_list)

    ##########################################################################
    # Inherited calls from wingview.CViewController
    ##########################################################################

    def GetDisplayTitle(self):
        """ Returns the title of this view suitable for display. """
        return _("Setuptools Panel")

    def GetCommandMap(self):
        """ Get the command map object for this view. """
        return self.__fCmdMap

    def BecomeActive(self):
        pass

    ##########################################################################
    # Popup menu and actions
    ##########################################################################

    def __CreateGui(self):
        self._notebook = wgtk.Notebook()

        self._build_button = wgtk.IconButton(
            icon=wgtk.STOCK_EXECUTE, relief=wgtk.RELIEF_NONE,
            border_width=0, focus_on_click=False)
        self._build_button.clicked.connect(self.build)
        self._build_button.set_tip(_('Build in-place'))

        self._clean_button = wgtk.IconButton(
            icon='wingide-trash', relief=wgtk.RELIEF_NONE,
            border_width=0, focus_on_click=False)
        self._clean_button.clicked.connect(self.clean)
        self._clean_button.set_tip(_('Clean'))

        self._terminate_button = wgtk.IconButton(
            icon='wingide-os-commands-stop', relief=wgtk.RELIEF_NONE,
            border_width=0, focus_on_click=False)
        self._terminate_button.clicked.connect(self.terminate)
        self._terminate_button.set_tip(_('Terminate build'))
        self._terminate_button.setEnabled(False)

        top_hbox = wgtk.HBox(visible=True)
        top_hbox.pack_start(self._build_button, expand=False)
        top_hbox.pack_start(self._clean_button, expand=False)
        top_hbox.pack_start(self._terminate_button, expand=False)

        self._error_list = wgtk.SimpleList(
            [_("File"), _("Line"), _("Column"), _("Message")],
            plain_text=True)
        for i in (0, 1):
            self._error_list.hideColumn(i)
        self._error_list.clicked.connect(self._on_click_error_item)
        wgtk.InitialShow(self._error_list)

        self._error_tab_label = wgtk.QLabel('Errors/Warnings')
        self._error_tab_label.setToolTip('Build errors and warnings')
        self._notebook.append_page(self._error_list, self._error_tab_label)

        self._log = cap_oscommands.CConsoleView(self.fSingletons)
        self._log_tab_label = wgtk.QLabel('   Log   ')
        self._log._fScint.set_wrap_mode(True)
        self._log_tab_label.setToolTip('Log of the last build')
        self._notebook.append_page(self._log.fGtkWidget, self._log_tab_label)

        self._status = wgtk.Label()

        vbox = wgtk.VBox(visible=True)
        vbox.pack_start(top_hbox, expand=False)
        vbox.pack_start(self._status, expand=False)
        vbox.pack_start(self._notebook, expand=True)

        self._SetGtkWidget(vbox)

    python_error_pattern = re.compile(
        r''' ^ Traceback .*? File \s+ " (?P<filename> [^"\n]+?) " , \s+
                line \s+ (?P<line>\d+) .*?
             ^ (?P<message> \w+ Error: .+?) $
        ''', flags=re.X|re.M|re.S)
    cython_clang_gcc_error_pattern = re.compile(
        r''' ^ (?P<filename>[^:\n]+?) : (?P<line>\d+) : (?P<column>\d+)
                : [ ] (?P<message>.+?) $
        ''', flags=re.X|re.M|re.S)
    msvc_error_pattern = re.compile(
        r''' ^
              ([.][\\])?
              (?P<filename>[^(\n]+?) \( (?P<line>\d+) \)
              \s* : \s*
              (?P<message>.+?)
             $
         ''', flags=re.X|re.M|re.S)

    setuptools_build_in_place_action = '{}()'.format(
        setuptools_build_in_place.__name__)

    def project_dir(self):
        my_proj = wingapi.gApplication.GetProject()
        if my_proj is None:
            wingapi.gApplication.ShowMessageDialog(
                title='Setuptools Build',
                text='You need to open a project first.',
                sheet=True)
            return None
        return os.path.dirname(my_proj.GetFilename())

    def execute(self, setup_py_args, postprocess=None):
        """ Execute setup.py with the given command line arguments """
        import proj.project

        projectDir = self.project_dir()
        if projectDir is None:
            return
        my_proj = wingapi.gApplication.GetProject()

        setup_dot_py = os.path.join(projectDir, 'setup.py')
        if not os.path.isfile(setup_dot_py):
            wingapi.gApplication.ShowMessageDialog(
                title='Setuptools Build',
                text='You need to create a file setup.py in your project '
                     'directory first.',
                sheet=True)
            return

        save_mgr = self.fSingletons.fGuiMgr.fSaveMgr
        savable_list = []
        for savable in save_mgr.GetItemsToSave():
            if isinstance(savable.fLocation, location.CUnknownLocation):
                continue # unsaved
            if isinstance(savable, proj.project.CProject):
                continue # .wpr itself
            if savable._fAutoSave is not None and not savable._fAutoSave:
                continue # looks like this one is marked for not auto-saving
            savable_list.append(savable)
        save_mgr.PromptForSave(
            savable_list, initial_prompt=False, can_cancel=False)

        encoding = encoding_utils.kDefaultConsoleOutputEncoding

        # buffer_size = 1 for for line mode
        cmd = (my_proj.GetPythonExecutable(setup_dot_py), "-u", "setup.py")
        self.output = ""
        self._log._Clear()
        self.child_process = spawn.CChildProcess(
            cmd + setup_py_args,
            env=my_proj.GetEnvironment(setup_dot_py),
            child_pwd=projectDir,
            io_encoding=encoding, buffer_size=1)
        self._build_button.setEnabled(False)
        self._clean_button.setEnabled(False)
        self._terminate_button.setEnabled(True)
        self._status.set_text("Running...")

        def received_output(child, text):
            self.output += text
            self._log.AppendOutput(text)
            self._log_tab_label.setStyleSheet("QLabel { color : red; }")

        def terminated(child_process):
            if postprocess is not None:
                postprocess()

            ret = self.child_process.GetExitCode()
            final_msg_tmpl = ('\n\n' + '='*8 +
                              ' %%s: %s '%' '.join(setup_py_args) +
                              '='*8 + '\n')
            final_msg = final_msg_tmpl % (
                'SUCCESS' if ret == 0 else 'FAILED')
            self._log.AppendOutput(final_msg)

            self._log_tab_label.setStyleSheet("QLabel { color : black; }")
            contents = []
            using_msvc = self.output.find('Microsoft Visual Studio') >= 0
            for m in self.python_error_pattern.finditer(self.output):
                contents.append(
                    m.group('filename', 'line') + ('', m.group('message')))
            if using_msvc:
                for m in self.msvc_error_pattern.finditer(self.output):
                    contents.append(
                        m.group('filename', 'line') + ('', m.group('message')))
            else:
                for m in self.cython_clang_gcc_error_pattern.finditer(self.output):
                    contents.append(
                        m.group('filename', 'line', 'column', 'message'))
            self._error_list.set_contents(contents)
            self._build_button.setEnabled(True)
            self._clean_button.setEnabled(True)
            self._terminate_button.setEnabled(False)
            self._status.set_text('')

            if ret != 0 and not contents:
                self._notebook.setCurrentIndex(1)

        def start_failed(child_process, exc):
            self._terminate_button.setEnabled(False)
            self._status.set_text('')
            wingapi.gApplication.ShowMessageDialog(
                title='Setuptools Build',
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

    def build(self):
        """ Build in-place """
        self._error_list.set_contents([])
        self.execute(setup_py_args=("build_ext", "-i"))

    def clean(self):
        """ Remove all files produced by builds so far

            The command clean does remove files from the source directory:
            this is a known limitation of Setuptools. Thus we roll our own
            hand-made heuristic.
        """
        self.execute(setup_py_args=("clean", "-a"),
                      postprocess=self.clean_source_directory)

    def clean_source_directory(self):
        projectDir = self.project_dir()
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
            self._log.AppendOutput(
                "Removing %s\n" % os.path.relpath(f, projectDir))
            os.unlink(f)

    def terminate(self):
        """ Called when the terminate button is clicked """
        self.child_process.Kill()
        self._terminate_button.setEnabled(False)
        self._status.set_text('')

    def _on_click_error_item(self, index):
        """ Called when the user clicks a line in the error list """
        selected = self._error_list.GetSelectedContent()
        if selected is not None and len(selected) != 0:
            filename = os.path.join(self.project_dir(), selected[0][0])
            line = int(selected[0][1])
            col_txt = selected[0][2]
            col = int(col_txt) if col_txt else 0
            doc = wingapi.gApplication.OpenEditor(filename)
            doc.ScrollToLine(lineno=line-1, pos='center', select=1)

# Register this panel type:  Note that this needs to be at the
# very end of the module so that all the classes defined here
# are already available
_CSetuptoolsPanelDefn(wingapi.gApplication.fSingletons)


