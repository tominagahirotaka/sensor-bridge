#!/usr/bin/env python3
"""
sensor-bridge: graph display module
Displays acquired sensor data in real time.
"""
# Defers type-annotation evaluation (e.g. build_wavelet_params's "->
# WaveletParams" below) so mylib.plot_utils can be imported lazily -- see
# the comment above its import in main().
from __future__ import annotations

import argparse
import ast
import contextlib
import copy
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
from concurrent.futures import ProcessPoolExecutor
from datetime import datetime


# Fixed position/total for every heavy import this file times, so the
# printed "[n/5]" stays consistent no matter when each one actually runs
# (the first 4 always run at startup, in this order; PyPDF2 only runs
# later, on PDF export -- see append_window_to_pdf()).
_TIMED_IMPORT_TOTAL = 5


@contextlib.contextmanager
def _timed_import(label, step):
    """Print progress before/after an import, so a genuinely slow one
    (antivirus real-time scanning of a compiled extension, a slow
    network-mounted profile dir -- reported by a student whose terminal
    just sat there with no output during a multi-minute scipy/PyPDF2
    import) shows up as a specific, timestamped, numbered line instead of
    a silently frozen terminal. flush=True matters here: stdout is
    line-buffered on a real terminal but fully buffered when redirected
    (e.g. into a log file), so without it these lines could sit in the
    buffer for the whole hang instead of appearing when they're printed."""
    prefix = f'[{step}/{_TIMED_IMPORT_TOTAL}]'
    print(f'[INFO] {prefix} importing {label}...', flush=True)
    t0 = time.time()
    yield
    print(f'[INFO] {prefix} ...{label} imported ({time.time() - t0:.1f}s)', flush=True)


with _timed_import('numpy', 1):
    import numpy as np
with _timed_import('pandas', 2):
    import pandas as pd
with _timed_import('PyQt5', 3):
    from PyQt5.QtCore import Qt, QRect, QSizeF, QTimer
    from PyQt5.QtGui import QIcon, QPainter, QPdfWriter
    from PyQt5.QtSvg import QSvgGenerator
    from PyQt5.QtWidgets import (QApplication, QCheckBox, QFileDialog,
                                 QGroupBox, QGridLayout, QLabel, QMainWindow,
                                 QMenu, QMessageBox, QPushButton, QVBoxLayout,
                                 QWidget)

import mylib.i18n as i18n
from mylib.debug_utils import debug_print
from mylib.i18n import t
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
            args = ast.literal_eval(f"[{args}")  # safely evaluate as a list
            history.append([name.strip(), args])
    return history


def merge_filter_and_history(filter_dict, history_dict):
    """Merge the default Filter and the SignalSmoothingWindow's operation
    History into a single dict (for the same key, Filter entries come
    first, followed by History entries)."""
    merged = {}
    all_keys = list(dict.fromkeys(list(filter_dict.keys()) + list(history_dict.keys())))
    for key in all_keys:
        merged[key] = []
        if key in filter_dict:
            merged[key].extend(filter_dict[key])  # filter comes first
        if key in history_dict:
            merged[key].extend(history_dict[key])  # history comes after
    return merged


graph_type = [
    # The tooltip field is an i18n catalog key; t() is called on the
    # setToolTip side (since this list is evaluated before --lang is
    # resolved, calling t() directly here would always freeze it to the
    # language at startup).
    ('Timeseries', lambda obj: obj.current_data, ['plot'], 'plot.tt.timeseries'),
    # 'freq': the X axis is Freq.(Hz), not Time. Time-based operations like Mark/Shift time don't apply.
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
    # get the indices that include 'image'
    image = [k for k, (_, _, modes, _) in enumerate(graph_type) if 'image' in modes]
    # get the indices that include 'wavelet'
    wavelet = [k for k, (_, _, modes, _) in enumerate(graph_type) if 'wavelet' in modes]
    # get the indices that include 'freq' (X axis is not Time)
    freq = [k for k, (_, _, modes, _) in enumerate(graph_type) if 'freq' in modes]
    return (name, func, image, wavelet, freq, tooltip)


(graph_name, graph_func, image_lst, wavelet_lst, freq_lst,
 graph_tooltip) = decompose_graph_type(graph_type)

graph_lst = {}
graph_lst['Analog_Sensor'] = ['Timeseries', 'PowerSpectra', 'Scalogram']
graph_lst['SHT35'] = ['Timeseries', 'PowerSpectra', 'Scalogram']
graph_lst['LIS3DH'] = ['Timeseries', 'PowerSpectra', 'Scalogram']


def resolve_graph_visibility(board_prog, graph_lst, graph_name):
    """Find the graph_lst entry matching board_prog (the board's title), and
    return a Boolean list of whether each element of graph_name is
    displayable for that board (all True if no matching entry exists)."""
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
            self.prepare_data(filename)  # load the data
            self.variable_parts()
        else:
            self.num_plots = 1
            self.dirname = default_dir

        # label, plots, p_base (placed within win)
        self.plots = pltutils.InitPlots(self.win, self.num_plots)
        if filename:
            self.update_plot()

    def initUI(self, args):
        # create the main widget and layout
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

        # file selection button
        self.file_selection_button = QPushButton(t('plot.gui.open_file'))
        self.file_selection_button.setToolTip(t('plot.gui.open_file_tip'))
        self.file_selection_button.clicked.connect(self.open_file_select_dialog)

        # Save Graph button (image: PDF/PNG of the currently displayed graph)
        self.image_save_button = QPushButton(t('plot.gui.save_graph'))
        self.image_save_button.setToolTip(t('plot.gui.save_graph_tip'))
        self.image_save_button.clicked.connect(self.open_image_save_dialog)

        # Save Data button (Excel/CSV export)
        self.file_write_button = QPushButton(t('plot.gui.save_data'))
        self.file_write_button.setToolTip(t('plot.gui.save_data_tip'))
        self.file_write_button.clicked.connect(self.open_file_write_dialog)

        # Signal Smoothing button
        self.smoothing_window = None   # variable holding the smoothing window
        self.smoothing_button = QPushButton(t('plot.gui.smoothing'))
        self.smoothing_button.setToolTip(t('plot.gui.smoothing_tip'))
        self.smoothing_button.clicked.connect(self.open_smoothing_window)

        # Wavelet Parameters button (edit range/omega0 without relaunching
        # plot.py -- see open_wavelet_param_window())
        self.wavelet_param_window = None   # variable holding the wavelet-params window
        self.wavelet_param_button = QPushButton(t('plot.gui.wavelet_params'))
        self.wavelet_param_button.setToolTip(t('plot.gui.wavelet_params_tip'))
        self.wavelet_param_button.clicked.connect(self.open_wavelet_param_window)

        # Graph selection button
        self.graph_actions = {}
        self.graph_sel_button = QPushButton(t('plot.gui.select_graph'), self)
        self.graph_sel_button.setToolTip(t('plot.gui.select_graph_tip'))
        self.graph_sel_menu = QMenu(self)        # create the menu
        self.graph_sel_menu.setToolTipsVisible(True)
        for name in graph_name:
            self.graph_actions[name] = self.graph_sel_menu.addAction(f'{name}', self.select_graph)
            self.graph_actions[name].setToolTip(t(graph_tooltip[name]))
        self.graph_sel_button.setMenu(self.graph_sel_menu)  # attach the menu to the button

        # INFO button
        self.info_window = None     # variable holding the Information window
        self.info_button = QPushButton(t('plot.gui.info'))
        self.info_button.setToolTip(t('plot.gui.info_tip'))
        self.info_button.clicked.connect(self.open_info_window)

        # Full Range button (toggles the bottom row's selected range between full range <-> the previous range)
        self.full_range_button = QPushButton(t('plot.gui.full_range'))
        self.full_range_button.setToolTip(t('plot.gui.full_range_tip'))
        self.full_range_button.setCheckable(True)  # change the background color while full-range display is active, for visibility
        self.full_range_button.setStyleSheet(
            "QPushButton:checked { background-color: #ffca28; }")
        self.full_range_button.clicked.connect(self.toggle_full_range)

        # Quit button
        self.quit_button = QPushButton(t('plot.gui.quit'), self)
        self.quit_button.setToolTip(t('plot.gui.quit_tip'))
        self.quit_button.clicked.connect(self.closeApp)

        # Port selection (GroupBox & checkbox)
        self.port_selection = QGroupBox(t('plot.gui.select_port'))

        # Peaks display
        self.peaks_check = QCheckBox('Peak')
        self.peaks_check.setToolTip(t('plot.gui.peak_tip'))
        if self.args.peaks:
            self.peaks_check.setChecked(True)

        # Mark (checkpoint) display
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
            QWidget().setLayout(self.derivatives.layout())  # remove the existing layout
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

        # add the control layout
        # row, column, rowspan (number of cells vertically), colspan (number of cells horizontally)
        widgets = [
            (self.title_label, 0, 0, 1, 7),
            (self.file_selection_button, 1, 0),
            (self.mv_layout, 2, 0, 1, 5),
            (self.label2, 2, 7, 1, 5),
            (self.image_save_button, 1, 1),
            (self.file_write_button, 1, 2),
            (self.smoothing_button, 1, 3),
            (self.wavelet_param_button, 1, 4),
            (self.full_range_button, 1, 5),
            (self.graph_sel_button, 1, 6),
            (self.peaks_check, 1, 7),
            (self.mark_check, 1, 8),
            (self.LT_check, 1, 9),
            (self.PRE_check, 1, 10),
            (self.port_selection, 0, 11, 2, 1),
            (self.time_shift, 0, 12, 2, 1),
            (self.shift_layout, 0, 13, 2, 1),
            (self.derivatives, 0, 14, 2, 1),
            (self.label3, 0, 15, 1, 2),
            (self.info_button, 1, 15),
            (self.quit_button, 1, 16)
        ]
        for wid in widgets:
            self.control_layout.addWidget(*wid)
        layout.addLayout(self.control_layout)

        # create the graph widget
        _, self.win = pltutils.init_pg('')
        layout.addWidget(self.win)

        if self.args.fullscreen:        # make the window fullscreen
            self.showFullScreen()
        else:
            self.resize(2048, 1600)  # set the window size
            self.move(200, 200)  # set the window position

        self.win.clear()         # clear the existing graph

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
        self.basename = os.path.basename(filename)  # get just the filename
        self.dirname = os.path.dirname(filename)
        self.fname, _ = os.path.splitext(filename)
        self.args.filename = filename
        self.data = pltutils.ReadData(self.args)    # load the data
        self.board_prog = self.data.header.__dict__['env_set']['title']

        result = resolve_graph_visibility(self.board_prog, graph_lst, graph_name)
        for name, flag in zip(graph_name, result):
            self.graph_actions[name].setVisible(flag)

        self.cpt_list = self.data.cpt_list
        self.current_data = copy.deepcopy(self.data.data0)   # original PlotData
        # apply the default filter up front (default: 'default_filter.json' -> e.g. LowPass filter & DownSampling)
        self.filter, self.current_data.data = pltutils.apply_default_filters(
            self.current_data.data, default_filter if self.args.smoothing else None, self.cpt_list)

        self.num_plots = self.current_data.num_data
        self.cpt_lines, self.LT_lines, self.PRE_lines = [], [], []

        if self.args.header:
            headerfile = f'{self.fname}_header.xlsx'
            if not os.path.exists(headerfile):
                pltutils.save_header(self.data.header, headerfile)

        self.wl_params = build_wavelet_params(self.args)
        # compute the wavelet transform asynchronously
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
        self.add_shift = 0  # variable holding a numeric value
        self.window_title = f'{self.basename}   {self.data.title}'  # Window Title setting
        self.setWindowTitle(self.window_title)

    def variable_parts(self):
        # Port Selection
        if self.port_selection.layout():
            QWidget().setLayout(self.port_selection.layout())  # remove the existing layout
        if self.num_plots > 1:   # For only 1port -> hide
            checkboxes_layout, self.checkboxes = pltutils.mk_checkbox(
                range(self.num_plots), self.hide_show_plot)
            self.port_selection.setLayout(checkboxes_layout)
        else:
            self.checkboxes = None
        self.port_selection.setVisible(self.num_plots > 1)  # For only 1port -> hide

        # Check points Selection(For time shift)
        if self.time_shift.layout():
            QWidget().setLayout(self.time_shift.layout())  # remove the existing layout
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
        if self.info_window:                # if the Information window is open
            self.info_window.close()    # close the window
            self.info_window = None   # drop the reference
            self.open_info_window()    # open the window

    def open_smoothing_window(self):
        if not self.smoothing_window:
            self.changed_data = copy.deepcopy(self.current_data)
            print(f'{self.cpt_list=}, {len(self.cpt_list)=}')
            self.smoothing_window = pltutils.SignalSmoothingWindow(
                self.plots.plts, self.changed_data, self.cpt_list)
            # connect the Signal (to receive the data)
            self.smoothing_window.execTriggered.connect(self.on_smoothing_finished)
            # drop the reference when the window is closed
            self.smoothing_window.setAttribute(Qt.WA_DeleteOnClose)
            self.smoothing_window.destroyed.connect(
                lambda: setattr(self, "smoothing_window", None))
            self.smoothing_window.show()

    def on_smoothing_finished(self, data):
        print(t('plot.exec_received_data'), f"{data['history']=}")
        self.current_data = copy.deepcopy(data['filtered'])  # update with the received data
        self.history = data['history']  # Get filter history
        self.filter = self.merge_filter_and_history()  # merge

        self.selected_graph = '0:Timeseries'
        self.update_plot()
        # compute the wavelet transform asynchronously
        executor = ProcessPoolExecutor()
        self.future = executor.submit(
            pltutils.do_wavelet_transform,
            self.current_data,
            self.wl_params)

    def open_wavelet_param_window(self):
        if not self.wavelet_param_window:
            self.wavelet_param_window = pltutils.WaveletParamWindow(self.wl_params)
            # connect the Signal (to receive the new parameters)
            self.wavelet_param_window.execTriggered.connect(self.on_wavelet_params_finished)
            # drop the reference when the window is closed
            self.wavelet_param_window.setAttribute(Qt.WA_DeleteOnClose)
            self.wavelet_param_window.destroyed.connect(
                lambda: setattr(self, "wavelet_param_window", None))
            self.wavelet_param_window.show()

    def on_wavelet_params_finished(self, params):
        print(f'[INFO] new {params=}')
        self.wl_params = params
        # compute the wavelet transform asynchronously with the new parameters
        executor = ProcessPoolExecutor()
        self.future = executor.submit(
            pltutils.do_wavelet_transform,
            self.current_data,
            self.wl_params)
        if self.graph_id in wavelet_lst:
            # already looking at a wavelet-family graph -- refresh it now
            # (update_plot() shows a busy cursor while this blocks on the
            # recompute finishing; see its wavelet_lst branch)
            self.update_plot()

    def open_info_window(self):
        """Open a separate window, and drop the reference when it's closed"""
        if self.info_window is None:
            self.info_window = pltutils.TabWindow(
                self.data.header, self.current_data)  # self.data.data0)
            # drop the reference when the window is closed
            self.info_window.setAttribute(Qt.WA_DeleteOnClose)
            self.info_window.destroyed.connect(lambda: setattr(self, "info_window", None))
            self.info_window.show()

    def closeEvent(self, event):
        # close the InfoWindow
        if self.info_window and self.info_window.isVisible():
            self.info_window.close()
        # close the SignalSmoothingWindow
        if self.smoothing_window and self.smoothing_window.isVisible():
            self.smoothing_window.close()
        # close the MainWindow
        event.accept()

    def closeApp(self):
        self.close()

    def open_file_select_dialog(self):
        options = QFileDialog.Options()  # options |= QFileDialog.DontUseNativeDialog
        # open the file selection dialog
        file_path, _ = QFileDialog.getOpenFileName(
            self, "Select .dat File", self.dirname, "DAT Files (*.dat)", options=options)
        if file_path:
            print(t('plot.selected_file', path=file_path))
            self.prepare_data(file_path)
            self.variable_parts()
            self.win.clear()      # clear the existing graph
            self.plots.remove_right_axes()  # remove plts_right
            self.plots = pltutils.InitPlots(
                self.win, self.num_plots)  # label, plots, p_base (placed within win)
            self.update_plot()    # update the plot
            # SignalSmoothingWindow
            if self.smoothing_window:          # if the SignalSmoothingWindow is open
                self.smoothing_window.close()  # close the window
                self.smoothing_window = None   # drop the reference
                self.open_smoothing_window()   # open the window

    def open_image_save_dialog(self):
        # Save an image of self.win (the pyqtgraph graph area only, not the
        # button panel) exactly as it's currently rendered -- when there is
        # more than one port, that already respects the "Select port"
        # checkboxes, since hide_show_plot() shows/hides whole subplot rows
        # in this same widget (see self.plots.show_or_hide()).
        default_name = f'{self.fname}_G{self.graph_id:02}.pdf'
        dialog = QFileDialog(
            self, t('plot.gui.save_image_dialog_title'), default_name,
            "PDF Files (*.pdf);;SVG Files (*.svg);;PNG Files (*.png);;"
            "TIFF Files (*.tif *.tiff);;EPS Files (*.eps)")
        dialog.setAcceptMode(QFileDialog.AcceptSave)
        # Adding the include-Region-Select checkbox requires disabling the native dialog.
        dialog.setOption(QFileDialog.DontUseNativeDialog, True)
        region_checkbox = QCheckBox(t('plot.gui.save_region_select_checkbox'))
        region_checkbox.setToolTip(t('plot.gui.save_region_select_checkbox_tip'))
        region_checkbox.setChecked(False)  # default: do not include
        layout = dialog.layout()
        layout.addWidget(region_checkbox, layout.rowCount(), 0, 1, layout.columnCount())

        if dialog.exec_() != QFileDialog.Accepted:
            return  # do nothing if cancelled
        selected = dialog.selectedFiles()
        if not selected:
            return
        filename = selected[0]
        selected_filter = dialog.selectedNameFilter()
        default_ext = {'PDF': '.pdf', 'SVG': '.svg', 'PNG': '.png',
                       'TIFF': '.tif', 'EPS': '.eps'}
        valid_exts = {'PDF': ('.pdf',), 'SVG': ('.svg',), 'PNG': ('.png',),
                     'TIFF': ('.tif', '.tiff'), 'EPS': ('.eps',)}
        fmt = next(key for key in default_ext if key in selected_filter)
        if not filename.lower().endswith(valid_exts[fmt]):
            filename += default_ext[fmt]
        include_region_select = region_checkbox.isChecked()

        # Temporarily hide the bottom Region Select row (p_base + the "F"
        # button) so it's excluded from the capture -- same hide/stretch-
        # factor mechanism InitPlots.show_or_hide() uses for port rows.
        region_row = self.num_plots + 1
        if not include_region_select:
            self.plots.p_base.hide()
            self.plots.full_range_button.hide()
            self.win.ci.layout.setRowStretchFactor(region_row, 0)
        try:
            self._save_graph_image(fmt, filename)
        except RuntimeError as e:
            QMessageBox.critical(self, t('plot.gui.save_image_dialog_title'), str(e))
        finally:
            if not include_region_select:
                self.plots.p_base.show()
                self.plots.full_range_button.show()
                self.win.ci.layout.setRowStretchFactor(region_row, 1)

    def _save_graph_image(self, fmt, filename):
        if fmt == 'PNG':
            self.win.grab().save(filename, 'PNG')
        elif fmt == 'TIFF':
            self.win.grab().save(filename, 'TIFF')
        elif fmt == 'SVG':
            _save_window_as_svg(self.win, filename)
        elif fmt == 'PDF':
            _save_window_as_pdf(self.win, filename)
        elif fmt == 'EPS':
            _save_window_as_eps(self.win, filename)

    def open_file_write_dialog(self):
        # This used to skip the dialog and write directly to
        # {original filename}_G{graph_id}.xlsx without confirmation
        # (silently overwriting the file if it already existed). Routing
        # this through a QFileDialog save dialog lets both the destination
        # confirmation and the overwrite-existing-file confirmation (a Qt
        # standard feature) work.
        default_name = f'{self.fname}_G{self.graph_id:02}.xlsx'
        is_image = self.graph_id in image_lst  # ImageItem (Scalogram)

        dialog = QFileDialog(self, t('plot.gui.save_graph_dialog_title'), default_name,
                             "Excel Files (*.xlsx)")
        dialog.setAcceptMode(QFileDialog.AcceptSave)
        # Adding the save-CSV-or-not checkbox requires disabling the native dialog.
        dialog.setOption(QFileDialog.DontUseNativeDialog, True)
        csv_checkbox = QCheckBox(t('plot.gui.save_csv_checkbox'))
        if is_image:
            # Scalogram is designed to skip writing the matrix data to an
            # Excel sheet (too heavy) and keep it in CSV only, so disabling
            # CSV would leave the actual data nowhere at all. So CSV is
            # forced on, and the checkbox itself disabled, only for Scalogram.
            csv_checkbox.setChecked(True)
            csv_checkbox.setEnabled(False)
            csv_checkbox.setToolTip(t('plot.gui.save_csv_checkbox_forced_tip'))
        else:
            csv_checkbox.setChecked(False)  # default: do not save
            csv_checkbox.setToolTip(t('plot.gui.save_csv_checkbox_tip'))
        layout = dialog.layout()
        layout.addWidget(csv_checkbox, layout.rowCount(), 0, 1, layout.columnCount())

        if dialog.exec_() != QFileDialog.Accepted:
            return  # do nothing if cancelled
        selected = dialog.selectedFiles()
        if not selected:
            return
        excelfile = selected[0]
        if not excelfile.lower().endswith('.xlsx'):
            excelfile += '.xlsx'
        save_csv = csv_checkbox.isChecked()

        mark_points = self.data.header.time['check_points']
        if self.data.LT_dict is not None and self.data.PRE_dict is not None:
            note_df = pd.Series({**self.data.LT_dict, **self.data.PRE_dict}).T
        else:
            note_df = None

        if is_image:
            self.image_data.to_excel(excelfile, self.filter, mark_points, note_df, save_csv=save_csv)
        else:
            self.plot_data.to_excel(excelfile, self.filter, mark_points, note_df, save_csv=save_csv)

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

    def toggle_full_range(self):
        """Toggle the bottom row's selected range between full range and the
        previously selected range. Whichever is pressed -- the top toolbar
        button or the "F" button to the left of the bottom graph -- both
        buttons' background color (checked state) is synced to region_mgr's
        actual state."""
        is_full = self.region_mgr.toggle_full_range() if hasattr(self, 'region_mgr') else False
        self.full_range_button.setChecked(is_full)
        if hasattr(self, 'plots') and hasattr(self.plots, 'full_range_button'):
            self.plots.full_range_button.setChecked(is_full)

    def hide_show_plot(self):
        if self.args.timeshift1 and len(self.data.cpt_list) > 0:
            self.time_offset = self.data.cpt_list[0]
        if self.time_shift.layout():
            selected_cpt = self.button_group.checkedId()
            self.time_offset = self.data.cpt_list[selected_cpt - 1] if selected_cpt > 0 else 0
        # For Timeseries
        if hasattr(self, 'curves'):
            # tell RegionManager the shift amount
            self.region_mgr.set_x_shift(self.time_offset + self.add_shift)
            for cur, (x, y) in zip(self.curves, self.plot_data.data):
                if len(x) == 0:
                    self.close()
                    return
                else:
                    x_shifted = x - self.time_offset - self.add_shift
                    x_d, y_d = pltutils.decimate_fixed(x_shifted, y)  # decimate
                    cur.setData(x_d, y_d)

            # If the bottom row's overview (region-select) plot were always
            # fixed to port0, it would keep showing even after port0 is
            # hidden via Select Port, which looks wrong -- so it uses the
            # first currently displayed (checked) port instead.
            base_idx = 0
            if self.checkboxes:
                checked = [num for num, cb in self.checkboxes if cb.isChecked()]
                if checked:
                    base_idx = checked[0]
            x0 = self.plot_data.data[base_idx][0] - self.time_offset - self.add_shift
            x_d0, y_d0 = pltutils.decimate_fixed(x0, self.plot_data.data[base_idx][1])
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
                        x_d, y_d = pltutils.decimate_fixed(x_shifted, y)  # decimate
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
        self.plot_vertical_lines()  # draw vertical lines
        self.show_filter_label()    # Filter label

    def plot_vertical_lines(self):
        def update_lines(check_box, line_list_name, data_source, plot_func):
            # update the lines if the checkbox is checked, otherwise just remove them
            lines = getattr(self, line_list_name, [])
            for (p, l) in lines:
                p.removeItem(l)
            setattr(self, line_list_name, [])

            if check_box and check_box.isChecked():
                all_plots = self.plots.plts + [self.plots.p_base]
                new_lines = plot_func(all_plots, data_source)
                setattr(self, line_list_name, new_lines)

        print(t('plot.selected_graph', graph=self.selected_graph))
        # hide the vertical lines when the graph is 'PowerSpectra'
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
        # LT display
        lt_dict = getattr(self.data, 'LT_dict', None)
        if self.LT_check and isinstance(lt_dict, dict) and lt_dict:
            key, val = next(iter(lt_dict.items()))
            label_parts.append(f"{key}={val}(sec)")
        # PRE display
        pre_dict = getattr(self.data, 'PRE_dict', None)
        if self.PRE_check and isinstance(pre_dict, dict):
            pre_parts = [f"{k}={v}" for k, v in pre_dict.items() if not np.isnan(v)]
            if pre_parts:
                label_parts.append(', '.join(pre_parts))
        # update the display
        label2_text = '; '.join(label_parts)
        self.label2.setText(label2_text)
        self.label2.setToolTip(t('plot.gui.label2_tip') if label2_text else '')

    def show_filter_label(self):
        if all(not v for v in self.filter.values()):  # if every value is []
            self.label3.setText('')
            self.label3.setToolTip('')
        else:
            self.label3.setText(f'{toStr(self.filter)}')
            self.label3.setToolTip(t('plot.gui.filters_tip'))

    def merge_filter_and_history(self):
        return merge_filter_and_history(self.filter, self.history)

    def update_plot(self):
        # draw according to the graph type
        self.graph_id = int(re.match(r'^(\d+)\:', self.selected_graph).group(1))
        debug_print(self.args, f'[Debug]{self.graph_id=}, {self.selected_graph=}')
        # cache the future's result
        if self.graph_id in wavelet_lst:
            # self.future.result() blocks until the (possibly still
            # running) wavelet transform finishes -- show a busy cursor
            # rather than freeze the GUI with no feedback, whether this is
            # the initial post-load computation or a fresh one kicked off
            # by on_wavelet_params_finished().
            QApplication.setOverrideCursor(Qt.WaitCursor)
            try:
                self.wv_data, self.energy, self.power, self.max_power_freq, self.max_power_bpm = self.future.result()
            finally:
                QApplication.restoreOverrideCursor()

        # Rather than reusing the PlotItem/ViewBox, it is recreated every
        # time, the same as in open_file_select_dialog(). Reusing a PlotItem
        # in the past (especially when the curve/colorbar/image changes, as
        # with PowerSpectra/Scalogram) reproduced a
        # "wrapped C/C++ object ... has been deleted" crash (caused by
        # pyqtgraph/Qt object-lifetime management; recreating it each time avoids this).
        self.win.clear()
        self.plots.remove_right_axes()
        self.plots = pltutils.InitPlots(self.win, self.num_plots)
        # Recreating the graph also creates a new region_mgr, resetting the
        # full-range display state, so the button's appearance (the
        # checked-state background color) is reset to match.
        self.full_range_button.setChecked(False)
        # InitPlots() creates a new Full Range button (the "F" button to the
        # left of the bottom graph) every time, so it must be reconnected each time.
        self.plots.full_range_button.clicked.connect(self.toggle_full_range)
        if self.graph_id in image_lst:    # ImageItem (Scalogram)
            # Clear leftovers from a previous PlotItem-family graph (used by hide_show_plot()'s hasattr checks).
            for stale in ('curves', 'p_base_plot', 'derivative_curves', 'peaks', 'valleys',
                          'plot_data', 'mavg_curves'):
                if hasattr(self, stale):
                    delattr(self, stale)
            self.derivatives.setVisible(False)  # Derivatives (1st/2nd) are irrelevant for ImageItem-family graphs
            self.peaks_check.setVisible(False)  # Peak is also irrelevant for ImageItem-family graphs
            self.image_data = graph_func[self.graph_id](self)
            self.plots.set_title(self.image_data.title)
            self.img, self.colorbar, self.region_mgr, self.cross_hair = pltutils.plot_scalogram(
                self.plots, self.image_data)
        else:                        # PlotItem
            # Clear leftovers from a previous ImageItem-family graph (used by hide_show_plot()'s hasattr checks).
            for stale in ('img', 'colorbar', 'image_data'):
                if hasattr(self, stale):
                    delattr(self, stale)
            self.derivatives.setVisible(True)
            self.peaks_check.setVisible(True)
            self.plot_data = graph_func[self.graph_id](self)  # passing self lets lambda(obj) be used
            self.plots.set_title(self.plot_data.title)
            self.curves, self.p_base_plot, self.region_mgr, self.cross_hair = pltutils.plot_timeseries(
                self.plots, self.plot_data)
            # Moving Average curves
            if hasattr(self, 'mavg_curves'):
                del self.mavg_curves
            # Derivatives (calc_derivatives() & plot_right_axis() return a list)
            self.derivative_data = pltutils.calc_derivatives(self.plot_data)
            self.derivative_curves = pltutils.plot_right_axis(
                self.plots.plts_right, self.derivative_data)
            # Draw Peaks & Valleys (non-ImageItem graphs only)
            self.peaks_data, self.valleys_data = pltutils.calc_peaks_and_valleys(self.plot_data)
            self.peaks = pltutils.plot_peaks(self.plots, self.peaks_data, 'circle')
            self.valleys = pltutils.plot_peaks(self.plots, self.valleys_data, 'square')
            visible = self.peaks_check.isChecked()
            for curve in self.peaks + self.valleys:
                curve.setVisible(visible)
        # PowerSpectra (FFT) has Freq. on the X axis rather than Time, so
        # Time-based operation UI such as Mark/Select Mark/Shift time is irrelevant.
        has_time_axis = self.graph_id not in freq_lst
        self.mark_check.setVisible(has_time_axis and len(self.data.cpt_list) > 0)
        self.time_shift.setVisible(has_time_axis and len(self.data.cpt_list) > 0)
        self.shift_layout.setVisible(has_time_axis)
        self.hide_show_plot()
        self.title_label.setText(self.window_title + "\n" + self.plots.title)
        if self.args.pdffile:
            append_window_to_pdf(self, output_pdf)

    def select_graph(self):
        # get the selected action's text
        selected_action = self.sender()
        self.selected_graph = selected_action.text()
        self.update_plot()

    def update_shift_value(self):
        # get the text box's value and convert it to a number; 0 if empty
        text = self.shift_input.text()
        self.add_shift = int(text) if text else 0
        if self.add_shift > self.data.data_t[0][-1]:
            self.add_shift = self.data.data_t[0][-1]
        print(t('plot.current_shift_value', shift=self.add_shift))
        self.hide_show_plot()


def append_window_to_pdf(window, existing_pdf_path, dpi=300):
    # Deferred: only needed for PDF export, and PyPDF2 has also been
    # observed to hang for a long time on import on some Windows lab
    # machines (see the scipy.signal comment in main()) -- importing it
    # only here keeps startup and non-PDF exports unaffected.
    with _timed_import('PyPDF2', 5):
        from PyPDF2 import PdfMerger

    # write out to a temporary PDF
    temp_pdf = existing_pdf_path + ".temp.pdf"
    _save_window_as_pdf(window, temp_pdf, dpi)

    # merge the existing + new PDF into a new temporary file
    merged_pdf = existing_pdf_path + ".merged.pdf"
    merger = PdfMerger()
    if os.path.exists(existing_pdf_path):
        merger.append(existing_pdf_path)
    merger.append(temp_pdf)
    merger.write(merged_pdf)
    merger.close()

    # overwrite
    os.replace(merged_pdf, existing_pdf_path)
    os.remove(temp_pdf)


def _save_window_as_pdf(window, filename, dpi=300):
    # grab() (not render(pixmap)) -- pyqtgraph's GraphicsView overrides
    # render() with an incompatible signature, so this must also work when
    # `window` is self.win (the graph area) rather than the whole MainWindow.
    pixmap = window.grab()

    pdf_writer = QPdfWriter(filename)
    size = window.size()
    pdf_writer.setPageSizeMM(QSizeF(size.width(), size.height()))
    pdf_writer.setResolution(dpi)

    painter = QPainter(pdf_writer)
    image = pixmap.toImage()
    rect = painter.viewport()
    scaled_size = image.size()
    scaled_size.scale(rect.size(), 1)  # preserve aspect ratio
    painter.setViewport(rect.x(), rect.y(), scaled_size.width(), scaled_size.height())
    painter.setWindow(image.rect())
    painter.drawImage(0, 0, image)
    painter.end()


def _save_window_as_svg(window, filename):
    # Wraps the same window.grab() raster capture used for PNG/PDF in an
    # SVG container, rather than a true vector scene render. pyqtgraph's
    # QGraphicsView.render(painter) path was tried and rejected during
    # development: it draws scene content beyond the visible viewport and
    # a normally-hidden crosshair item that never appears on screen, so
    # it isn't WYSIWYG. This keeps every exported format pixel-identical
    # to what's actually displayed.
    pixmap = window.grab()
    generator = QSvgGenerator()
    generator.setFileName(filename)
    size = window.size()
    generator.setSize(size)
    generator.setViewBox(QRect(0, 0, size.width(), size.height()))
    painter = QPainter(generator)
    painter.drawPixmap(0, 0, pixmap)
    painter.end()


def _save_window_as_eps(window, filename):
    # Qt5 has no built-in PostScript writer, so EPS is produced by
    # rendering to a temporary PDF (the same path used for the PDF
    # option) and converting it with poppler's `pdftops -eps`.
    pdftops = shutil.which('pdftops')
    if pdftops is None:
        raise RuntimeError(t('plot.save_image_eps_needs_pdftops'))
    fd, tmp_pdf = tempfile.mkstemp(suffix='.pdf')
    os.close(fd)
    try:
        _save_window_as_pdf(window, tmp_pdf)
        subprocess.run([pdftops, '-eps', tmp_pdf, filename], check=True)
    finally:
        os.remove(tmp_pdf)


def find_data_directories(base='.'):
    # Each board's .ini sets its own dir_name (data, data_LIS3DH,
    # data_SHT35, ...), so recordings from different board types land in
    # sibling directories, not all under a single 'data/'. Glob for all of
    # them so "the newest recording" isn't scoped to just one board type.
    return sorted(
        os.path.join(base, name) for name in os.listdir(base)
        if (name == 'data' or name.startswith('data_'))
        and os.path.isdir(os.path.join(base, name)))


def get_newest_file_name(folder_paths):
    if isinstance(folder_paths, str):
        folder_paths = [folder_paths]
    # filter to only .dat files, across every given folder
    dat_files = [
        os.path.join(folder_path, f)
        for folder_path in folder_paths
        for f in os.listdir(folder_path) if f.endswith('.dat')]
    # return None if no .dat files exist
    if not dat_files:
        return None
    # select the newest .dat file
    return max(dat_files, key=os.path.getmtime)


def get_files_from_directory(folder):
    dat_files = []
    for root, _, files in os.walk(folder):
        for f in files:
            if f.endswith('.dat'):
                dat_files.append(os.path.join(root, f))
    return sorted(dat_files)


# create the directory if it doesn't exist
default_dir = './data/'
os.makedirs(default_dir, exist_ok=True)

default_filter_file = 'default_filter.json'
with open(default_filter_file, "r", encoding="utf-8") as f:
    default_filter = json.load(f)

default_filename = get_newest_file_name(find_data_directories())
default_wpconfig = 'default_wavelet_params.json'

# The PDF output destination MainWindow.update_plot() refers to when
# args.pdffile is set. A local variable in main() would raise NameError
# (update_plot() can only see module globals), so it's decided once at the
# module level (accumulating into one file per run).
output_pdf = f"Figures_{datetime.now().strftime('%Y%m%d_%H%M%S')}.pdf"

# === Centralize parameter definitions (type, default, description) ===
# 'help' is an i18n catalog key. Only entries with dynamic values to embed
# have 'help_kwargs' (this dict itself is evaluated before --lang is
# resolved, so the actual translation happens inside parse_args()).
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
    # define the common parameters
    for key, meta in DEFAULTS.items():
        flags = [meta.get("short", ""), f"--{key}"]
        flags = [f for f in flags if f]  # exclude empty elements

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

    # option for config.json (independent of the others)
    parser.add_argument('--config', type=str, help=t('plot.help.config'))
    parser.add_argument('-lang',
                        '--lang',
                        choices=i18n.SUPPORTED_LANGS,
                        default=i18n.get_language(),
                        help=t('help.lang',
                               langs='/'.join(i18n.SUPPORTED_LANGS)))

    args = parser.parse_args()
    i18n.set_language(args.lang)

    # load the config file if one was specified
    if args.config:
        try:
            with open(args.config, 'r') as f:
                config_data = json.load(f)
                for key, value in config_data.items():
                    if hasattr(args, key):
                        expected_type = DEFAULTS[key]["type"]
                        # handle values like numbers stored as strings
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

    # override with CLI arguments if given
    if args.wlrange:
        params.range = args.wlrange
    if args.wlomega0:
        params.omega0 = args.wlomega0

    return params


def main():
    args = parse_args()

    # Deferred until after argparse has had a chance to handle -h/--help
    # (which exits right above, via parse_args()) and exit fast:
    # mylib.plot_utils pulls in scipy.signal, a compiled extension that has
    # been observed to take a very long time to import on some Windows lab
    # machines (antivirus real-time scanning, slow network-mounted profile
    # dirs) -- confirmed via a student report of `plot.py -h` hanging on
    # exactly this import. Importing it here instead of at module load time
    # means --help (and any other argparse error/exit) stays fast regardless.
    global pltutils, WaveletParams
    with _timed_import('mylib.plot_utils (scipy.signal)', 4):
        import mylib.plot_utils as pltutils
        from mylib.plot_utils import WaveletParams

    # argv[0] becomes the X11 WM_CLASS (verified via xprop); Qt's
    # setDesktopFileName() only affects the Wayland app-id, so both are
    # needed to match sensor-bridge-plot.desktop's StartupWMClass on either
    # session type and get the dock/taskbar icon to show.
    app = QApplication(['sensor-bridge-plot'] + sys.argv[1:])
    app.setDesktopFileName('sensor-bridge-plot')
    app.setWindowIcon(QIcon('icon.png'))
    app.setApplicationName("sensor-bridge")

    # Excel output (headless): calls MainWindow.open_file_write_dialog(),
    # the same as the GUI's "Save Data" button (Ctrl+S). The window is not shown.
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
            # -d wasn't pointed at a specific directory -> search every
            # data*/ directory (data, data_LIS3DH, data_SHT35, ...) for
            # the newest recording, not just one board type's; -d given
            # explicitly still scopes the search to that directory alone.
            search_dirs = find_data_directories() if args.dirname == default_dir else [args.dirname]
            candidates = [f for d in search_dirs for f in get_files_from_directory(d)]
            if not candidates:
                print(t('plot.no_dat_in_data_folder'))
                sys.exit(1)
            # files[-1] would be the alphabetically-last name, not the
            # actually most-recently-modified file (filenames don't always
            # sort chronologically, e.g. multi-board runs insert a port
            # suffix into the name) -- pick by mtime instead, consistent
            # with get_newest_file_name() above.
            args.filename = max(candidates, key=os.path.getmtime)
        window = MainWindow(args.filename, args)
        window.show()
        if args.background:
            QTimer.singleShot(1000, app.quit)

    sys.exit(app.exec_())


if __name__ == '__main__':
    main()
