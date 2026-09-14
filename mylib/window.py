#!/usr/bin/env python
"""get.py's live acquisition window: builds the GUI from the board .ini's
[code] section (menubar/panel1/lcd/figs), drives the Start/Stop/Calibrate/
Mark buttons, and refreshes the plot + LCD readouts on a timer."""

import platform
import sys
import time

from PyQt5.QtCore import QTimer
from PyQt5.QtGui import QFont
from PyQt5.QtWidgets import (QDateEdit, QHBoxLayout, QLabel, QLineEdit,
                             QMainWindow, QStatusBar, QStyle, QVBoxLayout,
                             QWidget)
# QDateEdit/QLineEdit/QStyle look unused here, but board .ini [code] sections
# (subject_template, menubar, ...) exec()/eval() against this module's
# globals() and construct them by bare name -- keep them importable.

import mylib.Qtutils as Qtu
import mylib.utils as utils
from mylib.debug_utils import debug_print
from mylib.i18n import t

font_family_name = {
    'Windows': 'Yu Gothic',
    'Linux': 'IPAexGothic',
    'Darwin': 'Hiragino Maru Gothic Pro'}


class ApplicationWindow(QMainWindow):
    def __init__(self, rcv, args):
        super().__init__()
        self.rcv, self.args = rcv, args
        self.code = rcv.code
        self.title = rcv.p.env_set['title']
        self.board = self.rcv.board
        self.setFont(QFont(font_family_name[platform.system()]))  # Font setting
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

        # ウィンドウサイズをスクリーンに合わせて設定 ← ここで行う
        from PyQt5.QtWidgets import QApplication
        screen = QApplication.primaryScreen()
        if screen is not None:
            sg = screen.availableGeometry()
            w = int(sg.width() * 0.75)
            h = int(sg.height() * 0.75)
            self.resize(w, h)                          # ApplicationWindow自体をresize
        # 画面中央に配置
            self.move(sg.x() + (sg.width() - w) // 2,
                      sg.y() + (sg.height() - h) // 2)
            debug_print(self.args, f'screen={sg.width()}x{sg.height()}, win={w}x{h}')

        # QTimer setting(一定時間ごとの図の更新を可能にする)
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

    # Plot開始(Qt)
    def start_animation(self):
        self.timer.start()

    # reset(Qt)
    def reset(self):
        self.rcv.stop_running()              # Send 'r' (reset)i.e. Stop to Board
        self.board.loop_th = False
        if self.rcv.init_flag:
            self.timer.stop()
        time.sleep(2)
        if hasattr(self.rcv, 'th'):
            self.rcv.th.join()
            print(t('window.reset_stop_thread'))
        # file closing ... threadを止めてから実行すること
        if self.rcv.write_flag:
            self.rcv.file.fwrite.close()
        # check pointsファイルopen&write&close
        if self.rcv.write_flag and self.rcv.init_flag and len(
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
                              title=t('window.subject_dialog_title'))
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
            fixedwidth=360)
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
        self.reset()
        self.rcv.init_flag = True
        self.rcv.write_flag = False
        self.status_label.setText(t('window.status_test'))
        self.status_label.setStyleSheet("QLabel { color : black; }")
        self.rcv.start_running(self.marker)
        self.start_animation()

    def on_start_button(self):
        self.marker = b's'
        self.reset()
        self.rcv.init_flag = True
        self.rcv.write_flag = True
        self.status_label.setText(t('window.status_run'))
        self.status_label.setStyleSheet("QLabel { color : red; }")
        self.rcv.start_running(self.marker)
        self.start_animation()

    def on_checkpoint_button(self):
        if self.rcv.init_flag:
            self.rcv.check_points()
            self.cp_label.setText(self.rcv.check_point_txt)
        else:
            self.cp_label.setText(t('window.status_push_after_running'))

    def on_calib_button(self):
        self.marker = b'c'
        self.reset()
        self.rcv.init_flag = True
        self.rcv.write_flag = False
        self.status_label.setText(t('window.status_calib'))
        self.status_label.setStyleSheet("QLabel { color : green; }")
        self.rcv.start_running(self.marker)
        self.start_animation()

    def on_stop_button(self):
        self.status_label.setText(t('window.status_stopped'))
        self.status_label.setStyleSheet("QLabel { color : orange; }")
        self.reset()

    def on_quit_button(self):
        self.quit(t('window.quit_pressed'))

    def closeEvent(self, event):
        self.quit(t('window.close_pressed'))

    def quit(self, msg):
        self.board.ser.write(b"q")  # quit... 必ず self.reset()の前に実行
        self.reset()
        print(t('window.quit_log', msg=msg))
        self.board.ser.close()
        sys.exit(0)
