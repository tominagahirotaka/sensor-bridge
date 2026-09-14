#!/usr/bin/env python3
from processed_binary import ProcessedBinaryError, decode_processed_payload
from mylib.i18n import t as tr
from mylib.debug_utils import debug_print
import mylib.utils as utils
import mylib.fileIO as FIO
import mylib.communicate as comm
from PyQt5.QtCore import pyqtSignal  # or from PySide2.QtCore import Signal if you're using PySide
from PyQt5.QtCore import Qt  # or from PySide2.QtCore import Signal if you're using PySide
from pyqtgraph.Qt import QtCore
from PyQt5.QtGui import QIntValidator
from PyQt5.QtWidgets import (QVBoxLayout, QTableWidget, QTableWidgetItem,
                             QTabWidget, QFileDialog, QDialog, QHBoxLayout,
                             QCheckBox, QLabel, QButtonGroup, QRadioButton,
                             QWidget, QSpinBox, QGroupBox, QSlider, QLineEdit,
                             QPushButton, QDoubleSpinBox)
from openpyxl import load_workbook
from openpyxl import Workbook
from dataclasses import dataclass, field, asdict
import time
import sys
import seaborn as sns
import scipy.signal as signal
import re
import copy
import json
import datetime
import numpy as np
import os
import pandas as pd
import platform
import pyqtgraph as pg
pg.setConfigOptions(antialias=False)

font_family_name = {
    'Windows': 'Yu Gothic',
    'Linux': 'IPAexGothic',
    'Darwin': 'Hiragino Maru Gothic Pro'}

tableau10 = [
    '#1f77b4',  # Blue
    '#ff7f0e',  # Orange
    '#2ca02c',  # Green
    '#d62728',  # Red
    '#9467bd',  # Purple
    '#8c564b',  # Brown
    '#e377c2',  # Pink
    '#7f7f7f',  # Gray
    '#bcbd22',  # Olive
    '#17becf'   # Cyan
]
cud_colors = [
    '#E69F00',  # orange
    '#56B4E9',  # blue
    '#009E73',  # green
    '#F0E442',  # yellow
    '#0072B2',  # dark blue
    '#D55E00',  # red-orange
    '#CC79A7'   # pink
]
colorbrewer_set1 = [
    '#e41a1c',  # red
    '#377eb8',  # blue
    '#4daf4a',  # green
    '#984ea3',  # purple
    '#ff7f00',  # orange
    '#ffff33',  # yellow
    '#a65628',  # brown
    '#f781bf'   # pink
]

# COLORS = ['black', 'red', 'blue', 'magenta', 'green', 'indigo', 'cyan', 'maroon']
COLORS = colorbrewer_set1  # cud_colors #tableau10

# 背景色を定義
bg_colors = {
    "BN": "#FFC8C8",
    "DS": "#C8FFC8",
    "MA": "#C8C8FF",
    "LP": "#FFFFC8",
    "BP": "#CFCFC8",
    "TR": "#CFCFC8"}  # 薄い赤, 薄い緑, 薄い青, 薄い黄
symbol_colors = ['#E69F00', '#56B4E9', '#009E73', '#F0E442', '#D55E00', '#CC79A7']


def make_style(color='k', symbol='o', size=10, pen=None):
    return {
        'pen': pen,
        'symbol': symbol,
        'symbolBrush': color,
        'symbolPen': color,
        'symbolSize': size}


style_dict = {
    'circle': make_style(color='k', symbol='o'),
    'cross': make_style(color='k', symbol='x'),
    'square': make_style(color='k', symbol='s', size=14)
}

os_name = platform.system()
sns.set(font=font_family_name[os_name])

# ViewBoxをオーバーライドして描画時間を計測


class TimedViewBox(pg.ViewBox):
    def paint(self, p, opt, widget):
        t0 = time.perf_counter()
        super().paint(p, opt, widget)
        t1 = time.perf_counter()
        print(f"ViewBox paint: {(t1 - t0) * 1000:.1f}ms")

# PlotWidgetをオーバーライド


class TimedPlotWidget(pg.PlotWidget):
    def __init__(self, **kwargs):
        super().__init__(viewBox=TimedViewBox(), **kwargs)


class PlotData:
    def __init__(self, data=None, labels=None):
        """
        data: list of (x, y) tuples or lists
        labels: optional list of labels
        """
        self.data = [(np.array(x), np.array(y)) for x, y in data] if data else []
        self.labels = labels if labels else [None] * len(self.data)
        self.xlabel = None
        self.title = None
        self.subtitle = None

    def __getitem__(self, idx):
        return self.data[idx]

    def __len__(self):
        return len(self.data)

    def __iter__(self):
        return iter(self.data)

    def add_series(self, x, y, label=None):
        self.data.append((np.array(x), np.array(y)))
        self.labels.append(label)
        self.num_data = len(self.data)

    def __repr__(self):
        return f"PlotData({len(self.data)} series)"

    def to_excel(self, filename, filter=None, mark_points=None, note_df=None):
        basename = os.path.splitext(filename)[0]  # 'ABC_G02'
        start = time.perf_counter()
        time_shift1 = float(mark_points[0][0]) if len(mark_points) > 0 else 0
        filter_df = pd.DataFrame(filter)
        title_df = pd.Series({'title': self.title, 'subtitle': self.subtitle}).T
#        with pd.ExcelWriter(filename, engine='openpyxl') as writer:
        with pd.ExcelWriter(filename, engine='xlsxwriter') as writer:
            sheet_count = 0
            for i, ((x, y), label) in enumerate(zip(self.data, self.labels)):
                if len(x) == 0 or len(y) == 0:
                    continue  # 空データはスキップ
                x_lab = f"{self.xlabel['bottom'][0]}({self.xlabel['bottom'][1]})" if self.xlabel else 'time'
                y_lab = f"{label['left'][0]}({label['left'][1]})" if label else f"Series{i + 1}"
                if time_shift1 > 0:
                    ts1 = x - time_shift1
                    df = pd.DataFrame({x_lab: x, x_lab + 'ts1': ts1, y_lab: y})
                else:
                    df = pd.DataFrame({x_lab: x, y_lab: y})
                sheet_name = y_lab
                print(f'{sheet_name=}')
                # シート名が31文字超えないようにし、不正文字も除去
                safe_name = sheet_name[:31].replace('/', '_')
                df.to_excel(writer, sheet_name=safe_name, index=False)
# clean_name = re.sub(r'[()]', '', safe_name)
                clean_name = re.sub(r'\([^)]*\)', '', safe_name)
                df.to_csv(f"{basename}_{clean_name}.csv", index=False)
                sheet_count += 1

            filter_df.to_excel(writer, sheet_name='Filter', index=False)
            title_df.to_excel(writer, sheet_name='Title', index=True, header=False)
            if mark_points is not None:
                mark_df = pd.DataFrame(
                    mark_points, columns=[
                        'real time', 'time'], index=range(
                        1, len(mark_points) + 1))
                mark_df.to_excel(writer, sheet_name='mark points', index=True, header=True)
            if note_df is not None:
                note_df.to_excel(writer, sheet_name='Note', index=True, header=False)

            if sheet_count == 0:
                raise ValueError(
                    "No valid data series to write. At least one non-empty sheet is required.")

        print(tr('pu.save_plotdata_excel', sec=time.perf_counter() - start))
        print(f"{filename=}")


class PlotImageData:
    def __init__(self, data=None, labels=None):
        """
        data: list of (x, y, value) tuples or lists
        labels: optional list of labels
        """
        self.data = [(np.array(x), np.array(y), np.array(z)) for x, y, z in data] if data else []
        self.labels = labels if labels else [None] * len(self.data)
        self.xlabel = None
        self.title = None
        self.subtitle = None

    def __getitem__(self, idx):
        return self.data[idx]

    def __len__(self):
        return len(self.data)

    def __iter__(self):
        return iter(self.data)

    def add_series(self, x, y, val, label=None):
        self.data.append((np.array(x), np.array(y), np.array(val)))
        self.labels.append(label)

    def __repr__(self):
        return f"PlotData({len(self.data)} series)"

    def to_excel(self, filename, filter=None, mark_points=None, note_df=None):
        basename = os.path.splitext(filename)[0]  # 'ABC_G02'
        start = time.perf_counter()
        time_shift1 = float(mark_points[0][0]) if len(mark_points) > 0 else 0
        filter_df = pd.DataFrame(filter)
        title_df = pd.Series({'title': self.title, 'subtitle': self.subtitle}).T
#        with pd.ExcelWriter(filename, engine='openpyxl') as writer:
        with pd.ExcelWriter(filename, engine='xlsxwriter') as writer:
            sheet_count = 0
            for i, ((x, y, val), label) in enumerate(zip(self.data, self.labels)):
                if len(x) == 0 or len(y) == 0 or len(val) == 0:
                    continue  # 空データはスキップ

                print(type(x), getattr(x, 'shape', None))
                print(type(y), getattr(y, 'shape', None))
                print(type(val), getattr(val, 'shape', None))

#                df = pd.DataFrame({'x': x, 'y': y, 'z':val})
                print(f'{self.xlabel=}, {label=}')
                df = pd.DataFrame(val.T, index=x, columns=y)
                x_lab = f"{self.xlabel['bottom'][0]}({self.xlabel['bottom'][1]})" if self.xlabel else 'time'
                sheet_name = f"{label['left'][0]}({label['left'][1]})" if label else f"Series{i + 1}"
                df.index.name = f"{x_lab}\\freq.({label['left'][1]})"
                # シート名が31文字超えないようにし、不正文字も除去
                safe_name = sheet_name[:31].replace('/', '_')
                df.to_excel(writer, sheet_name=safe_name, index=True)
# clean_name = re.sub(r'[()]', '', safe_name)
                clean_name = re.sub(r'\([^)]*\)', '', safe_name)
                df.to_csv(f"{basename}_{clean_name}.csv", index=True)
                sheet_count += 1

            filter_df.to_excel(writer, sheet_name='Filter', index=False)
            title_df.to_excel(writer, sheet_name='Title', index=True, header=False)
            if note_df is not None:
                note_df.to_excel(writer, sheet_name='Note', index=True, header=True)

            if sheet_count == 0:
                raise ValueError(
                    "No valid data series to write. At least one non-empty sheet is required.")

        print(tr('pu.save_imagedata_excel', sec=time.perf_counter() - start))
        print(f"{filename=}")

# Initialize plots
# 図の数(num_plots)分のplotとcontrol用plot(p_base)を用意,labelがrow=0なので1からcount


class InitPlots:
    def __init__(self, win, num_plots):
        self.title = ''
        self.label = mk_label(win, layout=[0, 0, 1], justify='left')  # right')  # make label
        self.plts, self.plts_right = [], []
        for i in range(num_plots):
            p1 = mk_plot(win, layout=[i + 1, 0, 4])
            p2 = add_right_axis(p1)
            self.plts.append(p1)
            self.plts_right.append(p2)
        self.color = COLORS[:num_plots]
        self.p_base = mk_plot(win, layout=[num_plots + 1, 0, 1])

    def __getitem__(self, idx):
        return self.plts[idx]

    def __len__(self):
        return len(self.plts)

    def __iter__(self):
        return iter(self.plts)

    def set_title(self, title):
        self.title = title

    def clear_plts_p_base(self):
        for p1 in self.plts:
            p1.clear()
        self.p_base.clear()

    def remove_right_axes(self):
        for p2, p1 in zip(self.plts_right, self.plts):
            if p1.getAxis('right').linkedView() == p2:
                p1.hideAxis('right')
            if p2.scene() is not None:
                p2.scene().removeItem(p2)
        self.plts_right.clear()

    # 軸を非表示にする
    def toggle_right_axis(self, visible):
        for p1 in self.plts:
            p1.getAxis('right').setStyle(showValues=visible)  # 目盛りを非表示
            p1.getAxis('right').setVisible(visible)           # 軸自体の表示非表示

    def show_or_hide(self, win, check):
        if check:
            for p, p2, (num, cb) in zip(self.plts, self.plts_right, check):
                if cb.isChecked():
                    p.show()
                    p2.show()
                    win.ci.layout.setRowStretchFactor(num + 1, 4)  # set StretchFactor=4
                else:
                    p.hide()
                    p2.hide()
                    win.ci.layout.setRowStretchFactor(num + 1, 0)  # set StretchFactor=0


class ReadData():
    def __init__(self, args):
        self.args = args
        file = FIO.FileIO()                                                      # Instance of FileIO class
        self.header = file.read_open(self.args.filename)  # header読込み
        if self.header:                                                            # 全データ一括読込み
            debug_print(self.args, f' With header ... Using file.fread.read()')
            all_bin_data = file.fread.read()
        else:
            debug_print(self.args, f' No header ... Using np.loadtxt()')
            data_ = np.loadtxt(sys.argv[1], dtype='int', comments='#', unpack=True)

        for key, val in self.header.__dict__.items():
            debug_print(self.args, f' {key:<10}={val}')  # header確認

        if hasattr(self.header, 'processed_data'):
            self._load_processed_payload(all_bin_data)
            self._load_external_excel()
            self.makeTitle()
            return

        self.board = comm.Board(self.header, self.args, False)     # Instance of Board class

        # For Old version (旧versionに入っていない項目追加)
        if 'struct' not in self.board.p.env_set:
            self.ForOldVersion()
            print(tr('pu.use_python38'))

        self.board.set_self_vars()               # set variables
        self.board._build_struct()
        # self.board.prepare_plotting()
        debug_print(self.args, f' self variables={vars(self.board)}')       # print self vars list
        debug_print(self.args, f'[INFO] one_data_size={self.board.one_data_size}')
        self.num_data = int(len(all_bin_data) / self.board.one_data_size)

        self.data = np.zeros((self.num_data, 2 * len(self.board.structure)))  # data配列確保
        for i in range(self.num_data):                # data変換(binary data -> numerical data)
            self.data[i] = self.board.convert(
                all_bin_data[i * self.board.one_data_size:(i + 1) * self.board.one_data_size])
        # data配列の行と列を入替え
        self.data_t = self.data.T
        # PlotData 作成
        self.data0 = PlotData()
        self.data0.title = 'Timeseries'
        for k, lst in enumerate(self.board.structure[1:]):
            ax_label = {'left': (f'{lst[0][0]}{lst[0][1]}',
                                 f'{self.board.func_unit[lst[2]]}')}   # axis label 'port\d(V)'
            self.data0.add_series(self.data_t[0], self.data_t[k + 1], label=ax_label)

        # Axis label bottom -->  'time(sec)'
        self.ax_time = {'bottom': (
            self.board.structure[0][0][0], self.board.func_unit[self.board.structure[0][2]])}
        self.data0.xlabel = {'bottom': (
            self.board.structure[0][0][0], self.board.func_unit[self.board.structure[0][2]])}

        self._load_checkpoint_list()
        self._load_external_excel()

        self.makeTitle()                         # setting Title

    def _load_processed_payload(self, payload):
        metadata = self.header.processed_data
        try:
            series = decode_processed_payload(payload, metadata)
        except ProcessedBinaryError as exc:
            raise ValueError(str(exc)) from exc

        self.board = None
        self.num_data = len(series[0][0]) if series else 0
        self.data0 = PlotData()
        self.data0.title = 'Timeseries'

        time_meta = metadata.get('time_axis', {})
        time_name = str(time_meta.get('name', 'time'))
        time_unit = str(time_meta.get('unit', ''))
        self.ax_time = {'bottom': (time_name, time_unit)}
        self.data0.xlabel = {'bottom': (time_name, time_unit)}

        data_rows = []
        first_time = None
        for index, (x, y) in enumerate(series):
            if first_time is None:
                first_time = x
            label_meta = metadata.get('series', [])[index]
            ax_label = {
                'left': (
                    label_meta.get(
                        'name', f'series_{index}'), label_meta.get(
                        'unit', ''))}
            self.data0.add_series(x, y, label=ax_label)
            data_rows.append(y)

        if first_time is None:
            self.data_t = np.array([[]])
        else:
            self.data_t = np.vstack([first_time, *data_rows])
        self._load_checkpoint_list()

    def _load_checkpoint_list(self):
        self.cpt_list = np.array([time[1] if type(time[0]) is datetime.datetime else time[0]
                                 for time in self.header.time['check_points']])
        debug_print(self.args, f' ================ {self.cpt_list=}')

    def _load_external_excel(self):
        # 外部excelファイルに縦線を描画したい位置とその文字列を指定(ex. 'LT' \n 300, 'PRE11'\n 250)
        self.external_excel = os.path.splitext(self.args.filename)[0] + ".xlsx"
        if os.path.exists(self.external_excel):
            external_df = pd.read_excel(self.external_excel)
            self.external_dict = external_df.to_dict(orient="index")[0]
            debug_print(self.args, f'{self.external_excel=}, {self.external_dict=}')
            self.LT_dict = {k: v for k, v in self.external_dict.items() if 'LT' in k}
            self.PRE_dict = {k: v for k, v in self.external_dict.items() if 'PRE' in k}
        else:
            self.external_dict = None
            self.LT_dict = None
            self.PRE_dict = None

    # For Old version
    # 旧versionに入っていない項目の追加
    # platformの仕様変更の為，読み込めない場合はpython3.8以下を使用
    def ForOldVersion(self):
        # 現行Firmwareの対象はRaspberry Pi Pico/Pico Wのみ。ここは、それ以前に
        # 実際にArduino Unoで記録した過去のData(.dat)を読むためだけの後方互換Codeで、
        # 現行のHardware対応状況とは無関係(Raw Data保持のため削除しないこと)。
        port_str = ','.join(str(item) for item in self.board.p.env_set['port_num'])
        time_unit = self.board.p.env_set['time_unit']
        time_byte = self.board.p.env_set['time_byte']
        data_byte = self.board.p.env_set['data_byte']
        ADCres = self.board.p.env_set['ADCres'] = '10'       # 記録当時のArduino Unoの仕様(10bit ADC)
        volt = self.board.p.env_set['volt'] = '5'          # 記録当時のArduino Unoの仕様(5V)
        self.board.p.env_set['struct'] = f'time(u{time_byte}:func0), [({port_str})]port(u{data_byte}:func1)'
        time_bits = 8 * time_byte
        volt_coeff = float(volt) / float(2**12)
        self.board.p.env_set['func'] = (
            f"[(lambda tm:tm/{float(10**time_unit)}, {time_bits}, 'sec'), "
            f" (lambda x:x*{volt_coeff}, {ADCres}, 'V')]"
        )
        self.board.p.env_set['endian'] = 'big'
        # debug_print(self.args, f"{self.board.p.env_set['func']=}")

    def makeTitle(self):                         # title設定
        if len(self.header.subject) != 0:
            if 'birth' not in self.header.subject:
                self.title = ';'.join(
                    [f'{key}:{val} ' for key, val in self.header.subject.items()])
                return
            elif 'age' not in self.header.subject:
                age = utils.calc_age(self.header.subject['birth'], self.header.time['start_time'])
            else:
                age = self.header.subject['age']
            self.title = f"{self.header.subject['name']} {self.header.subject['gender']}({age})"
# '%s %s(%s)' % (self.header.subject['name'], self.header.subject['gender'],age)
        else:
            self.title = ''  # 'Plot program'

    def output_excel_file(self, excelfile):
        col1 = [la + '_' + s for la, s in zip(self.board.lab, self.board.lab_sub)]
        columns = col1 + [lab + '(raw)' for lab in col1]
        print(f'num of data={self.num_data}, column names={columns}')
        if self.num_data < 2**20:
            with pd.ExcelWriter(excelfile) as writer:
                pd.DataFrame(
                    self.data,
                    columns=columns).to_excel(
                    writer,
                    sheet_name='data',
                    index=False,
                    header=True)
        else:
            print(tr('pu.excel_row_limit'))


class SignalSmoothingWindow(QWidget):
    execTriggered = pyqtSignal(object)  # データを送るための Signal

    def __init__(self, plts, data, cpt_list):
        super().__init__()
        self.setWindowTitle(tr('pu.smoothing_window_title'))
        self.resize(800, 600)
        self.plts, self.original_data, self.cpt_list = plts, data, cpt_list
        self.data = copy.deepcopy(self.original_data)
        self.filtered_plot = [None] * len(self.data)
        self.current_fs_label = [None] * len(self.data)
        self.ds_freq = [None] * len(self.data)
        self.anti_alias_check = [None] * len(self.data)
        self.ma_window = [None] * len(self.data)
        self.tr_min = [None] * len(self.data)
        self.tr_max = [None] * len(self.data)
        self.tr_reset_t0 = [None] * len(self.data)
        self.bp_low = [None] * len(self.data)
        self.bp_high = [None] * len(self.data)
        self.lp_cutoff = [None] * len(self.data)
        self.bn_center = [None] * len(self.data)
        self.bn_q = [None] * len(self.data)
        # Allタブ用
        self.current_fs_label_all = None
        self.ds_freq_all = None
        self.anti_alias_check_all = None
        self.ma_window_all = None
        self.tr_min_all = None
        self.tr_max_all = None
        self.tr_reset_t0_all = None
        self.bp_low_all = None
        self.bp_high_all = None
        self.lp_cutoff_all = None
        self.bn_center_all = None
        self.bn_q_all = None

        self.apply_button = {}
        self.history = {}
        self.history_label = {}
        self.undo_button = {}
        # メインレイアウト
        layout = QVBoxLayout()

        # Save/Load Button
        common_button_layout = QHBoxLayout()
        exec_button = QPushButton(tr('pu.btn_exec'))
        load_button = QPushButton(tr('pu.btn_load'))
        save_button = QPushButton(tr('pu.btn_save'))
        exec_button.clicked.connect(self.on_exec)
        load_button.clicked.connect(lambda: self.load_parameters())
        save_button.clicked.connect(lambda: self.save_parameters())
        common_button_layout.addWidget(exec_button)
        common_button_layout.addWidget(load_button)
        common_button_layout.addWidget(save_button)
        layout.addLayout(common_button_layout)

        # タブウィジェットの作成
        idxs = list(range(len(self.data.labels)))
        self.tab_widget = QTabWidget()

        # All Tabを作成
        tab = QWidget()
        self.tab_widget.addTab(tab, f"All")
        tab_layout = QVBoxLayout()            # タブ内のレイアウト
        self.historyAll = []
        # history_label with Undo setting
        history_label_layout = self.create_history_group(idxs)
        # フィルタ設定
        filter_layout = QVBoxLayout()
        tr_group = self.create_trim_group(idxs)          # Trimming
        lp_group = self.create_lowpass_group(idxs)       # Lowpass Filter
        ds_group = self.create_downsampling_group(idxs)  # Down sampling
        ma_group = self.create_ma_group(idxs)            # Moving Average
        bn_group = self.create_bandnotch_group(idxs)     # Band Notch Filter
        bp_group = self.create_bandpass_group(idxs)      # Bandpass Filter
        tr_group.setStyleSheet(f"QGroupBox {{ background-color: {bg_colors['TR']}; }}")
        lp_group.setStyleSheet(f"QGroupBox {{ background-color: {bg_colors['LP']}; }}")
        ds_group.setStyleSheet(f"QGroupBox {{ background-color: {bg_colors['DS']}; }}")
        ma_group.setStyleSheet(f"QGroupBox {{ background-color: {bg_colors['MA']}; }}")
        bn_group.setStyleSheet(f"QGroupBox {{ background-color: {bg_colors['BN']}; }}")
        bp_group.setStyleSheet(f"QGroupBox {{ background-color: {bg_colors['BP']}; }}")
        filter_layout.addWidget(tr_group)
        filter_layout.addWidget(lp_group)
        filter_layout.addWidget(ds_group)
        filter_layout.addWidget(ma_group)
        filter_layout.addWidget(bn_group)
        filter_layout.addWidget(bp_group)

        tab_layout.addLayout(history_label_layout)
        tab_layout.addLayout(filter_layout)
        tab.setLayout(tab_layout)

        # 各データに対応するタブを作成
        for idx, label in enumerate(self.data.labels):
            name, unit = next(iter(label.values()))
            tab = QWidget()
            self.tab_widget.addTab(tab, f"{name}")
            tab_layout = QVBoxLayout()            # タブ内のレイアウト

            # Label setting
            self.history[idx] = []
            # history_label with Undo setting
            history_label_layout = self.create_history_group(idx)

            # フィルタ設定
            filter_layout = QVBoxLayout()
            tr_group = self.create_trim_group(idx)          # Trimming
            lp_group = self.create_lowpass_group(idx)       # Lowpass Filter
            ds_group = self.create_downsampling_group(idx)  # Down sampling
            ma_group = self.create_ma_group(idx)            # Moving Average
            bn_group = self.create_bandnotch_group(idx)     # Band Notch Filter
            bp_group = self.create_bandpass_group(idx)      # Bandpass Filter
            tr_group.setStyleSheet(f"QGroupBox {{ background-color: {bg_colors['TR']}; }}")
            lp_group.setStyleSheet(f"QGroupBox {{ background-color: {bg_colors['LP']}; }}")
            ds_group.setStyleSheet(f"QGroupBox {{ background-color: {bg_colors['DS']}; }}")
            ma_group.setStyleSheet(f"QGroupBox {{ background-color: {bg_colors['MA']}; }}")
            bn_group.setStyleSheet(f"QGroupBox {{ background-color: {bg_colors['BN']}; }}")
            bp_group.setStyleSheet(f"QGroupBox {{ background-color: {bg_colors['BP']}; }}")
            filter_layout.addWidget(tr_group)
            filter_layout.addWidget(lp_group)
            filter_layout.addWidget(ds_group)
            filter_layout.addWidget(ma_group)
            filter_layout.addWidget(bn_group)
            filter_layout.addWidget(bp_group)

            tab_layout.addLayout(history_label_layout)
            tab_layout.addLayout(filter_layout)
            tab.setLayout(tab_layout)

        layout.addWidget(self.tab_widget)

        self.setLayout(layout)

    def on_exec(self):
        self.execTriggered.emit({'filtered': self.data, 'history': self.history})
        self.close()

    def create_downsampling_group(self, idxs):
        idxs = [idxs] if isinstance(idxs, int) else idxs
        is_all = len(idxs) > 1

        t, _ = self.data.data[idxs[0]]
        group = QGroupBox("Down Sampling")
        layout = QVBoxLayout()
        param_layout = QHBoxLayout()

        # 新しいサンプリング周波数の設定
        param_layout.addWidget(QLabel("New Fs (Hz):"))

        ds_freq = QSpinBox()
        current_fs = int(1 / (t[1] - t[0]))  # 現在のサンプリング周波数
        ds_freq.setRange(1, current_fs)
        ds_freq.setValue(current_fs // 2)  # デフォルト値は現在のFsの半分
        param_layout.addWidget(ds_freq)

        # 現在のサンプリング周波数を表示
        current_fs_label = QLabel(f"Current Fs: {current_fs} Hz")
        param_layout.addWidget(current_fs_label)

        # Anti-aliasing filterのチェックボックス
        anti_alias_check = QCheckBox("Anti-aliasing Filter")
        layout.addLayout(param_layout)
        anti_alias_check.setChecked(True)
        layout.addWidget(anti_alias_check)

        if is_all:
            self.ds_freq_all = ds_freq
            self.anti_alias_check_all = anti_alias_check
            self.current_fs_label_all = current_fs_label
        else:
            self.ds_freq[idxs[0]] = ds_freq
            self.anti_alias_check[idxs[0]] = anti_alias_check
            self.current_fs_label[idxs[0]] = current_fs_label

        buttons_layout = self.control_buttons('down sampling', idxs)
        layout.addLayout(buttons_layout)
        group.setLayout(layout)
        return group

    def create_trim_group(self, idxs):
        idxs = [idxs] if isinstance(idxs, int) else idxs
        is_all = len(idxs) > 1

        group = QGroupBox("Trim")
        layout = QVBoxLayout()

        tr_reset_t0 = QCheckBox(tr('pu.reset_tmin_to_zero'))
        tr_reset_t0.setChecked(True)  # デフォルトはON
        layout.addWidget(tr_reset_t0)

        if len(self.cpt_list) > 0:
            # --- Mark 選択 ---
            cpt_layout = QHBoxLayout()
            cpt_layout.addWidget(QLabel("Mark #"))

            cpt_idx = QSpinBox()
            cpt_idx.setRange(0, len(self.cpt_list) - 1)
            cpt_layout.addWidget(cpt_idx)

            cpt_val_label = QLabel(f"= {self.cpt_list[0]:.2f} s")
            cpt_layout.addWidget(cpt_val_label)

            # SpinBox 変化時に時刻を表示更新
            cpt_idx.valueChanged.connect(
                lambda i: cpt_val_label.setText(f"= {self.cpt_list[i]:.2f} s")
            )

            apply_min_btn = QPushButton("→ t_min")
            apply_min_btn.clicked.connect(
                lambda: tr_min.setValue(self.cpt_list[cpt_idx.value()])
            )

            apply_max_btn = QPushButton("→ t_max")
            apply_max_btn.clicked.connect(
                lambda: tr_max.setValue(self.cpt_list[cpt_idx.value()])
            )

            cpt_layout.addWidget(apply_min_btn)
            cpt_layout.addWidget(apply_max_btn)
            layout.addLayout(cpt_layout)

        # --- t_min / t_max ---
        param_layout = QHBoxLayout()
        param_layout.addWidget(QLabel("t_min (sec):"))
        tr_min = QDoubleSpinBox()
        tr_min.setRange(0, 1000)
        tr_min.setValue(0)
        param_layout.addWidget(tr_min)

        param_layout.addWidget(QLabel("t_max (sec):"))
        tr_max = QDoubleSpinBox()
        tr_max.setRange(0, 1000)
        t_max_val = self.original_data.data[idxs[0]][0][-1]  # t配列の最終要素

        tr_max.setValue(t_max_val)
        tr_min.setRange(0, t_max_val)
        tr_max.setRange(0, t_max_val)
        tr_min.setValue(0)
        tr_max.setValue(t_max_val)  # 初期値はデータの最大時刻
        param_layout.addWidget(tr_max)

        if is_all:
            self.tr_reset_t0_all = tr_reset_t0
            self.tr_min_all = tr_min
            self.tr_max_all = tr_max
        else:
            self.tr_reset_t0[idxs[0]] = tr_reset_t0
            self.tr_min[idxs[0]] = tr_min
            self.tr_max[idxs[0]] = tr_max

        buttons_layout = self.control_buttons('trim', idxs)
        layout.addLayout(param_layout)
        layout.addLayout(buttons_layout)
        group.setLayout(layout)
        return group

    def create_ma_group(self, idxs):
        idxs = [idxs] if isinstance(idxs, int) else idxs
        is_all = len(idxs) > 1

        group = QGroupBox("Moving Average" if len(idxs) == 1 else "Moving Average (All)")
        layout = QVBoxLayout()

        # Window Size
        param_layout = QHBoxLayout()
        param_layout.addWidget(QLabel("Window Size:"))

        spinbox = QSpinBox()
        spinbox.setRange(1, 1000)
        spinbox.setValue(5)
        param_layout.addWidget(spinbox)

        if is_all:
            self.ma_window_all = spinbox
        else:
            self.ma_window[idxs[0]] = spinbox

        buttons_layout = self.control_buttons('moving average', idxs)
        layout.addLayout(param_layout)
        layout.addLayout(buttons_layout)
        group.setLayout(layout)
        return group

    def create_bandpass_group(self, idxs):
        idxs = [idxs] if isinstance(idxs, int) else idxs
        is_all = len(idxs) > 1

        group = QGroupBox("Bandpass Filter")
        layout = QVBoxLayout()

        param_layout = QHBoxLayout()
        # Low cutoff
        param_layout.addWidget(QLabel("Low (Hz):"))
        bp_low = QDoubleSpinBox()
        bp_low.setRange(0, 1000)
        bp_low.setValue(0.1)
        param_layout.addWidget(bp_low)

        # High cutoff
        param_layout.addWidget(QLabel("High (Hz):"))
        bp_high = QDoubleSpinBox()
        bp_high.setRange(0, 1000)
        bp_high.setValue(10)
        param_layout.addWidget(bp_high)

        if is_all:
            self.bp_high_all = bp_high
            self.bp_low_all = bp_low
        else:
            self.bp_high[idxs[0]] = bp_high
            self.bp_low[idxs[0]] = bp_low

        buttons_layout = self.control_buttons('bandpass', idxs)
        layout.addLayout(param_layout)
        layout.addLayout(buttons_layout)
        group.setLayout(layout)
        return group

    def create_lowpass_group(self, idxs):
        idxs = [idxs] if isinstance(idxs, int) else idxs
        is_all = len(idxs) > 1

        group = QGroupBox("Lowpass Filter")
        layout = QVBoxLayout()

        param_layout = QHBoxLayout()
        # cutoff
        param_layout.addWidget(QLabel("Cutoff (Hz):"))

        lp_cutoff = QDoubleSpinBox()
        lp_cutoff.setRange(0, 1000)
        lp_cutoff.setValue(10)
        param_layout.addWidget(lp_cutoff)

        if is_all:
            self.lp_cutoff_all = lp_cutoff
        else:
            self.lp_cutoff[idxs[0]] = lp_cutoff

        buttons_layout = self.control_buttons('lowpass', idxs)
        layout.addLayout(param_layout)
        layout.addLayout(buttons_layout)
        group.setLayout(layout)
        return group

    def create_bandnotch_group(self, idxs):
        idxs = [idxs] if isinstance(idxs, int) else idxs
        is_all = len(idxs) > 1

        group = QGroupBox("Band Notch Filter")
        layout = QVBoxLayout()

        param_layout = QHBoxLayout()
        # Center frequency
        param_layout.addWidget(QLabel("Freq (Hz):"))

        bn_center = QDoubleSpinBox()
        bn_center.setRange(0, 1000)
        bn_center.setValue(60)
        param_layout.addWidget(bn_center)

        # Quality factor
        param_layout.addWidget(QLabel("Q:"))
        bn_q = QDoubleSpinBox()
        bn_q.setRange(0.1, 100)
        bn_q.setValue(30)
        param_layout.addWidget(bn_q)

        if is_all:
            self.bn_center_all = bn_center
            self.bn_q_all = bn_q
        else:
            self.bn_center[idxs[0]] = bn_center
            self.bn_q[idxs[0]] = bn_q

        buttons_layout = self.control_buttons('bandnotch', idxs)
        layout.addLayout(param_layout)
        layout.addLayout(buttons_layout)
        group.setLayout(layout)
        return group

    def create_history_group(self, idxs):
        idxs = [idxs] if isinstance(idxs, int) else idxs
        is_all = len(idxs) > 1

        button_layout = QHBoxLayout()

        undo_btn = QPushButton(tr('pu.btn_undo'))
        undo_btn.clicked.connect(lambda checked, i=idxs: self.undo_exec(i))

        if is_all:
            self.undo_button['all'] = undo_btn
            self.history_label['all'] = QLabel('')
            button_layout.addWidget(self.undo_button['all'], stretch=1)
            button_layout.addWidget(self.history_label['all'], stretch=7)
        else:
            self.undo_button[idxs[0]] = undo_btn
            self.history_label[idxs[0]] = QLabel('')
            button_layout.addWidget(self.undo_button[idxs[0]], stretch=1)
            button_layout.addWidget(self.history_label[idxs[0]], stretch=7)

        return button_layout

    def control_buttons(self, method, idxs):
        idxs = [idxs] if isinstance(idxs, int) else idxs
        is_all = len(idxs) > 1
        key = f'method_all_{method}' if is_all else f'method_{idxs[0]}_{method}'

        self.apply_button[key] = QPushButton(tr('pu.btn_apply'))
        self.apply_button[key].clicked.connect(lambda checked, m=method, i=idxs: self.apply(m, i))

        control_buttons_layout = QHBoxLayout()
        control_buttons_layout.addWidget(self.apply_button[key])
        return control_buttons_layout

    def apply(self, method, idxs):
        idxs = [idxs] if isinstance(idxs, int) else idxs
        is_all = len(idxs) > 1
        for idx in idxs:
            if 'down sampling' in method:
                new_fs = self.ds_freq_all.value() if len(
                    idxs) > 1 else self.ds_freq[idxs[0]].value()
                is_anti_alias = self.anti_alias_check_all.isChecked() if len(
                    idxs) > 1 else self.anti_alias_check[idxs[0]].isChecked()
                self.history[idx].append(["DS", [new_fs, is_anti_alias]])
                if len(idxs) > 1:
                    self.current_fs_label_all.setText(f"Current Fs: {new_fs} Hz")
                    self.ds_freq_all.setValue(new_fs // 2)  # デフォルト値は現在のFsの半分
                else:
                    self.current_fs_label[idxs[0]].setText(f"Current Fs: {new_fs} Hz")
                    self.ds_freq[idxs[0]].setValue(new_fs // 2)  # デフォルト値は現在のFsの半分
            elif 'moving average' in method:
                window = self.ma_window_all.value() if len(
                    idxs) > 1 else self.ma_window[idxs[0]].value()
                self.history[idx].append(["MA", [window]])
            elif 'lowpass' in method:
                cutoff = self.lp_cutoff_all.value() if len(
                    idxs) > 1 else self.lp_cutoff[idxs[0]].value()
                self.history[idx].append(["LP", [cutoff]])
            elif 'bandpass' in method:
                lowcut = self.bp_low_all.value() if len(idxs) > 1 else self.bp_low[idxs[0]].value()
                highcut = self.bp_high_all.value() if len(
                    idxs) > 1 else self.bp_high[idxs[0]].value()
                self.history[idx].append(["BP", [lowcut, highcut]])
            elif 'bandnotch' in method:
                f0 = self.bn_center_all.value() if len(
                    idxs) > 1 else self.bn_center[idxs[0]].value()
                Q = self.bn_q_all.value() if len(idxs) > 1 else self.bn_q[idxs[0]].value()
                self.history[idx].append(["BN", [f0, Q]])
            elif 'trim' in method:
                t_min = self.tr_min_all.value() if len(idxs) > 1 else self.tr_min[idxs[0]].value()
                t_max = self.tr_max_all.value() if len(idxs) > 1 else self.tr_max[idxs[0]].value()
                tr_reset_t0 = self.tr_reset_t0_all.isChecked() if len(
                    idxs) > 1 else self.tr_reset_t0[idxs[0]].isChecked()
                self.history[idx].append(["TR", [t_min, t_max, tr_reset_t0]])

            print(f'Original {self.history=}')
            # SignalFilter クラスのみ。関数・dictは不要。
            sf = SignalFilter(self.original_data.data[idx])
            self.data.data[idx] = sf.apply(self.history[idx]).data
            # self.data.data[idx] = cont_calc_filters(self.original_data.data[idx], self.history[idx])
            txt = tr('pu.history_prefix') + \
                '+'.join(set_bg_color(f'{method}{param}') for method, param in self.history[idx])
            self.history_label[idx].setText(txt)
            # プロットの更新
            self.update_plot(idx)

        # Allタブの履歴ラベルも更新
        if is_all and 'all' in self.history_label:
            self.history_label['all'].setText(txt)

    def update_plot(self, idxs):
        idxs = [idxs] if isinstance(idxs, int) else idxs
        for idx in idxs:
            t, y = self.data.data[idx]
            if self.filtered_plot[idx]:
                self.filtered_plot[idx].setData(t, y)
                self.filtered_plot[idx].show()
            else:
                self.filtered_plot[idx] = self.plts[idx].plot(
                    t, y, pen=pg.mkPen(color=COLORS[-1], width=3), name='Filtered')

    def undo_exec(self, idxs):
        idxs = [idxs] if isinstance(idxs, int) else idxs
        is_all = len(idxs) > 1

        for idx in idxs:
            num_history = len(self.history[idx])
            print(f'{num_history=}, {self.history[idx]=}')
            if num_history == 0:
                continue
            del self.history[idx][-1]
            if num_history > 1:
                self.exec_history(idx)
            else:
                self.history_label[idx].setText(tr('pu.history_prefix'))
                self.filtered_plot[idx].hide()

        # ループ後にAllタブのラベルを最新状態に更新
        if is_all and 'all' in self.history_label:
            # idxs[0]の履歴が残っているかで判断
            if len(self.history[idxs[0]]) > 0:
                txt = tr('pu.history_prefix') + \
                    '+'.join(set_bg_color(f'{m}{p}') for m, p in self.history[idxs[0]])
                self.history_label['all'].setText(txt)
            else:
                self.history_label['all'].setText(tr('pu.history_prefix'))
                # Allタブに対応するfiltered_plotも非表示
                for idx in idxs:
                    self.filtered_plot[idx].hide()

    def exec_history(self, idxs):
        idxs = [idxs] if isinstance(idxs, int) else idxs
        for idx in idxs:
            if len(self.history[idx]) == 0:
                continue
            print(f'Loaded {self.history=}')
            sf = SignalFilter(self.original_data.data[idx])
            self.data.data[idx] = sf.apply(self.history[idx]).data
            # RESET (Down sampling Freq.)
            t, _ = self.data.data[idx]
            current_fs = int(1 / (t[1] - t[0]))
            self.current_fs_label[idx].setText(f"Current Fs: {current_fs} Hz")
            self.ds_freq[idx].setValue(current_fs // 2)
            txt = tr('pu.history_prefix') + \
                '+'.join(set_bg_color(f'{method}{param}') for method, param in self.history[idx])
            self.history_label[idx].setText(txt)
            self.update_plot(idx)

    def save_parameters(self):
        with open("history.json", "w", encoding="utf-8") as f:
            json.dump(self.history, f, ensure_ascii=False, separators=(",", ":"))
        print(f'Save {self.history=}')

    def load_parameters(self):
        filename, _ = QFileDialog.getOpenFileName(
            self, "Load Parameters", "", "JSON Files (*.json)")
        with open(filename, "r", encoding="utf-8") as f:
            dt = json.load(f)
            self.history = {int(k): v for k, v in dt.items()}

        print(f'Load {self.history=}')
        for idx in self.history.keys():
            self.exec_history(idx)


class TabWindow(QDialog):
    """タブウィジェットを表示する別ウィンドウ"""

    def __init__(self, header, data0):
        super().__init__()
        self.setWindowTitle("Header Viewer - Tabs")
        self.resize(800, 900)
        # メインレイアウト
        self.layout = QVBoxLayout(self)
        # タブウィジェット
        self.tab_widget = QTabWidget()
        self.layout.addWidget(self.tab_widget)
        # ヘッダーデータの読み込み
        self.header = header
        self.load_header_data()
        # Timeinterval Histogram
        self.time, _ = data0.data[0]
        _, win = init_pg('')
        plt = plot_timeinterval_histogram(win, self.time)
        self.tab_widget.addTab(win, 'timeinterval histogram')

    def load_header_data(self):
        """self.headerのデータを読み取ってタブを作成"""
        current_index = -1
        for idx, (sheet, dic) in enumerate(self.header.__dict__.items()):
            if sheet == 'subject':
                current_index = idx
            # タブに追加
            table_widget = QTableWidget()
            self.tab_widget.addTab(table_widget, sheet)

            # データをテーブルに表示
            if sheet == "machine" and not isinstance(dic, dict):
                table_widget.setRowCount(1)
                table_widget.setColumnCount(1)
                table_widget.setItem(0, 0, QTableWidgetItem(str(dic)))
            else:
                self.display_dict_data(dic, table_widget)

        if current_index != -1:
            self.tab_widget.setCurrentIndex(current_index)

    def display_dict_data(self, dic, table_widget):
        """辞書型データをテーブルに表示"""
        rows = len(dic)
        table_widget.setRowCount(rows)
        table_widget.setColumnCount(2)  # キーと値の2列

        for row_idx, (key, lst) in enumerate(dic.items()):
            table_widget.setItem(row_idx, 0, QTableWidgetItem(str(key)))

            # lst がリストかどうか確認
            if isinstance(lst, list):
                value = ", ".join(map(str, lst))  # リストの場合は結合して表示
            else:
                value = str(lst)  # リストでない場合はそのまま文字列化
            table_widget.setItem(row_idx, 1, QTableWidgetItem(value))

#
# 変換系関数
#
#


def do_compute_time_varying_freq_amp(xy):
    pv_freq = PlotData()
    pv_freq.xlabel = xy.xlabel
    pv_freq.title = 'Freq. from peaks & valleys'
    pv_freq.subtitle = tr('pu.prominence_10pct')
    pv_amp = PlotData()
    pv_amp.xlabel = pv_freq.xlabel
    pv_amp.title = 'Amp. from peaks & valleys'
    pv_amp.subtitle = pv_freq.subtitle
    energy = PlotData()
    energy.title = 'Energy from peaks & valleys'
    energy.subtitle = pv_freq.subtitle
    energy.xlabel = pv_freq.xlabel
    power = PlotData()
    power.title = 'Power from peaks & valleys'
    power.subtitle = pv_freq.subtitle
    power.xlabel = pv_freq.xlabel
    for (x, y), l in zip(xy.data, xy.labels):
        prominence_value = 0.1 * (np.max(y) - np.min(y))
        peaks, _ = signal.find_peaks(y, height=None, distance=None, prominence=prominence_value)
        valleys, _ = signal.find_peaks(-y, height=None, distance=None, prominence=prominence_value)
        time, freq, amp = compute_time_varying_freq_amp(x, y, peaks, valleys)
        lab = {k: (v[0], '') for k, v in l.items()}
        pv_freq.add_series(time, freq, label=lab)
        pv_amp.add_series(time, amp, label=lab)
        # energy & powerを計算
        energy.add_series(time, (amp * freq)**2, label=lab)
        power.add_series(time, amp**2, label=lab)
    return pv_freq, pv_amp, energy, power

# wavelet変換用Class


@dataclass
class WaveletParams:
    # rangeOfFreq = [1.2, 2.2, 0.001] # 周波数[min,max,step]
    range: list = field(default_factory=lambda: [1.2, 3.0, 0.01])
    omega0: float = 6

    def __post_init__(self):
        if not (isinstance(self.range, (list, tuple)) and len(self.range) == 3):
            raise ValueError("range must be a list of 3 numbers [start, stop, step]")
        if self.range[2] <= 0 or self.omega0 <= 0:
            raise ValueError("range step and omega0 must be > 0")
        if self.range[0] >= self.range[1]:
            raise ValueError("range[0] must be less than range[1]")

    def to_dict(self):
        return asdict(self)

    @classmethod
    def from_dict(cls, d):
        return cls(**d)

    @classmethod
    def from_json(cls, filepath):
        with open(filepath, "r") as f:
            return cls.from_dict(json.load(f))

    def __repr__(self):
        return f"[INFO] WaveletParams(range={self.range}, omega0={self.omega0})"

    def __str__(self):
        return self.__repr__()

# wavelet変換


def do_wavelet_transform(xy, params: WaveletParams = WaveletParams()):
    data_skip = 2
    wv_data = PlotImageData()
    wv_data.xlabel = xy.xlabel
    wv_data.title = 'Scalogram'
    print(params)
    wv_data.subtitle = params  # f'{params.range=},{params.omega0=}'
    energy = PlotData()
    energy.title = 'Energy'
    energy.xlabel = wv_data.xlabel
    power = PlotData()
    power.title = 'Power'
    power.subtitle = wv_data.subtitle
    power.xlabel = wv_data.xlabel
    max_power_freq = PlotData()
    max_power_freq.title = 'Max power freq.'
    max_power_freq.subtitle = wv_data.subtitle
    max_power_freq.xlabel = wv_data.xlabel
    max_power_bpm = PlotData()
    max_power_bpm.title = 'Max power BPM'
    max_power_bpm.subtitle = wv_data.subtitle
    max_power_bpm.xlabel = wv_data.xlabel

    for (x, y), l in zip(xy.data, xy.labels):
        # wavelet変換(swanが処理できなくなるのでデータを半分間引く)
        x_sub = x[data_skip:-data_skip - 1:data_skip]
        y_sub = y[data_skip:-data_skip - 1:data_skip]
        # continuous wavelet transform実行
        freq, result = calc_wavelet(x_sub, y_sub, params)
        lab = {k: (v[0], 'Hz') for k, v in l.items()}
        wv_data.add_series(x_sub, freq, result, label=lab)
        # energy & power & max power freq を計算
        lab = {k: (v[0], '') for k, v in l.items()}
        energy.add_series(x_sub, ene := np.sum((result.T * freq)**2, axis=1), label=lab)
        lab = {k: (v[0], '') for k, v in l.items()}
        power.add_series(x_sub, np.sum(result.T**2, axis=1), label=lab)
        lab = {k: (v[0], 'Hz') for k, v in l.items()}
        # 各時間ステップで最大の power の index を取得
        max_power_indices = np.argmax(result, axis=0)  # shape: (n_times,)
        # index に対応する周波数を取得
        dominant_freqs = freq[max_power_indices]     # shape: (n_times,)
        threshold = 0.1 * np.max(result)  # 最大値の10%
        # dominant_freqs_filtered = np.where(
        #     power[max_power_indices, np.arange(result.shape[1])] > threshold,
        #     freqs[max_power_indices],
        #     np.nan  # 閾値未満は NaN
        # )
#        max_power_freq.add_series(x_sub, dominant_freqs_filtered, label=lab)
        max_power_freq.add_series(x_sub, dominant_freqs, label=lab)
        lab = {k: (v[0], 'bpm') for k, v in l.items()}
        max_power_bpm.add_series(x_sub, dominant_freqs * 60, label=lab)

    return wv_data, energy, power, max_power_freq, max_power_bpm


def do_power_spectrum(xy):
    ps = PlotData()
    ps.xlabel = {'bottom': ('Freq', 'Hz')}
    ps.title = 'Power Spectra'
    ps.subtitle = ''
    for (x, y), l in zip(xy.data, xy.labels):
        freq, power = compute_power_spectrum(x, y)
        lab = {k: (v[0], '') for k, v in l.items()}
        ps.add_series(freq, power, label=lab)

    return ps


def compute_power_spectrum(x, y):
    """
    パワースペクトルを計算する関数。
    Parameters:
        x (array-like): 時間軸またはx軸（等間隔であることが望ましい）
        y (array-like): 信号データ（y軸）

    Returns:
        freqs (ndarray): 周波数成分
        power (ndarray): パワースペクトル（振幅の2乗）
    """
    x = np.asarray(x)
    y = np.asarray(y)

    # サンプリング間隔（平均値で推定）
    dt = np.mean(np.diff(x))
    fs = 1.0 / dt  # サンプリング周波数
    # FFT
    fft_vals = np.fft.fft(y)
    fft_freqs = np.fft.fftfreq(len(y), d=dt)
    # パワースペクトル（正の周波数のみ）
    positive_freqs = fft_freqs > 0
    freqs = fft_freqs[positive_freqs]
    power = np.abs(fft_vals[positive_freqs])**2 / len(y)
    return freqs, power

# 移動平均を計算


def do_ma(xy, mva_sec):
    t = xy.data[0][0]
    delta_t = (t[-1] - t[0]) / (len(t) - 1)
    print(f'{delta_t=}, {mva_sec=}')
    window = int(float(mva_sec) / delta_t)
    mv = PlotData()
    mv.xlabel = xy.xlabel
    mv.title = tr('pu.mavg_title', title=xy.title, sec=mva_sec)
    mv.subtitle = xy.subtitle
    print(mv.title)
    for dt, l in zip(xy.data, xy.labels):
        lab = {k: (v[0], '') for k, v in l.items()}
        t, y = calc_ma(dt, window)
        mv.add_series(t, y, label=lab)
    return mv

# 累積和を計算


def calc_cumsum(xy):
    cm = PlotData()
    cm.xlabel = xy.xlabel
    cm.title = xy.title
    cm.subtitle = xy.subtitle
    for (t, y), l in zip(xy.data, xy.labels):
        lab = {k: (v[0], '') for k, v in l.items()}
        cm_y = np.cumsum(y)
        cm.add_series(t, cm_y, label=lab)
    return cm


# pyqtgraph用関数
#
# Initialize pyqtgraph
def init_pg(title):
    app = pg.mkQApp(title)
    win = pg.GraphicsLayoutWidget(show=True)
    win.setWindowTitle(title)
    win.setBackground('w')
    return app, win

# plot系関数


def decimate_for_range(x, y, x_min, x_max, max_points=5000):
    """
    表示範囲内のデータだけ抽出して間引く
    → ズームすると自動的に高解像度になる
    """
    # 表示範囲内のデータを抽出
    mask = (x >= x_min) & (x <= x_max)
    x_vis = x[mask]
    y_vis = y[mask]

    if len(x_vis) == 0:
        return x_vis, y_vis

    # 範囲内の点数がmax_points以下なら元データをそのまま使用
    if len(x_vis) <= max_points:
        return x_vis, y_vis

    # 多い場合は間引く
    step = len(x_vis) // max_points
    return x_vis[::step], y_vis[::step]


def decimate_fixed(x, y, max_points=5000):
    """均等間引き：最もシンプルで高速"""
    n = len(x)
    if n <= max_points:
        return x, y
    step = n // max_points
    return x[::step], y[::step]


def plot_timeseries(plots, xy):
    curves = []

    assert len(xy.data) == len(xy.labels) == len(plots.plts), "長さが一致していません"
    for (x, y), l, p, col in zip(xy.data, xy.labels, plots.plts, COLORS):
        set_axis_label(p, l)              # y軸ラベル
        x_d, y_d = decimate_fixed(x, y)  # ✅ 間引き
        print(tr('pu.decimate_points', before=len(x), after=len(x_d)))
        curves.append(p.plot(x_d, y_d, pen=pg.mkPen(color=col, width=5), skipFiniteCheck=True))

    # Region select
    set_axis_label(plots.p_base, xy.xlabel)  # x軸ラベル
    x_d0, y_d0 = decimate_fixed(xy.data[0][0], xy.data[0][1])
    p_base_plot = plots.p_base.plot(x_d0, y_d0, pen="black", skipFiniteCheck=True)

    region_mgr = RegionManager(plots.p_base, p_base_plot, plots.plts, curves=curves, xy=xy)

    cross_hair = CrossHairManager(mouseMoved, plots, xy)

    return curves, p_base_plot, region_mgr, cross_hair

# additional timeseries plot


def add_timeseries(plots, xy):
    curves = []
    assert len(xy.data) == len(xy.labels) == len(plots.plts), "長さが一致していません"
    for (x, y), l, p, col in zip(xy.data, xy.labels, plots.plts, COLORS[1:]):
        # set_axis_label(p, l)              # y軸ラベル
        x_d, y_d = decimate_fixed(x, y)  # ✅ 間引き
        curves.append(p.plot(x_d, y_d, pen=pg.mkPen(color=col, width=5)))
    return curves

# plot right axis (複数curve対応)


def plot_right_axis(plts_right, xys):
    curves_all = []
    for num, xy in enumerate(xys):
        curves = []
        assert len(xy.data) == len(xy.labels) == len(plts_right), "長さが一致していません"
        for (x, y), l, p, col in zip(xy.data, xy.labels, plts_right, COLORS[num + 1:]):
            # set_axis_label(p, l)              # y軸ラベル
            curve = pg.PlotDataItem(x, y, pen=pg.mkPen(color=col, width=5))
            p.addItem(curve)
            curves.append(curve)
        curves_all.append(curves)
    return curves_all


def plot_peaks(plots, xy, style='red_circle'):
    peaks = []
    for (x, y), p in zip(xy.data, plots.plts):
        peaks.append(p.plot(x, y, **style_dict[style]))
    return peaks


def calc_derivatives(xy):
    d1 = PlotData()
    d2 = PlotData()
    d1.xlabel = xy.xlabel
    d2.xlabel = xy.xlabel
    d1.title = f'1st derivatives'
    d2.title = f'2nd derivatives'
    for x, y in xy.data:
        dy = np.gradient(y, x)
        ddy = np.gradient(dy, x)
        d1.add_series(x, dy)
        d2.add_series(x, ddy)
    return d1, d2


def calc_peaks_and_valleys(xy):
    peaks_data = PlotData()
    peaks_data.xlabel = xy.xlabel
    peaks_data.title = tr('pu.prominence_10pct')
    valleys_data = PlotData()
    valleys_data.xlabel = xy.xlabel
    valleys_data.title = tr('pu.prominence_10pct')
    for x, y in xy.data:
        # yの変動幅に対して10%のprominence
        prominence_value = 0.1 * (np.max(y) - np.min(y))
        p_t, p_y = find_peaks_in_timeseries(x, y, prominence=prominence_value)
        v_t, v_y = find_peaks_in_timeseries(x, -y, prominence=prominence_value)
        peaks_data.add_series(p_t, p_y)
        valleys_data.add_series(v_t, -v_y)
    return peaks_data, valleys_data


def plot_scalogram(plots, xyz):
    img, colorbar = [], []
    for p, (t, f, r), l in zip(plots.plts, xyz.data, xyz.labels):
        im, cb = mk_image0(p, justify='right', values=(np.min(r), np.max(r)), ax_label=l)
        im.setImage(r.T)
        im.setRect(pg.QtCore.QRectF(t[0], f[0], t[-1] - t[0], f[-1] - f[0]))
        img.append(im)
        colorbar.append(cb)

    # Region select
    im, cb = mk_image0(plots.p_base, justify='right', values=(np.min(r), np.max(r)), ax_label=None)
    im.setImage(r.T)
    im.setRect(pg.QtCore.QRectF(t[0], f[0], t[-1] - t[0], f[-1] - f[0]))

    region_mgr = RegionManager(plots.p_base, im, plots.plts)
    colorbar.append(cb)
    img.append(im)
    # make cross hair Mouse moved
    cross_hair = CrossHairManager(mouseMovedImage, plots, xyz)

    return img, colorbar, region_mgr, cross_hair


def shift_image(im, t, f, offset):
    im.setRect(pg.QtCore.QRectF(t[0] - offset, f[0], t[-1] - t[0], f[-1] - f[0]))

# Calc. diff of the sampling time interval


def plot_timeinterval_histogram(win, time):
    diff_timeinterval = np.diff(time) * 1000
    title = tr('pu.time_interval_histogram_title')
    plt = win.addPlot(title=title)               # プロット領域を追加
    optimal_bins = auto_bins(diff_timeinterval)  # or get_optimal_bins(diff_timeinterval)
    y, x = np.histogram(diff_timeinterval, bins=optimal_bins)
    plt.plot(x, y, stepMode=True, fillLevel=0, brush=(0, 0, 255, 150))  # ヒストグラム描画
    plt.setLabels(left='Count', bottom=('Time Interval', 'ms'))        # 軸ラベル設定
    plt.showGrid(x=True, y=True)                                       # グリッド表示
    return plt


def calc_ma(data, window):  # 端を無視して「正確な部分」だけ使う（mode='valid'）
    t, y = data
    filtered_y = np.convolve(y, np.ones(window) / window, mode='valid')
    # filtered_yの長さは len(y) - window + 1
    start = window // 2
    end = start + len(filtered_y)
    t_new = t[start:end]
    return (t_new, filtered_y)

# filter系関数


def apply_filters(data, filter_history, cpt_lst=None):
    """
    filter_historyに従ってフィルタを適用する。
    cpt_lst: チェックポイントのリスト（省略可）
    """
    if cpt_lst is None:
        cpt_lst = []
    resolved = resolve_filter_params(filter_history, cpt_lst)
    return SignalFilter(data).apply(resolved).data


def resolve_filter_params(history, cpt_lst):
    resolved = []
    for method, params in history:
        new_params = []
        for p in params:
            if isinstance(p, dict) and 'mark' in p:
                if len(cpt_lst) == 0:
                    print(tr('pu.warn_cpt_lst_empty'))
                    new_params.append(0.0)
                else:
                    cpt_idx = p['mark']
                    if cpt_idx >= len(cpt_lst):
                        print(tr('pu.warn_index_out_of_range', idx=cpt_idx))
                        new_params.append(cpt_lst[-1])
                    else:
                        new_params.append(cpt_lst[cpt_idx])
            else:
                new_params.append(p)
        resolved.append([method, new_params])
    return resolved


def apply_default_filters(data_list, default_filter, cpt_lst=None):
    """
    Parameters
    ----------
    data_list : list of (t, y) タプル
    default_filter : dict or list
    cpt_lst : チェックポイントのリスト（省略可）

    Returns
    -------
    filter_history : dict  {idx: filter_history}
    data_list      : list  フィルタ適用後のデータ
    """
    if cpt_lst is None:
        cpt_lst = []
    num_data = len(data_list)

    if not default_filter:
        filter_history = {idx: [] for idx in range(num_data)}
    elif isinstance(default_filter, dict):
        filter_history = {int(key): val for key, val in default_filter.items()}
    elif isinstance(default_filter, list):
        filter_history = {idx: default_filter for idx in range(num_data)}
    else:
        print(tr('pu.warn_unsupported_filter_type', filter_type=type(default_filter)))
        filter_history = {idx: [] for idx in range(num_data)}

    for idx in range(num_data):
        if filter_history[idx]:
            data_list[idx] = apply_filters(data_list[idx], filter_history[idx], cpt_lst)

    return filter_history, data_list


def mouseMoved(evt, plots, vLine, hLine, xy):
    pos = evt
    x = xy.data[0][0]
    xlab, xunit = next(iter(xy.xlabel.values()))

    for p in plots.plts:
        if p.sceneBoundingRect().contains(pos):
            mousePoint = p.vb.mapSceneToView(pos)
            index = find_nearest(x, mousePoint.x())
            if index is not None and 0 <= index < len(x):
                label_text = make_title_span(
                    plots.title) + f'<span style="font-size: 12pt; color:green"> {xlab}={mousePoint.x():.5f}{xunit}'
                for (x, y), l, col in zip(xy.data, xy.labels, plots.color):
                    name, unit = next(iter(l.values()))
                    idx = find_nearest(x, mousePoint.x())
                    if 0 <= idx < len(y):
                        label_text += f", <span style='color:{col}'>{name}={
                            y[idx]:.2f}{unit}</span>"
                    else:
                        label_text += f", <span style='color:{col}'>{name}=---</span>"
                        # label_text += f", <span style='color:{col}'>{name}={y[index]:.2f}{unit}</span>"
                plots.label.setText(label_text)
            for v in vLine:
                v.setPos(mousePoint.x())
            for h in hLine:
                h.setPos(mousePoint.y())


def mouseMovedImage(evt, plots, vLine, hLine, xyz):
    pos = evt
    time = xyz.data[0][0]
    image_data = xyz.data[-1]   # 2]
    xlab, xunit = next(iter(xyz.xlabel.values()))
    ylab, yunit = next(iter(xyz.labels[0].values()))
    for p in plots.plts:
        if p.sceneBoundingRect().contains(pos):
            mouse_point = p.vb.mapSceneToView(pos)
            x, y = mouse_point.x(), mouse_point.y()
            # 画像の値を取得（境界チェック付き）
            if 0 <= x < time[-1] and 0 <= y < image_data[0].shape[0]:
                label_text = make_title_span(plots.title)
                label_text += f'<span style="font-size: 12pt"><span style="color:green"> {xlab}={
                    x:.2f}sec({
                    x /
                    60:.2f}min),</span> <span style="color: blue">{ylab}={
                    y:.2f}Hz({
                    y *
                    60:.1f}bpm)'
                plots.label.setText(label_text)
            for v in vLine:
                v.setPos(x)
            for h in hLine:
                h.setPos(y)


def make_title_span(str):
    return f'<span style="background-color: #333333; color: #e6e6e6; font-size: 13pt; padding: 3px 6px;">{str}:</span>'

##
# win add系関数
##
# make plot


def mk_plot(win, layout):
    plt = win.addPlot(row=layout[0], col=layout[1])
    plt.avgPen = pg.mkPen('#000000')
    plt.avgShadowPen = pg.mkPen('#8080DD', width=10)
#    plt.getViewBox().setBackgroundColor('#DDDDDD')  # 灰色
    plt.showGrid(x=True, y=True, alpha=0.8)
    plt.setAutoVisible(y=True)
    win.ci.layout.setRowStretchFactor(layout[0], layout[2])  # set StretchFactor
    return plt

# add plot


def add_right_axis(p1, label="Derivatives", color='g'):
    p2 = pg.ViewBox()
    p1.showAxis('right')
    p1.getAxis('right').linkToView(p2)
    p1.getAxis('right').setLabel(label, color=color)
    p1.scene().addItem(p2)
    p2.setXLink(p1)

    def updateViews():
        p2.setGeometry(p1.vb.sceneBoundingRect())
        p2.linkedViewChanged(p1.vb, p2.XAxis)

    updateViews()
    p1.vb.sigResized.connect(updateViews)
    return p2

# make label


def mk_label(win, layout, justify):
    label = pg.LabelItem(justify=justify)
    win.addItem(label)
    win.ci.layout.setRowStretchFactor(layout[0], layout[2])  # set StretchFactor
    return label

# make image


def mk_image0(plt, justify, values, ax_label):
    cmap = pg.colormap.getFromMatplotlib("jet")
    img = pg.ImageItem(justify=justify)
    plt.addItem(img)
    img.setColorMap(cmap)
    colorbar = plt.addColorBar(img, colorMap=cmap, values=values)
    set_axis_label(plt, ax_label)              # 軸ラベル
    return img, colorbar

# make image


def mk_image(win, layout, justify, values, ax_label):
    p = win.addPlot(row=layout[0], col=layout[1])
    # Set a custom color map
    # colors = [(0, 0, 0), (45, 5, 61),(84, 42, 55),(150, 87, 60),(208, 171, 141),(255, 255, 255)]
    # cmap = pg.ColorMap(pos=np.linspace(0.0, 1.0, 6), color=colors)
    # cmap='plasma' #viridis, plasma, magma, inferno, cividis[rf.
    # site-packages/pyqtgraph/colors/maps/]
    cmap = pg.colormap.getFromMatplotlib("jet")
    img = pg.ImageItem(justify=justify)
    p.addItem(img)
    img.setColorMap(cmap)
    p.addColorBar(img, colorMap=cmap, values=values)
    set_axis_label(p, ax_label)              # 軸ラベル
#    p.setLabel("bottom", ax_label[0])  # x軸にラベルを設定
#    p.setLabel("left", ax_label[1])   # y軸にラベルを設定
    win.ci.layout.setRowStretchFactor(layout[0], layout[2])  # set StretchFactor
    return p, img


# set axis label  (ex) ax_label = {'bottom': ('Time', 'sec'), 'left': ('Amplitude', 'V')}
def set_axis_label(p, ax_label):
    if ax_label:
        for axis, (label, unit) in ax_label.items():
            p.setLabel(axis, label, units=unit)

# plot vertical lines at Checkpoint positions


def plot_cpt_lines(plts, cpt_list, offset):
    lines = []
    for x in cpt_list:
        for p in plts:
            ln = v_line(x - offset, 'magenta')
            p.addItem(ln)
            lines.append((p, ln))
    return lines

# plot vertical lines at LT, PRE11-PRE13


def plot_additional_lines(plts, vline_dict):
    lines = []
    if vline_dict is not None:
        print(f'{vline_dict=}')
        for lab, x in vline_dict.items():
            if x is None or np.isnan(x):
                continue
            col = 'red' if lab == 'LT' else 'yellow'
            for p in plts:
                ln = v_line(x, col)
                p.addItem(ln)
                lines.append((p, ln))
    return lines


def v_line(pos, col):
    return pg.InfiniteLine(pos=pos, angle=90, pen=pg.mkPen(color=col, width=4))

# make checkbox
#  (ex. plotの表示・非表示を選択)
#  return: チェックボックスとラベルのリスト


def mk_checkbox(labels, func, isChecked=True):
    checkboxes_layout = QHBoxLayout()
    checkboxes = []
    for lab in labels:
        checkbox_layout = QVBoxLayout()
        checkbox = QCheckBox("")
        checkbox.setChecked(isChecked)                              # 初期状態は選択済み
        checkbox_layout.addWidget(QLabel(f"{lab}"))
        checkbox_layout.addWidget(checkbox)
        checkbox.stateChanged.connect(func)
        checkboxes.append((lab, checkbox))
        checkboxes_layout.addLayout(checkbox_layout)
    return checkboxes_layout, checkboxes


# make radiobutton
# (ex. checkpointsのlistで初期時間をshiftさせる。初期選択値はsel)
def mk_radiobuttons(num, sel, func):
    radiobuttons_layout = QHBoxLayout()
    button_group = QButtonGroup()
    button_group.setExclusive(True)  # ラジオボタンを排他選択モードに設定
    for lab in range(num):
        radiobutton_layout = QVBoxLayout()
        label = QLabel(f"{lab}")
        radiobutton = QRadioButton("")
        radiobutton_layout.addWidget(label)
        radiobutton_layout.addWidget(radiobutton)
        if lab == sel:
            radiobutton.setChecked(True)  # 最初のボタンを選択状態
        button_group.addButton(radiobutton, id=lab)
        radiobutton.toggled.connect(func)  # ラジオボタンの選択時の動作を接続
        radiobuttons_layout.addLayout(radiobutton_layout)
    return radiobuttons_layout, button_group


def create_shift_input(
        label_text="Shift time(sec)",
        placeholder=None,
        max_length=10,
        tooltip=None):
    """
    Shift 入力用のラベル付きレイアウトを返す。

    Returns:
        QWidget: ラベルと QLineEdit を含む縦レイアウト widget
        QLineEdit: 入力フィールド（呼び出し元で値取得用に使う）
    """
    # デフォルト引数はimport時に一度だけ評価されるため、--langが確定してから
    # 呼ばれる関数本体側でカタログを引く（Noneセンチネルで遅延解決）。
    if placeholder is None:
        placeholder = tr('pu.shift_placeholder')
    if tooltip is None:
        tooltip = tr('pu.shift_tooltip')
    container = QWidget()
    layout = QVBoxLayout(container)
    label = QLabel(label_text)
    label.setToolTip(tooltip)
    layout.addWidget(label)

    line_edit = QLineEdit()
    line_edit.setPlaceholderText(placeholder)
    line_edit.setValidator(QIntValidator())
    line_edit.setMaxLength(max_length)
    line_edit.setFixedWidth(line_edit.fontMetrics().width('9' * max_length))

    layout.addWidget(line_edit)
    return container, line_edit


def create_labeled_slider(
        title: str,
        minimum: int,
        maximum: int,
        initial: int,
        interval: int = 1,
        orientation=Qt.Horizontal):
    """
    スライダーとラベルを一体化して返すウィジェットを生成。
    Parameters:
        title (str): ラベルのタイトル（何のスライダーか）
        minimum (int): スライダーの最小値
        maximum (int): スライダーの最大値
        initial (int): 初期値
        interval (int): 目盛の間隔
        orientation (Qt.Orientation): Qt.Horizontal または Qt.Vertical
    Returns:
        QWidget: スライダーとラベルを含むウィジェット
        QSlider: スライダーオブジェクト（外部からアクセス可能）
    """
    container = QWidget()
    layout = QVBoxLayout() if orientation == Qt.Horizontal else QVBoxLayout()

    label = QLabel(f"{title}: {initial}sec")
    slider = QSlider(orientation)
    slider.setRange(minimum, maximum)
    slider.setValue(initial)
    slider.setTickInterval(interval)
    slider.setTickPosition(QSlider.TicksBelow if orientation ==
                           Qt.Horizontal else QSlider.TicksLeft)

    # スライダーの値が変わったらラベルも更新
    slider.valueChanged.connect(lambda value: label.setText(f"{title}: {value}sec"))

    layout.addWidget(label)
    layout.addWidget(slider)
    container.setLayout(layout)

    return container, slider


def set_bg_color(history):
    color = bg_colors[history[:2]]
    return f"<span style='background-color: {color};'> {history} </span>"


####
def find_peaks_in_timeseries(t, y, height=None, distance=None, prominence=None):
    """
    時系列データからピークの位置と値を検出

    Parameters:
        t (array-like): 時刻の配列
        y (array-like): 値の配列
        height (float or tuple, optional): ピークの最小/最大高さ
        distance (int, optional): ピーク間の最小距離（サンプル数）
        prominence (float, optional): ピークの目立ち度（prominence）

    Returns:
        peaks_t (np.ndarray): ピークの時刻
        peaks_y (np.ndarray): ピークの値
    """
    peaks, _ = signal.find_peaks(y, height=height, distance=distance, prominence=prominence)
    peaks_t = np.array(t)[peaks]
    peaks_y = np.array(y)[peaks]
    return peaks_t, peaks_y


def pair_peaks_valleys(peaks, valleys):
    """ピークごとに最近傍の谷をペアリング"""
    pairs = []
    for p in peaks:
        # 距離が最も近い valley を探す
        if len(valleys) == 0:
            continue
        idx = np.argmin(np.abs(valleys - p))
        v = valleys[idx]
        # 左右の順序は問わず登録
        pairs.append((min(p, v), max(p, v)))
    return pairs


def compute_time_varying_freq_amp(t, y, peaks, valleys):
    pairs = pair_peaks_valleys(peaks, valleys)

    freqs = []
    amps = []
    times = []

    for i, (i1, i2) in enumerate(pairs):
        try:
            if np.isnan(y[i1]) or np.isnan(y[i2]):
                continue
            dt = np.abs(t[i2] - t[i1])
            dy = np.abs(y[i2] - y[i1])
            if dt == 0:
                continue
            freqs.append(1.0 / dt)
            amps.append(dy / 2)
            times.append((t[i1] + t[i2]) / 2)
        except Exception as e:
            print(tr('pu.error_at_pair', i=i, err=e))
            continue

    return np.array(times), np.array(freqs), np.array(amps)

####
# arrayの中でvalueに最も近い値のindexを返す


def find_nearest(array, value):
    """ソート済み配列に対して二分探索で最近傍indexを返す"""
    if array is None or len(array) == 0:
        return None
    idx = np.searchsorted(array, value)
    # 境界チェック
    if idx == 0:
        return 0
    if idx >= len(array):
        return len(array) - 1
    # value が array[idx-1] と array[idx] のどちらに近いか
    if abs(array[idx - 1] - value) <= abs(array[idx] - value):
        return idx - 1
    return idx


def calc_wavelet(x, y, params):
    from swan import pycwt   # pip install swan でinstallする必要あり
    dt = (x[-1] - x[0]) / (len(x) - 1)
    Fs = 1 / dt
    freqs = np.arange(*params.range)
    wavelet = pycwt.Morlet(params.omega0)    # Morlet wavelet 生成
    r = pycwt.cwt_f(y, freqs, Fs, wavelet)
    return freqs, np.abs(r)

# For Histogram


def auto_bins(data):
    # Freedman-Diaconisの方法
    iqr = np.percentile(data, 75) - np.percentile(data, 25)
    h = 2 * iqr / (len(data) ** (1 / 3))  # bin幅
    bins = int((np.max(data) - np.min(data)) / h)
    return max(10, bins)  # 最低10bins

# または


def get_optimal_bins(data):
    # Scottの標準偏差に基づく方法
    h = 3.49 * np.std(data) * (len(data) ** (-1 / 3))
    bins = int((np.max(data) - np.min(data)) / h)
    return max(10, bins)

# Save関数


def save_header(header, excelfile):
    start = time.perf_counter()
    column_cpt = ['real time', 'time']
    with pd.ExcelWriter(excelfile) as writer:
        pd.DataFrame(header.time['check_points'],
                     columns=column_cpt,
                     index=range(1,
                                 len(header.time['check_points']) + 1)).to_excel(writer,
                                                                                 sheet_name='Mark_points',
                                                                                 index=True,
                                                                                 header=True)
    wb = load_workbook(filename=excelfile)
    for sheet, dic in header.__dict__.items():
        ws = wb.create_sheet(sheet)
        if sheet == 'machine' and type(dic) is not dict:
            ws.append([str(dic)])
        else:
            for key, lst in dic.items():
                ws.append([key, str(lst)])
    wb.save(excelfile)
    wb.close()
    print(tr('pu.auto_saving_header', excelfile=excelfile, sec=time.perf_counter() - start))


class CrossHairManager:
    """クロスヘアの生成・マウス連動を管理するクラス"""

    THROTTLE_MS = 16  # 60fps相当

    def __init__(self, funcMouseMoved, plots, xy):
        """
        funcMouseMoved : マウス移動時に呼ぶ関数
        plots          : プロット群オブジェクト
        xy             : ラベル等の表示オブジェクト
        """
        # --- 状態をインスタンス変数として保持 ---
        self.funcMouseMoved = funcMouseMoved
        self.plots = plots
        self.xy = xy
        self._last_update = 0          # スロットリング用タイムスタンプ

        # クロスヘアを生成してシグナル接続
        self.vLine, self.hLine = self._mk_cross_hair()
        self._connect_signals()

    # -------------------------------------------------- #
    #  クロスヘア生成                                      #
    # -------------------------------------------------- #
    def _mk_cross_hair(self):
        """各プロットにクロスヘアラインを追加して返す"""
        vLine, hLine = [], []
        for p in self.plots.plts:
            vl = pg.InfiniteLine(angle=90, movable=False,
                                 pen=pg.mkPen(color='cyan', width=2))
            hl = pg.InfiniteLine(angle=0, movable=False,
                                 pen=pg.mkPen(color='cyan', width=2))
            p.addItem(vl, ignoreBounds=True)
            p.addItem(hl, ignoreBounds=True)
            vLine.append(vl)
            hLine.append(hl)
        return vLine, hLine

    # -------------------------------------------------- #
    #  シグナル接続                                        #
    # -------------------------------------------------- #
    def _connect_signals(self):
        """各プロットのマウス移動シグナルを接続する"""
        for p in self.plots.plts:
            p.scene().sigMouseMoved.connect(self._on_mouse_moved)

    # -------------------------------------------------- #
    #  マウス移動ハンドラ（スロットリング付き）             #
    # -------------------------------------------------- #
    def _on_mouse_moved(self, evt):
        """シグナルから直接呼ばれるメソッド"""
        now = time.monotonic() * 1000
        if now - self._last_update < self.THROTTLE_MS:
            return                        # スキップ
        self._last_update = now

        # 元の funcMouseMoved を呼び出す
        self.funcMouseMoved(
            evt,
            self.plots,
            self.vLine,
            self.hLine,
            self.xy
        )

    def cleanup(self):
        """シーンからクロスヘアを安全に削除する"""
        for p, vl, hl in zip(self.plots.plts, self.vLine, self.hLine):
            try:
                if vl.scene() is not None:
                    p.removeItem(vl)
                if hl.scene() is not None:
                    p.removeItem(hl)
            except Exception:
                pass


class RegionManager:
    """LinearRegionの生成・更新を管理するクラス"""

    THROTTLE_MS = 32  # ~30fps（regionはcrosshairより低くてOK）

    def __init__(self, p_base, plotted_data, plt, curves=None, xy=None):
        self.curves = curves  # ✅ 追加
        self.xy = xy      # ✅ 追加（元データ参照用）
        self.x_shift = 0.0
        self.p_base = p_base
        self.plotted_data = plotted_data
        self.plt = plt
        self._last_region_update = 0
        self._last_range_update = 0
        self._updating = False  # 再帰的更新防止フラグ
        self._initialized = False  # ✅ 追加

        # region生成・接続
        self.region = self._mk_region()
        self._connect_signals()

        # 初期範囲を遅延設定
        QtCore.QTimer.singleShot(0, self._set_initial_region)

    # -------------------------------------------------- #
    #  region生成                                         #
    # -------------------------------------------------- #
    def _mk_region(self):
        region = pg.LinearRegionItem(swapMode='block')
#        region = pg.LinearRegionItem()
        region.setZValue(10)
        for line in region.lines:
            line.setPen(pg.mkPen(color='yellow', width=10))
            line.setHoverPen(pg.mkPen(color='red', width=12))
        self.p_base.addItem(region, ignoreBounds=True)
        return region

    # -------------------------------------------------- #
    #  シグナル接続                                        #
    # -------------------------------------------------- #
    def _connect_signals(self):
        # regionの変更シグナル
        self.region.sigRegionChanged.connect(self._on_region_changed)

        # 各プロットのレンジ変更シグナル
        for p in self.plt:
            if not hasattr(p, '_region_update_connected'):
                p.sigRangeChanged.connect(self._on_range_changed)
                p._region_update_connected = True

    # -------------------------------------------------- #
    #  初期region範囲設定                                  #
    # -------------------------------------------------- #
    def _set_initial_region(self):
        if isinstance(self.plotted_data, pg.PlotDataItem):
            x_values = self.plotted_data.xData
            if x_values is None or len(x_values) == 0:
                QtCore.QTimer.singleShot(100, self._set_initial_region)
                return
            min_x, max_x = np.min(x_values), np.max(x_values)
        elif isinstance(self.plotted_data, pg.ImageItem):
            view_range = self.p_base.getViewBox().viewRange()
            min_x, max_x = view_range[0][0], view_range[0][1]
            if min_x == 0 and max_x == 1:
                QtCore.QTimer.singleShot(100, self._set_initial_region)
                return
        else:
            print(tr('pu.unsupported_region_type'))
            return

        range_width = max_x - min_x
        start = min_x
        end = start + range_width * 0.7
        self.region.setRegion([start, end])
        self._initialized = True  # ✅ 設定完了

    def set_x_shift(self, shift):
        self.x_shift = shift

    # -------------------------------------------------- #
    #  regionが動いたとき → プロットのx範囲を更新          #
    # -------------------------------------------------- #
    def _on_region_changed(self):
        # スロットリング
        now = time.monotonic() * 1000
        if now - self._last_region_update < self.THROTTLE_MS:
            return
        self._last_region_update = now

        # 再帰防止
        if self._updating:
            return
        self._updating = True

        try:
            min_x, max_x = self.region.getRegion()
            for p in self.plt:
                p.setXRange(min_x, max_x, padding=0)

            # ✅ 表示範囲内のデータを高解像度で再描画
            if self.curves and self.xy:
                for cur, (x, y) in zip(self.curves, self.xy.data):
                    x_shifted = x - self.x_shift  # ✅ シフトを適用
                    x_d, y_d = decimate_for_range(x_shifted, y, min_x, max_x)
                    cur.setData(x_d, y_d)

        finally:
            self._updating = False

    def _on_range_changed(self, view, range_):
        # ✅ 初期化完了前は無視する
        if not self._initialized:
            return

        # スロットリング
        now = time.monotonic() * 1000
        if now - self._last_range_update < self.THROTTLE_MS:
            return
        self._last_range_update = now

        # 再帰防止
        if self._updating:
            return
        self._updating = True

        try:
            x_range = range_[0]  # [[xmin,xmax],[ymin,ymax]]
            self.region.setRegion(x_range)
        finally:
            self._updating = False

    def cleanup(self):
        """シーンからアイテムを安全に削除する"""
        try:
            if self.region.scene() is not None:
                self.p_base.removeItem(self.region)
        except Exception:
            pass


class SignalFilter:
    """
    信号平滑化フィルタ群をまとめたクラス。
    data = (t, y) のタプルを受け取り、各フィルタを適用して返す。
    """

    METHOD_MAP = {
        'DS': 'downsample',
        'MA': 'moving_average',
        'LP': 'lowpass',
        'BN': 'bandnotch',
        'BP': 'bandpass',
        'TR': 'trim',
    }

    def __init__(self, data: tuple):
        """
        Parameters
        ----------
        data : (t, y) のタプル
        """
        self.t, self.y = data

    @property
    def data(self) -> tuple:
        return (self.t, self.y)

    @property
    def fs(self) -> float:
        """現在のサンプリング周波数 [Hz]"""
        return 1 / (self.t[1] - self.t[0])

    @property
    def nyq(self) -> float:
        """ナイキスト周波数 [Hz]"""
        return self.fs / 2

    # ------------------------------------------------------------------ #
    #  各フィルタメソッド（in-placeで self.t, self.y を更新して self を返す）
    # ------------------------------------------------------------------ #

    def trim(self, t_min: float, t_max: float = None, reset_t0: bool = False) -> "SignalFilter":
        """
        時系列を指定範囲 [t_min, t_max] でカットする
        """
        if t_min is None:
            t_min = self.t[0]
        if t_max is None:
            t_max = self.t[-1]  # Noneの場合はデータの最大値を使用
        mask = (self.t >= t_min) & (self.t <= t_max)
        self.t = self.t[mask]
        self.y = self.y[mask]
        if reset_t0:
            self.t = self.t - self.t[0]  # t_min の時点を 0 にオフセット
        return self

    def downsample(self, new_fs: int, is_anti_alias: bool) -> "SignalFilter":
        downsample_factor = int(self.fs) // new_fs
        if is_anti_alias:
            cutoff = new_fs / 2
            normalized_cutoff = cutoff / self.nyq
            print(f'{self.fs=}, {normalized_cutoff=}, {cutoff=}, {self.nyq=}')
            b, a = signal.butter(4, normalized_cutoff, btype='low')
            y_proc = signal.filtfilt(b, a, self.y)
        else:
            y_proc = self.y
        print('Down sampling')
        self.t = self.t[::downsample_factor]
        self.y = y_proc[::downsample_factor]
        return self

    def moving_average(self, window: int) -> "SignalFilter":
        """端を無視して「正確な部分」だけ使う（mode='valid'）"""
        filtered_y = np.convolve(self.y, np.ones(window) / window, mode='valid')
        start = window // 2
        end = start + len(filtered_y)
        self.t = self.t[start:end]
        self.y = filtered_y
        return self

    def lowpass(self, cutoff: float) -> "SignalFilter":
        norm_cutoff = cutoff / self.nyq
        if not (0 < norm_cutoff < 1):
            raise ValueError(tr('pu.cutoff_range_error', cutoff=cutoff, nyq=self.nyq))
        b, a = signal.butter(4, norm_cutoff, btype='low')
        self.y = signal.filtfilt(b, a, self.y)
        print('Lowpass filter')
        return self

    def bandnotch(self, f0: float, Q: float) -> "SignalFilter":
        w0 = f0 / self.nyq
        b, a = signal.iirnotch(w0, Q)
        self.y = signal.filtfilt(b, a, self.y)
        return self

    def bandpass(self, lowcut: float, highcut: float) -> "SignalFilter":
        low = lowcut / self.nyq
        high = highcut / self.nyq
        if not (0 < low < high < 1):
            raise ValueError(f"Invalid frequency range: {low=}, {high=}")
        baseline = np.mean(self.y)
        sos = signal.butter(4, [low, high], btype='band', output='sos')
        self.y = signal.sosfiltfilt(sos, self.y)
        self.y += baseline
        return self

    # ------------------------------------------------------------------ #
    #  パイプライン実行
    # ------------------------------------------------------------------ #

    def apply(self, history: list) -> "SignalFilter":
        """
        history のリストに従って連続でフィルタを適用する。

        Parameters
        ----------
        history : [('DS', (new_fs, is_anti_alias)), ('LP', (cutoff,)), ...] の形式
        """
        for method_key, params in history:
            method_name = self.METHOD_MAP.get(method_key)
            if method_name is None:
                print(tr('pu.unsupported_method', method=method_key))
                continue
            getattr(self, method_name)(*params)
        return self
