#!/usr/bin/env python3
"""
sensor-bridge: グラフ表示モジュール
取得したセンサーデータをリアルタイムで表示する
"""

import argparse
import ast
import copy
import json
import os
import re
import sys
from concurrent.futures import ProcessPoolExecutor
from datetime import datetime

import numpy as np
import pandas as pd
from PyPDF2 import PdfMerger
from PyQt5.QtCore import Qt, QSizeF, QTimer
from PyQt5.QtGui import QIcon, QPainter, QPdfWriter, QPixmap
from PyQt5.QtWidgets import (QApplication, QCheckBox, QFileDialog,
                             QGroupBox, QGridLayout, QLabel, QMainWindow,
                             QMenu, QPushButton, QVBoxLayout, QWidget)

import mylib.i18n as i18n
import mylib.plot_utils as pltutils
from mylib.debug_utils import debug_print
from mylib.i18n import t
from mylib.plot_utils import WaveletParams  # 必要に応じてインポート
from version import __version__


def toStr(filter):
    def _toStr(filter):
        return ';'.join([val[0] + ','.join(str(x) for x in val[1]) for val in filter])

    if isinstance(filter, dict):
        return '\n'.join([f'{key}:{_toStr(val)}' for key, val in filter.items()])
    elif isinstance(filter, list):
        return _toStr(filter)


def parse_filter_string(filter_str):
    history = []
    for item in filter_str.split(','):
        if '[' in item and item.endswith(']'):
            name, args = item.split('[', 1)
            args = ast.literal_eval(f"[{args}")  # 安全にリストとして評価
            history.append([name.strip(), args])
    return history


def merge_filter_and_history(filter_dict, history_dict):
    """defaultのFilterとSignalSmoothingWindowでの操作Historyを1つのdictへ合成する
    （同じKeyはFilterが先、Historyが後の順で連結）。"""
    merged = {}
    all_keys = list(dict.fromkeys(list(filter_dict.keys()) + list(history_dict.keys())))
    for key in all_keys:
        merged[key] = []
        if key in filter_dict:
            merged[key].extend(filter_dict[key])  # filterが先
        if key in history_dict:
            merged[key].extend(history_dict[key])  # historyが後
    return merged


graph_type = [
    # tooltip欄はi18nカタログのkey。setToolTip側でt()を呼ぶ（--lang解決前にこのリストが
    # 評価されるため、ここで直接t()すると常に起動時点の言語になってしまう）。
    ('Timeseries', lambda obj: obj.current_data, ['plot'], 'plot.tt.timeseries'),
    # 'freq': X軸がTimeではなくFreq.(Hz)。Mark/Shift time等のTime系操作は無関係。
    ('PowerSpectra', lambda obj: obj.ps_data, ['plot', 'freq'], 'plot.tt.powerspectra'),
    ('Scalogram', lambda obj: obj.wv_data, ['image', 'wavelet'],
     'plot.tt.scalogram'),
    ('Energy', lambda obj: obj.energy, ['plot', 'wavelet'],
     'plot.tt.energy'),
    ('Energy(cumlative sum)', lambda obj: pltutils.calc_cumsum(obj.energy),
     ['plot', 'wavelet'], 'plot.tt.energy_cumsum'),
    ('Energy(m-avg)', lambda obj: pltutils.do_ma(obj.energy, obj.args.mvaverage),
     ['plot', 'wavelet'], 'plot.tt.energy_mavg'),
    ('Power', lambda obj: obj.power, ['plot', 'wavelet'],
     'plot.tt.power'),
    ('Power(m-avg)', lambda obj: pltutils.do_ma(obj.power, obj.args.mvaverage),
     ['plot', 'wavelet'], 'plot.tt.power_mavg'),
    ('max power freq.', lambda obj: obj.max_power_freq, ['plot', 'wavelet'],
     'plot.tt.max_power_freq'),
    ('max power BPM', lambda obj: obj.max_power_bpm, ['plot', 'wavelet'],
     'plot.tt.max_power_bpm'),
    ('pv_Frequency', lambda obj: obj.pv_freq, ['plot'], 'plot.tt.pv_freq'),
    ('pv_Amplitude', lambda obj: obj.pv_amp, ['plot'], 'plot.tt.pv_amp'),
    ('pv_Energy', lambda obj: obj.pv_energy, ['plot'], 'plot.tt.pv_energy'),
    ('pv_Power', lambda obj: obj.pv_power, ['plot'], 'plot.tt.pv_power'),
    ('pv_Frequency(m-avg)', lambda obj: pltutils.do_ma(obj.pv_freq, obj.args.mvaverage),
     ['plot'], 'plot.tt.pv_freq_mavg'),
    ('pv_Amplitude(m-avg)', lambda obj: pltutils.do_ma(obj.pv_amp, obj.args.mvaverage),
     ['plot'], 'plot.tt.pv_amp_mavg'),
    ('pv_Energy(m-avg)', lambda obj: pltutils.do_ma(obj.pv_energy, obj.args.mvaverage),
     ['plot'], 'plot.tt.pv_energy_mavg'),
    ('pv_Power(m-avg)', lambda obj: pltutils.do_ma(obj.pv_power, obj.args.mvaverage),
     ['plot'], 'plot.tt.pv_power_mavg'),
]


def decompose_graph_type(graph_type):
    name = [f"{k}:{name}" for k, (name, _, _, _) in enumerate(graph_type)]
    func = {k: func for k, (_, func, _, _) in enumerate(graph_type)}
    tooltip = {f"{k}:{name}": tp for k, (name, _, _, tp) in enumerate(graph_type)}
    # 'image' を含む index を取得
    image = [k for k, (_, _, modes, _) in enumerate(graph_type) if 'image' in modes]
    # 'wavelet' を含む index を取得
    wavelet = [k for k, (_, _, modes, _) in enumerate(graph_type) if 'wavelet' in modes]
    # 'freq' (X軸がTimeでない) を含む index を取得
    freq = [k for k, (_, _, modes, _) in enumerate(graph_type) if 'freq' in modes]
    return (name, func, image, wavelet, freq, tooltip)


(graph_name, graph_func, image_lst, wavelet_lst, freq_lst,
 graph_tooltip) = decompose_graph_type(graph_type)

graph_lst = {}
graph_lst['Analog_Sensor'] = ['Timeseries', 'PowerSpectra', 'Scalogram']
graph_lst['SHT35'] = ['Timeseries', 'PowerSpectra', 'Scalogram']
graph_lst['LIS3DH'] = ['Timeseries', 'PowerSpectra', 'Scalogram']


def resolve_graph_visibility(board_prog, graph_lst, graph_name):
    """board_prog(Boardのtitle)に対応するgraph_lstのEntryを探し、graph_nameの各要素が
    そのBoardで表示可能かどうかのBoolean Listを返す（該当Entryが無ければ全てTrue）。"""
    matched_key = next((k for k in graph_lst if k in board_prog), None)
    if matched_key is None:
        return [True] * len(graph_name)
    return [name.split(':')[1] in graph_lst[matched_key] for name in graph_name]


class MainWindow(QMainWindow):
    def __init__(self, filename, args):
        super().__init__()
        self.args = args
        self.initUI(args)
        if filename:
            self.prepare_data(filename)  # Data 読み込み
            self.variable_parts()
        else:
            self.num_plots = 1
            self.dirname = default_dir

        # label,plots,p_base(win内配置)
        self.plots = pltutils.InitPlots(self.win, self.num_plots)
        if filename:
            self.update_plot()

    def initUI(self, args):
        # メインウィジェットとレイアウト作成
        main_widget = QWidget()
        layout = QVBoxLayout()
        main_widget.setLayout(layout)
        self.setCentralWidget(main_widget)

        # Control panel LAYOUT
        self.control_layout = QGridLayout()

        # Title label
        self.title_label = QLabel('')

        # label2 & 3
        self.label2 = QLabel('')
        self.label3 = QLabel('')

        # ファイル選択ボタン
        self.file_selection_button = QPushButton(t('plot.gui.open_file'))
        self.file_selection_button.setToolTip(t('plot.gui.open_file_tip'))
        self.file_selection_button.clicked.connect(self.open_file_select_dialog)

        # Write ボタン
        self.file_write_button = QPushButton(t('plot.gui.save_graph'))
        self.file_write_button.setToolTip(t('plot.gui.save_graph_tip'))
        self.file_write_button.clicked.connect(self.open_file_write_dialog)

        # Signal Smoothingボタン
        self.smoothing_window = None   # Smoothing windowを保持する変数
        self.smoothing_button = QPushButton(t('plot.gui.smoothing'))
        self.smoothing_button.setToolTip(t('plot.gui.smoothing_tip'))
        self.smoothing_button.clicked.connect(self.open_smoothing_window)

        # Graph選択ボタン
        self.graph_actions = {}
        self.graph_sel_button = QPushButton(t('plot.gui.select_graph'), self)
        self.graph_sel_button.setToolTip(t('plot.gui.select_graph_tip'))
        self.graph_sel_menu = QMenu(self)        # メニューを作成
        self.graph_sel_menu.setToolTipsVisible(True)
        for name in graph_name:
            self.graph_actions[name] = self.graph_sel_menu.addAction(f'{name}', self.select_graph)
            self.graph_actions[name].setToolTip(t(graph_tooltip[name]))
        self.graph_sel_button.setMenu(self.graph_sel_menu)  # ボタンにメニューを設定

        # INFO button
        self.info_window = None     # Information windowを保持する変数
        self.info_button = QPushButton(t('plot.gui.info'))
        self.info_button.setToolTip(t('plot.gui.info_tip'))
        self.info_button.clicked.connect(self.open_info_window)

        # Quit button
        self.quit_button = QPushButton(t('plot.gui.quit'), self)
        self.quit_button.setToolTip(t('plot.gui.quit_tip'))
        self.quit_button.clicked.connect(self.closeApp)

        # Port selection (GroupBox & checkbox)
        self.port_selection = QGroupBox(t('plot.gui.select_port'))

        # Peaks描画
        self.peaks_check = QCheckBox('Peak')
        self.peaks_check.setToolTip(t('plot.gui.peak_tip'))
        if self.args.peaks:
            self.peaks_check.setChecked(True)

        # Mark(checkpoint)描画
        self.mark_check = QCheckBox(t('plot.gui.mark_check'))
        self.mark_check.setToolTip(t('plot.gui.mark_tip'))
        if self.args.vline:
            self.mark_check.setChecked(True)
        self.mark_check.stateChanged.connect(self.hide_show_plot)

        # Time shift  (From Mark selection)
        self.time_shift = QGroupBox(t('plot.gui.select_mark'))
        self.time_shift.setToolTip(t('plot.gui.time_shift_tip'))
        self.peaks_check.stateChanged.connect(self.hide_show_plot)

        # Derivatives
        self.derivatives = QGroupBox(t('plot.gui.derivatives'))
        self.derivatives.setToolTip(t('plot.gui.derivatives_tip'))
        if self.derivatives.layout():
            QWidget().setLayout(self.derivatives.layout())  # 既存の設定を削除
        derivatives_layout, self.derivatives_checkboxes = pltutils.mk_checkbox(
            ['1st', '2nd'], self.hide_show_plot, isChecked=False)
        self.derivatives.setLayout(derivatives_layout)

        # Time shift (Set value (sec))
        self.shift_layout, self.shift_input = pltutils.create_shift_input()
        self.shift_input.textChanged.connect(self.update_shift_value)

        # Moving Averaga Slider
        self.mv_layout, self.mv_slider = pltutils.create_labeled_slider(
            t('plot.gui.mv_window_size'), 1, 120, 20, 1)
        self.mv_slider.valueChanged.connect(self.control_moving_average)
        if self.args.mvaslider:
            self.mv_layout.show()
        else:
            self.mv_layout.hide()

        # Wavelet parameters setting

        # LT line(from external excel) plotting
        self.LT_check = QCheckBox('LT')
        self.LT_check.setToolTip(t('plot.gui.lt_tip'))
        if self.args.LT:
            self.LT_check.setChecked(True)
        self.LT_check.stateChanged.connect(self.hide_show_plot)

        # PRE lines(from external excel) plotting
        self.PRE_check = QCheckBox('PRE')
        self.PRE_check.setToolTip(t('plot.gui.pre_tip'))
        if self.args.PRE:
            self.PRE_check.setChecked(True)
        self.PRE_check.stateChanged.connect(self.hide_show_plot)

        # コントロールレイアウトを追加
        # row(行), column(列), rowspan(行方向セル数), colspan(列方向セル数)
        widgets = [
            (self.title_label, 0, 0, 1, 7),
            (self.file_selection_button, 1, 0),
            (self.mv_layout, 2, 0, 1, 5),
            (self.label2, 2, 6, 1, 5),
            (self.file_write_button, 1, 1),
            (self.smoothing_button, 1, 2),
            (self.graph_sel_button, 1, 3),
            (self.peaks_check, 1, 4),
            (self.mark_check, 1, 5),
            (self.LT_check, 1, 6),
            (self.PRE_check, 1, 7),
            (self.port_selection, 0, 8, 2, 1),
            (self.time_shift, 0, 9, 2, 1),
            (self.shift_layout, 0, 10, 2, 1),
            (self.derivatives, 0, 11, 2, 1),
            (self.label3, 0, 12, 1, 2),
            (self.info_button, 1, 12),
            (self.quit_button, 1, 13)
        ]
        for wid in widgets:
            self.control_layout.addWidget(*wid)
        layout.addLayout(self.control_layout)

        # グラフウィジェット作成
        _, self.win = pltutils.init_pg('')
        layout.addWidget(self.win)

        if self.args.fullscreen:        # ウィンドウをフルスクリーンに
            self.showFullScreen()
        else:
            self.resize(2048, 1600)  # ウィンドウサイズ設定
            self.move(200, 200)  # ウィンドウ位置設定

        self.win.clear()         # 既存のグラフをクリア

    def keyPressEvent(self, event):
        if event.key() == Qt.Key_Q and event.modifiers() & Qt.ControlModifier:
            self.close()
        if event.key() == Qt.Key_I and event.modifiers() & Qt.ControlModifier:
            self.open_info_window()
        if event.key() == Qt.Key_F and event.modifiers() & Qt.ControlModifier:
            self.open_smoothing_window()
        if event.key() == Qt.Key_O and event.modifiers() & Qt.ControlModifier:
            self.open_file_select_dialog()
        if event.key() == Qt.Key_S and event.modifiers() & Qt.ControlModifier:
            self.open_file_write_dialog()
        if event.key() == Qt.Key_G and event.modifiers() & Qt.ControlModifier:
            self.graph_sel_button.showMenu()

    def prepare_data(self, filename):
        self.basename = os.path.basename(filename)  # ファイル名のみ取得
        self.dirname = os.path.dirname(filename)
        self.fname, _ = os.path.splitext(filename)
        self.args.filename = filename
        self.data = pltutils.ReadData(self.args)    # data読込み
        self.board_prog = self.data.header.__dict__['env_set']['title']

        result = resolve_graph_visibility(self.board_prog, graph_lst, graph_name)
        for name, flag in zip(graph_name, result):
            self.graph_actions[name].setVisible(flag)

        self.cpt_list = self.data.cpt_list
        self.current_data = copy.deepcopy(self.data.data0)   # original PlotData
        # 前もってfilter(default:'default_filter.json'->ex. LowPass filter & DownSampling)
        self.filter, self.current_data.data = pltutils.apply_default_filters(
            self.current_data.data, default_filter if self.args.smoothing else None, self.cpt_list)

        self.num_plots = self.current_data.num_data
        self.cpt_lines, self.LT_lines, self.PRE_lines = [], [], []

        if self.args.header:
            headerfile = f'{self.fname}_header.xlsx'
            if not os.path.exists(headerfile):
                pltutils.save_header(self.data.header, headerfile)

        self.wl_params = build_wavelet_params(self.args)
        # 非同期でwavelet計算
        executor = ProcessPoolExecutor()
        self.future = executor.submit(
            pltutils.do_wavelet_transform,
            self.current_data,
            self.wl_params)

        # compute PowerSpectra
        self.ps_data = pltutils.do_power_spectrum(self.current_data)

        # compute freq & amp from peaks & valleys
        self.pv_freq, self.pv_amp, self.pv_energy, self.pv_power = pltutils.do_compute_time_varying_freq_amp(
            self.current_data)

        self.selected_graph = f'{graph_name[int(self.args.graph)]}'
        self.time_offset = 0
        self.add_shift = 0  # 数値を格納する変数
        self.window_title = f'{self.basename}   {self.data.title}'  # Window Title setting
        self.setWindowTitle(self.window_title)

    def variable_parts(self):
        # Port Selection
        if self.port_selection.layout():
            QWidget().setLayout(self.port_selection.layout())  # 既存の設定を削除
        if self.num_plots > 1:   # For only 1port -> hide
            checkboxes_layout, self.checkboxes = pltutils.mk_checkbox(
                range(self.num_plots), self.hide_show_plot)
            self.port_selection.setLayout(checkboxes_layout)
        else:
            self.checkboxes = None
        self.port_selection.setVisible(self.num_plots > 1)  # For only 1port -> hide

        # Check points Selection(For time shift)
        if self.time_shift.layout():
            QWidget().setLayout(self.time_shift.layout())  # 既存の設定を削除
        if len(self.data.cpt_list) > 0:
            sel = 1 if self.args.timeshift1 else 0
            radiobuttons_layout, self.button_group = pltutils.mk_radiobuttons(
                len(self.data.cpt_list) + 1, sel, self.hide_show_plot)
            self.time_shift.setLayout(radiobuttons_layout)
        else:
            self.button_group = None

        # Mark Button Visible or Invisible
        visible = len(self.data.cpt_list) > 0
        self.mark_check.setVisible(visible)
        self.time_shift.setVisible(visible)

        # LT & PRE Button Visible or Invisible
        self.LT_check.setVisible(bool(self.data.LT_dict))
        self.PRE_check.setVisible(bool(self.data.PRE_dict))

        # Information window
        if self.info_window:                # Information Windowが開いていれば
            self.info_window.close()    # Windowを閉じる
            self.info_window = None   # 参照を削除
            self.open_info_window()    # Windowを開く

    def open_smoothing_window(self):
        if not self.smoothing_window:
            self.changed_data = copy.deepcopy(self.current_data)
            print(f'{self.cpt_list=}, {len(self.cpt_list)=}')
            self.smoothing_window = pltutils.SignalSmoothingWindow(
                self.plots.plts, self.changed_data, self.cpt_list)
            # Signal を connect（データ取得）
            self.smoothing_window.execTriggered.connect(self.on_smoothing_finished)
            # ウィンドウを閉じたときに参照を削除
            self.smoothing_window.setAttribute(Qt.WA_DeleteOnClose)
            self.smoothing_window.destroyed.connect(
                lambda: setattr(self, "smoothing_window", None))
            self.smoothing_window.show()

    def on_smoothing_finished(self, data):
        print(t('plot.exec_received_data'), f"{data['history']=}")
        self.current_data = copy.deepcopy(data['filtered'])  # 取得したデータで更新
        self.history = data['history']  # Get filter history
        self.filter = self.merge_filter_and_history()  # merge

        self.selected_graph = '0:Timeseries'
        self.update_plot()
        # 非同期でwavelet計算
        executor = ProcessPoolExecutor()
        self.future = executor.submit(
            pltutils.do_wavelet_transform,
            self.current_data,
            self.wl_params)

    def open_info_window(self):
        """別ウィンドウを開き、閉じたときに参照を削除"""
        if self.info_window is None:
            self.info_window = pltutils.TabWindow(
                self.data.header, self.current_data)  # self.data.data0)
            # ウィンドウを閉じたときに参照を削除
            self.info_window.setAttribute(Qt.WA_DeleteOnClose)
            self.info_window.destroyed.connect(lambda: setattr(self, "info_window", None))
            self.info_window.show()

    def closeEvent(self, event):
        # InfoWindowを閉じる
        if self.info_window and self.info_window.isVisible():
            self.info_window.close()
        # SignalSmoothingWindowを閉じる
        if self.smoothing_window and self.smoothing_window.isVisible():
            self.smoothing_window.close()
        # MainWindowを閉じる
        event.accept()

    def closeApp(self):
        self.close()

    def open_file_select_dialog(self):
        options = QFileDialog.Options()  # options |= QFileDialog.DontUseNativeDialog
        # ファイル選択ダイアログを開く
        file_path, _ = QFileDialog.getOpenFileName(
            self, "Select .dat File", self.dirname, "DAT Files (*.dat)", options=options)
        if file_path:
            print(t('plot.selected_file', path=file_path))
            self.prepare_data(file_path)
            self.variable_parts()
            self.win.clear()      # 既存のグラフをクリア
            self.plots.remove_right_axes()  # plts_right 削除
            self.plots = pltutils.InitPlots(
                self.win, self.num_plots)  # label, plots, p_base(win内配置)
            self.update_plot()    # プロット更新
            # SignalSmoothingWindow
            if self.smoothing_window:          # SignalSmoothingWindowが開いていれば
                self.smoothing_window.close()  # Windowを閉じる
                self.smoothing_window = None   # 参照を削除
                self.open_smoothing_window()   # Windowを開く

    def open_file_write_dialog(self):
        excelfile = f'{self.fname}_G{self.graph_id:02}.xlsx'
        mark_points = self.data.header.time['check_points']
        if self.data.LT_dict is not None and self.data.PRE_dict is not None:
            note_df = pd.Series({**self.data.LT_dict, **self.data.PRE_dict}).T
        else:
            note_df = None

        if self.graph_id in image_lst:    # ImageItem (Scalogram)
            self.image_data.to_excel(excelfile, self.filter, mark_points, note_df)
        else:
            self.plot_data.to_excel(excelfile, self.filter, mark_points, note_df)

    def control_moving_average(self, value):
        self.mavg_data = pltutils.do_ma(self.plot_data, value)
        if hasattr(self, 'mavg_curves'):
            for cur, (x, y) in zip(self.mavg_curves, self.mavg_data.data):
                print(f'{len(x)=}')
                if len(x) == 0:
                    self.close()
                    return
                else:
                    cur.setData(x - self.time_offset - self.add_shift, y)
        else:
            self.mavg_curves = pltutils.add_timeseries(self.plots, self.mavg_data)
        print(f'{value=}')

    def hide_show_plot(self):
        if self.args.timeshift1 and len(self.data.cpt_list) > 0:
            self.time_offset = self.data.cpt_list[0]
        if self.time_shift.layout():
            selected_cpt = self.button_group.checkedId()
            self.time_offset = self.data.cpt_list[selected_cpt - 1] if selected_cpt > 0 else 0
        # For Timeseries
        if hasattr(self, 'curves'):
            # ✅ RegionManagerにシフト量を伝える
            self.region_mgr.set_x_shift(self.time_offset + self.add_shift)
            for cur, (x, y) in zip(self.curves, self.plot_data.data):
                if len(x) == 0:
                    self.close()
                    return
                else:
                    x_shifted = x - self.time_offset - self.add_shift
                    x_d, y_d = pltutils.decimate_fixed(x_shifted, y)  # ✅ 間引き
                    cur.setData(x_d, y_d)

            x0 = self.plot_data.data[0][0] - self.time_offset - self.add_shift
            x_d0, y_d0 = pltutils.decimate_fixed(x0, self.plot_data.data[0][1])
            self.p_base_plot.setData(x_d0, y_d0)

        # For Derivatives
        if hasattr(self, 'derivative_curves'):
            for derivative_curve, derivative_data in zip(
                    self.derivative_curves, self.derivative_data):
                for cur, (x, y) in zip(derivative_curve, derivative_data):
                    if len(x) == 0:
                        self.close()
                        return
                    else:
                        x_shifted = x - self.time_offset - self.add_shift
                        x_d, y_d = pltutils.decimate_fixed(x_shifted, y)  # ✅ 間引き
                        cur.setData(x_d, y_d)

            visible_all = False
            for curves, (lab, cb) in zip(self.derivative_curves, self.derivatives_checkboxes):
                visible = cb.isChecked()
                visible_all |= visible
                for curve in curves:
                    curve.setVisible(visible)
            self.plots.toggle_right_axis(visible_all)

        # For Peaks
        if hasattr(self, 'peaks'):
            for cur, (x, y) in zip(self.peaks, self.peaks_data.data):
                cur.setData(x - self.time_offset - self.add_shift, y)  # cur.yData)
            for cur in self.peaks:
                cur.setVisible(self.peaks_check.isChecked())
        if hasattr(self, 'valleys'):
            for cur, (x, y) in zip(self.valleys, self.valleys_data.data):
                cur.setData(x - self.time_offset - self.add_shift, y)  # cur.yData)
            for cur in self.valleys:
                cur.setVisible(self.peaks_check.isChecked())

        # For Images
        if hasattr(self, 'img'):
            for im, (t, f, r) in zip(self.img, self.wv_data.data + [self.wv_data.data[-1]]):
                pltutils.shift_image(im, t, f, self.time_offset + self.add_shift)

        self.plots.show_or_hide(self.win, self.checkboxes)
        self.plot_vertical_lines()  # 縦線を引く
        self.show_filter_label()    # Filter label

    def plot_vertical_lines(self):
        def update_lines(check_box, line_list_name, data_source, plot_func):
            # チェックが有効なら線を更新、無効なら削除だけ
            lines = getattr(self, line_list_name, [])
            for (p, l) in lines:
                p.removeItem(l)
            setattr(self, line_list_name, [])

            if check_box and check_box.isChecked():
                all_plots = self.plots.plts + [self.plots.p_base]
                new_lines = plot_func(all_plots, data_source)
                setattr(self, line_list_name, new_lines)

        print(t('plot.selected_graph', graph=self.selected_graph))
        # 'PowerSpectra' の時は縦線は非表示
        if 'PowerSpectra' not in self.selected_graph:
            # At Mark points
            update_lines(
                self.mark_check,
                'cpt_lines',
                self.data.cpt_list,
                lambda plots,
                data: pltutils.plot_cpt_lines(
                    plots,
                    data,
                    self.time_offset +
                    self.add_shift))
            # PRE (from Excel)
            update_lines(
                self.PRE_check,
                'PRE_lines',
                self.data.PRE_dict,
                pltutils.plot_additional_lines)
            # LT (from Excel)
            update_lines(
                self.LT_check,
                'LT_lines',
                self.data.LT_dict,
                pltutils.plot_additional_lines)

        label_parts = []
        # LT 表示
        lt_dict = getattr(self.data, 'LT_dict', None)
        if self.LT_check and isinstance(lt_dict, dict) and lt_dict:
            key, val = next(iter(lt_dict.items()))
            label_parts.append(f"{key}={val}(sec)")
        # PRE 表示
        pre_dict = getattr(self.data, 'PRE_dict', None)
        if self.PRE_check and isinstance(pre_dict, dict):
            pre_parts = [f"{k}={v}" for k, v in pre_dict.items() if not np.isnan(v)]
            if pre_parts:
                label_parts.append(', '.join(pre_parts))
        # 表示更新
        label2_text = '; '.join(label_parts)
        self.label2.setText(label2_text)
        self.label2.setToolTip(t('plot.gui.label2_tip') if label2_text else '')

    def show_filter_label(self):
        if all(not v for v in self.filter.values()):  # すべて[]ならば
            self.label3.setText('')
            self.label3.setToolTip('')
        else:
            self.label3.setText(f'{toStr(self.filter)}')
            self.label3.setToolTip(t('plot.gui.filters_tip'))

    def merge_filter_and_history(self):
        return merge_filter_and_history(self.filter, self.history)

    def update_plot(self):
        # graphの種類に応じて描画
        self.graph_id = int(re.match(r'^(\d+)\:', self.selected_graph).group(1))
        debug_print(self.args, f'[Debug]{self.graph_id=}, {self.selected_graph=}')
        # future 結果のキャッシュ
        if self.graph_id in wavelet_lst:
            self.wv_data, self.energy, self.power, self.max_power_freq, self.max_power_bpm = self.future.result()

        # PlotItem/ViewBoxを使い回さず、open_file_select_dialog()と同じ手順で毎回作り直す。
        # 過去にPlotItemを使い回すと(特にPowerSpectra/Scalogramのようにcurve/colorbar/
        # imageが入れ替わるとき)"wrapped C/C++ object ... has been deleted"というクラッシュが
        # 再現したため(pyqtgraph/Qtのオブジェクト寿命管理起因、都度作り直すことで回避する)。
        self.win.clear()
        self.plots.remove_right_axes()
        self.plots = pltutils.InitPlots(self.win, self.num_plots)
        if self.graph_id in image_lst:    # ImageItem (Scalogram)
            # 前回がPlotItem系Graphだった場合の残骸を消す(hide_show_plot()のhasattr判定用)。
            for stale in ('curves', 'p_base_plot', 'derivative_curves', 'peaks', 'valleys',
                          'plot_data', 'mavg_curves'):
                if hasattr(self, stale):
                    delattr(self, stale)
            self.derivatives.setVisible(False)  # ImageItem系にはDerivatives(1st/2nd)は無関係
            self.peaks_check.setVisible(False)  # ImageItem系にはPeakも無関係
            self.image_data = graph_func[self.graph_id](self)
            self.plots.set_title(self.image_data.title)
            self.img, self.colorbar, self.region_mgr, self.cross_hair = pltutils.plot_scalogram(
                self.plots, self.image_data)
        else:                        # PlotItem
            # 前回がImageItem系Graphだった場合の残骸を消す(hide_show_plot()のhasattr判定用)。
            for stale in ('img', 'colorbar', 'image_data'):
                if hasattr(self, stale):
                    delattr(self, stale)
            self.derivatives.setVisible(True)
            self.peaks_check.setVisible(True)
            self.plot_data = graph_func[self.graph_id](self)  # self を渡すことで lambda(obj) が使える
            self.plots.set_title(self.plot_data.title)
            self.curves, self.p_base_plot, self.region_mgr, self.cross_hair = pltutils.plot_timeseries(
                self.plots, self.plot_data)
            # Moving Average curves
            if hasattr(self, 'mavg_curves'):
                del self.mavg_curves
            # Derivatives (calc_derivatives() & plot_right_axis() listが返される)
            self.derivative_data = pltutils.calc_derivatives(self.plot_data)
            self.derivative_curves = pltutils.plot_right_axis(
                self.plots.plts_right, self.derivative_data)
            # Peaks & Valleys描画(ImageItem以外)
            self.peaks_data, self.valleys_data = pltutils.calc_peaks_and_valleys(self.plot_data)
            self.peaks = pltutils.plot_peaks(self.plots, self.peaks_data, 'circle')
            self.valleys = pltutils.plot_peaks(self.plots, self.valleys_data, 'square')
            visible = self.peaks_check.isChecked()
            for curve in self.peaks + self.valleys:
                curve.setVisible(visible)
        # PowerSpectra(FFT)はX軸がFreq.でTimeではないため、
        # Mark/Select Mark/Shift timeといったTime系の操作UIは無関係。
        has_time_axis = self.graph_id not in freq_lst
        self.mark_check.setVisible(has_time_axis and len(self.data.cpt_list) > 0)
        self.time_shift.setVisible(has_time_axis and len(self.data.cpt_list) > 0)
        self.shift_layout.setVisible(has_time_axis)
        self.hide_show_plot()
        self.title_label.setText(self.window_title + "\n" + self.plots.title)
        if self.args.pdffile:
            append_window_to_pdf(self, output_pdf)

    def select_graph(self):
        # 選択されたアクションのテキストを取得
        selected_action = self.sender()
        self.selected_graph = selected_action.text()
        self.update_plot()

    def update_shift_value(self):
        # テキストボックスの値を取得して数値に変換，空の場合は0
        text = self.shift_input.text()
        self.add_shift = int(text) if text else 0
        if self.add_shift > self.data.data_t[0][-1]:
            self.add_shift = self.data.data_t[0][-1]
        print(t('plot.current_shift_value', shift=self.add_shift))
        self.hide_show_plot()


def append_window_to_pdf(window, existing_pdf_path, dpi=300):
    # 一時PDFに書き出す
    temp_pdf = existing_pdf_path + ".temp.pdf"
    _save_window_as_pdf(window, temp_pdf, dpi)

    # 既存 + 新しいPDFをマージして新しい一時ファイルへ
    merged_pdf = existing_pdf_path + ".merged.pdf"
    merger = PdfMerger()
    if os.path.exists(existing_pdf_path):
        merger.append(existing_pdf_path)
    merger.append(temp_pdf)
    merger.write(merged_pdf)
    merger.close()

    # 上書き
    os.replace(merged_pdf, existing_pdf_path)
    os.remove(temp_pdf)


def _save_window_as_pdf(window, filename, dpi=300):
    pixmap = QPixmap(window.size())
    window.render(pixmap)

    pdf_writer = QPdfWriter(filename)
    size = window.size()
    pdf_writer.setPageSizeMM(QSizeF(size.width(), size.height()))
    pdf_writer.setResolution(dpi)

    painter = QPainter(pdf_writer)
    image = pixmap.toImage()
    rect = painter.viewport()
    scaled_size = image.size()
    scaled_size.scale(rect.size(), 1)  # アスペクト比維持
    painter.setViewport(rect.x(), rect.y(), scaled_size.width(), scaled_size.height())
    painter.setWindow(image.rect())
    painter.drawImage(0, 0, image)
    painter.end()


def get_newest_file_name(folder_path):
    # .datファイルのみをフィルタリング
    dat_files = [f for f in os.listdir(folder_path) if f.endswith('.dat')]
    # .datファイルが存在しない場合は None を返す
    if not dat_files:
        return None
    # 最新の.datファイルを選択
    newest_file = max(dat_files, key=lambda f: os.path.getmtime(os.path.join(folder_path, f)))
    return os.path.join(folder_path, newest_file)


def get_files_from_directory(folder):
    dat_files = []
    for root, _, files in os.walk(folder):
        for f in files:
            if f.endswith('.dat'):
                dat_files.append(os.path.join(root, f))
    return sorted(dat_files)


# ディレクトリが存在しない場合は作成する
default_dir = './data/'
os.makedirs(default_dir, exist_ok=True)

default_filter_file = 'default_filter.json'
with open(default_filter_file, "r", encoding="utf-8") as f:
    default_filter = json.load(f)

default_filename = get_newest_file_name(default_dir)
default_wpconfig = 'default_wavelet_params.json'

# MainWindow.update_plot()がargs.pdffile時に参照するPDF出力先。
# main()のローカル変数だと(update_plot()はモジュールグローバルしか見えない)
# NameErrorになるため、モジュールレベルで1回だけ決める(1回の実行で1ファイルに蓄積)。
output_pdf = f"Figures_{datetime.now().strftime('%Y%m%d_%H%M%S')}.pdf"

# === パラメータ定義（型・デフォルト・説明）を一元化 ===
# 'help' はi18nカタログのkey。動的な値を埋め込むものだけ 'help_kwargs' を持つ
# （--lang解決前にこの辞書自体は評価されるため、実際の翻訳はparse_args()内で行う）。
DEFAULTS = {
    'dirname': {
        'short': '-d',
        'default': default_dir,
        'type': str,
        'help': 'plot.help.dirname'},
    'filename': {
        'short': '-f',
        'default': default_filename,
        'type': str,
        'help': 'plot.help.filename'},
    'graph': {
        'short': '-g',
        'default': 0,
        'type': int,
        'help': 'plot.help.graph',
                'help_kwargs': lambda: {
                    'types': ' / '.join(graph_name)}},
    'smoothing': {
        'short': '-s',
        'default': False,
        'type': bool,
        'help': 'plot.help.smoothing',
        'help_kwargs': lambda: {
            'file': default_filter_file,
            'filt': default_filter}},
    'mvaverage': {
        'short': '-mva',
        'default': 30,
        'type': int,
        'help': 'plot.help.mvaverage'},
    'timeshift1': {
        'short': '-ts1',
        'default': False,
        'type': bool,
        'help': 'plot.help.timeshift1'},
    'vline': {
        'short': '-v',
        'default': False,
        'type': bool,
        'help': 'plot.help.vline'},
    'LT': {
        'short': '-L',
        'default': False,
        'type': bool,
        'help': 'plot.help.LT'},
    'PRE': {
        'short': '-P',
        'default': False,
        'type': bool,
        'help': 'plot.help.PRE'},
    'mvaslider': {
        'short': '-slider',
        'default': False,
        'type': bool,
        'help': 'plot.help.mvaslider'},
    'wpconfig': {
        'short': '-wpc',
        'default': default_wpconfig,
        'type': str,
        'help': 'plot.help.wpconfig'},
    'wlrange': {
        'short': '-wlr',
        'default': (
            1.2,
            3.0,
            0.01),
        'nargs': 3,
        'type': float,
        'metavar': "('START', 'STOP', 'STEP')",
        'help': 'plot.help.wlrange'},
    'wlomega0': {
        'short': '-wlo',
        'default': 6,
        'type': float,
        'help': 'plot.help.wlomega0'},
    'pdffile': {
        'short': '-pdf',
        'default': False,
        'type': bool,
        'help': 'plot.help.pdffile'},
    'background': {
        'short': '-bg',
        'default': False,
        'type': bool,
        'help': 'plot.help.background'},
    'automation': {
        'short': '-auto',
        'default': False,
        'type': bool,
        'help': 'plot.help.automation'},
    'fullscreen': {
        'short': '-fs',
        'default': False,
        'type': bool,
        'help': 'plot.help.fullscreen'},
    'excel': {
        'short': '-x',
        'default': False,
        'type': bool,
        'help': 'plot.help.excel'},
    'header': {
        'short': '-hdr',
        'default': False,
        'type': bool,
        'help': 'plot.help.header'},
    'peaks': {
        'short': '-p',
        'default': False,
        'type': bool,
        'help': 'plot.help.peaks'},
    'Debug': {
        'short': '-dbg',
        'default': False,
        'type': bool,
        'help': 'help.debug'}}


def parse_args():
    # --lang must be resolved before the parser is built so --help itself is localized.
    i18n.set_language(i18n.resolve_lang_from_argv(sys.argv)
                      or os.environ.get('SENSOR_BRIDGE_LANG'))

    parser = argparse.ArgumentParser(description=t('plot.description'))
    parser.add_argument(
        '-V',
        '--version',
        action="version",
        version=f"%(prog)s {__version__}",
        help=t('help.version'))
    # 共通パラメータを定義
    for key, meta in DEFAULTS.items():
        flags = [meta.get("short", ""), f"--{key}"]
        flags = [f for f in flags if f]  # 空要素除外

        help_kwargs = meta['help_kwargs']() if 'help_kwargs' in meta else {}
        help_text = f"{t(meta['help'], **help_kwargs)} (default: {meta['default']})"

        if meta["type"] == bool:
            parser.add_argument(*flags, action="store_true", help=help_text)
        elif 'nargs' in meta.keys():
            parser.add_argument(
                *flags,
                nargs=meta['nargs'],
                type=meta["type"],
                default=meta["default"],
                help=help_text)
        else:
            parser.add_argument(*flags, type=meta["type"], default=meta["default"], help=help_text)

    # config.json用オプション(これは他と独立)
    parser.add_argument('--config', type=str, help=t('plot.help.config'))
    parser.add_argument('-lang',
                        '--lang',
                        choices=i18n.SUPPORTED_LANGS,
                        default=i18n.get_language(),
                        help=t('help.lang',
                               langs='/'.join(i18n.SUPPORTED_LANGS)))

    args = parser.parse_args()
    i18n.set_language(args.lang)

    # configファイルが指定されていたら読み込み
    if args.config:
        try:
            with open(args.config, 'r') as f:
                config_data = json.load(f)
                for key, value in config_data.items():
                    if hasattr(args, key):
                        expected_type = DEFAULTS[key]["type"]
                        # 文字列で保存された数値などに対応
                        setattr(args, key, expected_type(value))
        except Exception as e:
            print(t('plot.config_load_error', err=e))
            sys.exit(1)

    return args


def build_wavelet_params(args) -> WaveletParams:
    if args.wpconfig:
        params = WaveletParams.from_json(args.wpconfig)
    else:
        params = WaveletParams()  # default

    # CLI引数がある場合は上書き
    if args.wlrange:
        params.range = args.wlrange
    if args.wlomega0:
        params.omega0 = args.wlomega0

    return params


def main():
    args = parse_args()

    app = QApplication(sys.argv)
    app.setWindowIcon(QIcon('icon.png'))
    app.setApplicationName("sensor-bridge")

    # excel出力 (headless): GUIの「Save Graph」ボタン(Ctrl+S)と同じ
    # MainWindow.open_file_write_dialog() を呼ぶ。ウィンドウは表示しない。
    if args.excel:
        window = MainWindow(args.filename, args)
        window.open_file_write_dialog()
        sys.exit(0)

    files = get_files_from_directory(args.dirname)
    if args.automation:
        if not files:
            print(t('plot.no_dat_in_dir', dirname=args.dirname))
            sys.exit(1)
        print(f'{files=}')
        for fname in files:
            window = MainWindow(fname, args)
            window.show()
            QTimer.singleShot(1000, window.close)
    else:
        if args.filename == default_filename:
            if not files:
                print(t('plot.no_dat_in_data_folder'))
                sys.exit(1)
            args.filename = files[-1]
        window = MainWindow(args.filename, args)
        window.show()
        if args.background:
            QTimer.singleShot(1000, app.quit)

    sys.exit(app.exec_())


if __name__ == '__main__':
    main()
