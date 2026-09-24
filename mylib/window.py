#!/usr/bin/env python
"""get.py's live acquisition window: builds the GUI from the board .ini's
[code] section (menubar/panel1/lcd/figs), drives the Start/Stop/Calibrate/
Mark buttons, and refreshes the plot + LCD readouts on a timer."""

import platform
import sys

from PyQt5.QtCore import QTimer
from PyQt5.QtGui import QFont, QIcon
from PyQt5.QtWidgets import (QDateEdit, QHBoxLayout, QLabel, QLineEdit,
                             QMainWindow, QStatusBar, QStyle, QVBoxLayout,
                             QWidget)
# QDateEdit/QIcon/QLineEdit/QStyle look unused here, but board .ini [code]
# sections (subject_template, menubar, window_setting, ...) exec()/eval()
# against this module's globals() and construct them by bare name -- keep
# them importable.

import mylib.Qtutils as Qtu
import mylib.utils as utils
from mylib.debug_utils import debug_print
from mylib.i18n import t
from mylib.sync import SyncListener

font_family_name = {
    'Windows': 'Yu Gothic',
    'Linux': 'IPAexGothic',
    'Darwin': 'Hiragino Maru Gothic Pro'}


class ApplicationWindow(QMainWindow):
    def __init__(self, rcv, args, win_index=0):
        super().__init__()
        self.rcv, self.args, self.win_index = rcv, args, win_index
        self.code = rcv.code
        self.title = rcv.p.env_set['title']
        self.board = self.rcv.board
        self.setFont(QFont(font_family_name[platform.system()]))  # Font setting
        # Opt-in "start/stop together" listener (see mylib/sync.py and
        # sync_trigger.py) -- off by default so a plain `python get.py`
        # behaves exactly as before.
        self.sync = SyncListener(label=self.title) if getattr(args, 'sync', False) else None
        if self.sync:
            self.sync.triggered.connect(self.on_sync_command)
        self.initUI()

    def initUI(self):
        exec(self.code['window_setting'], globals(), locals())   # Additional window setting
        self.setWindowTitle(self.title)                          # title setting
        # Status bar setting
        self.status = QStatusBar()
        self.setStatusBar(self.status)
        self.status_label = QLabel('')
        self.status.addPermanentWidget(self.status_label)
        self.cp_label = QLabel('')
        self.status.addWidget(self.cp_label)
        # Menu bar setting
        exec(self.code['menubar'], globals(), locals())                  # menubar setting
        #
        if self.rcv.style:
            self.setStyleSheet(self.rcv.style.replace('256px', '32px'))  # StyleSheet setting
        self.initCanvas()                                                # Canvas initialize
        self.panel1 = eval(self.code['panel1'], globals(), locals())     # panel1 setting
        l_panel1 = Qtu.setWidQVBox(self.panel1)
        self.lcd = eval(self.code['lcd'], globals(), locals())        # lcd panel setting
        l_lcd = Qtu.setWidQGrid(self.lcd, columnstretch=[1, 3, 3])
        main_canvas = QWidget()
        main_canvas.setLayout(Qtu.setQHBoxLayout([                       # Main LAYOUT setting
            [Qtu.setWidQHBox([self.canvas]), 10],                        # Canvas (Figures)
            [Qtu.setQVBoxLayout([l_panel1, l_lcd, 1]), 1]                # Panels
        ]))
        self.setCentralWidget(main_canvas)                               # set QMainWindow

        # Size the window to fit the screen -- done here
        from PyQt5.QtWidgets import QApplication
        screen = QApplication.primaryScreen()
        if screen is not None:
            sg = screen.availableGeometry()
            w = int(sg.width() * 0.75)
            h = int(sg.height() * 0.75)
            self.resize(w, h)                          # resize the ApplicationWindow itself
        # Center it on screen, then stagger by win_index so multiple
        # simultaneously-connected boards (each its own process/window) don't
        # land exactly on top of each other; a single board (win_index=0)
        # still lands exactly centered, as before. Clamped to available
        # screen geometry so the cascade can't push a window off-screen.
            base_x = sg.x() + (sg.width() - w) // 2
            base_y = sg.y() + (sg.height() - h) // 2
            step = 32
            max_dx = max(sg.x() + sg.width() - w - base_x, 0)
            max_dy = max(sg.y() + sg.height() - h - base_y, 0)
            self.move(base_x + min(step * self.win_index, max_dx),
                      base_y + min(step * self.win_index, max_dy))
            debug_print(self.args, f'screen={sg.width()}x{sg.height()}, win={w}x{h}, '
                                    f'win_index={self.win_index}')

        # QTimer setting (allows the figure to be redrawn at a fixed interval)
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.update)
        self.timer.setInterval(0)

        if self.args.fullscreen:
            self.showFullScreen()                      # Fullscreen or not
        self.show()                                                      # Window show

    def initCanvas(self):
        figs = eval(self.code['figs'], globals(), locals())
        self.figure = Qtu.FigureQtPG(self.board, figs, self.args)
        self.canvas = self.figure.win    # ← pg.GraphicsLayoutWidget
        self.canvas.setParent(self)

    def update(self):
        first_last_data, peak_interval = self.figure.update(self.rcv.stream)
        exec(self.code['lcd_update'], globals(), locals())
        # Board.went_idle is set once by the reader thread (see
        # communicate.py's get_data_no_write()/get_data_and_write()) the
        # moment the board is first found to have gone quiet. Always
        # consumed here so a stale flag can never carry over into a later,
        # unrelated session; only surfaced as a status message during
        # caliBrate, since that's the one mode where "went quiet" means
        # "finished" rather than "disconnected".
        if self.board.went_idle:
            self.board.went_idle = False
            if self.marker == b'c':
                self.status_label.setText(t('window.status_calib_done'))
                self.status_label.setStyleSheet("QLabel { color : blue; }")

    # Start plotting (Qt)
    def start_animation(self):
        self.timer.start()

    # reset (Qt)
    def reset(self):
        self.rcv.stop_running()              # Send 'r' (reset)i.e. Stop to Board
        self.board.loop_th = False
        if self.rcv.init_flag:
            self.timer.stop()
        # th.join() itself correctly waits until the read thread has actually
        # stopped, so the fixed 2-second sleep here used to be unnecessary
        # extra delay (adding at least 2 extra seconds to every Stop/Quit).
        if hasattr(self.rcv, 'th'):
            self.rcv.th.join()
            print(t('window.reset_stop_thread'))
        # File closing ... must run after the thread has been stopped.
        # If start_running() raises (e.g. from connect_serial()) and fails,
        # write_flag can end up True while self.rcv.file was never created
        # (start_read_thread() was never reached). Without the hasattr guard,
        # the next Stop/Quit would crash here again.
        if self.rcv.write_flag and hasattr(self.rcv, 'file'):
            self.rcv.file.fwrite.close()
        # Open, write, and close the checkpoint file
        if self.rcv.write_flag and hasattr(self.rcv, 'file') and self.rcv.init_flag and len(
                self.rcv.p.time['check_points']) != 0:
            print(t('window.exec_write_close_cpt'))
            self.rcv.file.write_close_cpt(self.rcv.p)
            for no, val in enumerate(self.rcv.p.time['check_points']):
                print(t('window.check_time', no=no + 1, val=val))

        self.rcv.p.time['check_points'] = []
        self.board.loop_th = True
        self.cp_label.setText('')

    def on_subject_button(self):
        if not hasattr(self, 'subject'):
            self.subject = {}
        templ = eval(self.code['subject_template'])
        if 'before_subject_window' in self.code:
            exec(self.code['before_subject_window'], globals(), locals())  # Pre-Processing
        qDia = Qtu.setQDialog(self.subject, self.args, template=templ,
                              title=t('window.subject_dialog_title'), fixedwidth=200)
        qDia.exec_()
        debug_print(self.args, f'{qDia.result=}')
        # Check subject changed?
        if self.subject == qDia.result:
            return
        else:
            self.subject = qDia.result
        self.rcv.set_subject_info(qDia.result)
        if 'after_subject_window' in self.code:
            exec(self.code['after_subject_window'], globals(), locals())  # Post-Processing
        debug_print(self.args, f'{self.subject=}')

    def on_param_setting_button(self):
        templ = eval(self.code['param_setting_template'])
        if 'before_param_setting_window' in self.code:
            exec(self.code['before_param_setting_window'], globals(), locals())  # Pre-Processing
        qDia = Qtu.setQDialog(
            self.rcv.p.env_set,
            self.args,
            template=templ,
            title=t('window.param_dialog_title'),
            fixedwidth=400)
        qDia.exec_()
        if self.rcv.p.env_set == qDia.result:
            return None           # Check changed or not?
        self.on_stop_button()
        self.rcv.change_env_set(qDia.result)
        if 'after_param_setting_window' in self.code:
            exec(self.code['after_param_setting_window'], globals(), locals())  # Post-Processing
        debug_print(self.args, f'{self.rcv.p.env_set=}')

    def on_test_button(self):
        self.marker = b's'
        try:
            self.reset()
            self.rcv.init_flag = True
            self.rcv.write_flag = False
            self.status_label.setText(t('window.status_test'))
            self.status_label.setStyleSheet("QLabel { color : black; }")
            self.rcv.start_running(self.marker)
            self.start_animation()
        except RuntimeError as exc:
            self._show_connection_error(exc)

    def on_start_button(self):
        self.marker = b's'
        try:
            self.reset()
            self.rcv.init_flag = True
            self.rcv.write_flag = True
            self.status_label.setText(t('window.status_run'))
            self.status_label.setStyleSheet("QLabel { color : red; }")
            self.rcv.start_running(self.marker)
            self.start_animation()
        except RuntimeError as exc:
            self._show_connection_error(exc)

    def on_checkpoint_button(self):
        if self.rcv.init_flag:
            self.rcv.check_points()
            self.cp_label.setText(self.rcv.check_point_txt)
        else:
            self.cp_label.setText(t('window.status_push_after_running'))

    def on_temperature_query(self):
        """No button -- only reachable via the 'temp' sync command (see
        scripts/calibrate_timing.py). Deliberately does nothing while a
        board is connected but not initialized (self.rcv.init_flag),
        same guard as on_checkpoint_button()."""
        if self.rcv.init_flag:
            self.rcv.query_temperature()

    def on_calib_button(self):
        self.marker = b'c'
        try:
            self.reset()
            self.rcv.init_flag = True
            self.rcv.write_flag = False
            self.status_label.setText(t('window.status_calib'))
            self.status_label.setStyleSheet("QLabel { color : green; }")
            self.rcv.start_running(self.marker)
            self.start_animation()
        except RuntimeError as exc:
            self._show_connection_error(exc)

    def on_stop_button(self):
        self.status_label.setText(t('window.status_stopped'))
        self.status_label.setStyleSheet("QLabel { color : orange; }")
        try:
            self.reset()
        except RuntimeError as exc:
            self._show_connection_error(exc)

    def _show_connection_error(self, exc):
        """A board write failed (see Board._write_marker()): print the
        already-translated, actionable message and surface it in the
        status bar too, instead of letting it crash the button-click slot
        uncaught with a raw traceback and no visible GUI feedback."""
        print(exc)
        self.status_label.setText(str(exc))
        self.status_label.setStyleSheet("QLabel { color : red; }")

    def on_sync_command(self, command):
        """Handles a run/test/calibrate/stop/mark/quit/temp trigger from
        sync_trigger.py (see mylib/sync.py); only bound when this window
        was launched with -sync. Named to match this board's own button
        labels ('Run'/'Test'/'caliBrate'/'Stop'/'mArk', see e.g.
        DPG_X95840W.ini's panel1), not the underlying on_*_button() method
        names. 'calibrate' is broadcast the same as every other command --
        a board whose firmware doesn't implement it (no caliBrate button
        in its own .ini) just never replies to marker b'c', which
        connect_serial() already turns into a clean, non-crashing
        RuntimeError/status message after its normal retry/timeout, not a
        hang or corrupted state. 'temp' (no matching button; used by
        scripts/calibrate_timing.py) has no such retry -- see
        Board.query_temperature()'s own timeout/None-on-failure handling."""
        if command == 'run':
            self.on_start_button()
        elif command == 'test':
            self.on_test_button()
        elif command == 'calibrate':
            self.on_calib_button()
        elif command == 'stop':
            self.on_stop_button()
        elif command == 'mark':
            self.on_checkpoint_button()
        elif command == 'quit':
            self.on_quit_button()
        elif command == 'temp':
            self.on_temperature_query()

    def on_quit_button(self):
        self.quit(t('window.quit_pressed'))

    def closeEvent(self, event):
        self.quit(t('window.close_pressed'))

    def quit(self, msg):
        if self.sync:
            self.sync.close()
        self.board.ser.write(b"q")  # quit... must run before self.reset()
        self.reset()
        print(t('window.quit_log', msg=msg))
        self.board.ser.close()
        sys.exit(0)
