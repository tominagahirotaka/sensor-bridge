"""Dialog widgets driven by the filter/plotting layers: SignalSmoothingWindow
(the interactive per-series filter-pipeline editor), WaveletParamWindow
(editing the continuous-wavelet-transform parameters without relaunching
plot.py), and TabWindow (the tabbed header/metadata +
sampling-interval-histogram viewer)."""

import copy
import json

import pyqtgraph as pg
from PyQt5.QtCore import pyqtSignal
from PyQt5.QtWidgets import (QCheckBox, QDialog, QDoubleSpinBox, QFileDialog,
                             QGroupBox, QHBoxLayout, QLabel, QMessageBox,
                             QPushButton, QSpinBox, QTabWidget, QTableWidget,
                             QTableWidgetItem, QVBoxLayout, QWidget)

from mylib.i18n import t as tr
from mylib.plot_utils.common import COLORS, bg_colors, init_pg, set_bg_color
from mylib.plot_utils.filters import SignalFilter
from mylib.plot_utils.plotting import plot_timeinterval_histogram
from mylib.plot_utils.wavelet import WaveletParams


class SignalSmoothingWindow(QWidget):
    execTriggered = pyqtSignal(object)  # Signal used to send the data

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
        # for the All tab
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
        # main layout
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

        # create the tab widget
        idxs = list(range(len(self.data.labels)))
        self.tab_widget = QTabWidget()

        # create the All tab
        tab = QWidget()
        self.tab_widget.addTab(tab, f"All")
        tab_layout = QVBoxLayout()            # layout within the tab
        self.historyAll = []
        # history_label with Undo setting
        history_label_layout = self.create_history_group(idxs)
        # filter settings
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

        # create a tab for each corresponding data series
        for idx, label in enumerate(self.data.labels):
            name, unit = next(iter(label.values()))
            tab = QWidget()
            self.tab_widget.addTab(tab, f"{name}")
            tab_layout = QVBoxLayout()            # layout within the tab

            # Label setting
            self.history[idx] = []
            # history_label with Undo setting
            history_label_layout = self.create_history_group(idx)

            # filter settings
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

        # set the new sampling frequency
        param_layout.addWidget(QLabel("New Fs (Hz):"))

        ds_freq = QSpinBox()
        current_fs = int(1 / (t[1] - t[0]))  # current sampling frequency
        ds_freq.setRange(1, current_fs)
        ds_freq.setValue(current_fs // 2)  # default value is half the current Fs
        param_layout.addWidget(ds_freq)

        # show the current sampling frequency
        current_fs_label = QLabel(f"Current Fs: {current_fs} Hz")
        param_layout.addWidget(current_fs_label)

        # anti-aliasing filter checkbox
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
        tr_reset_t0.setChecked(True)  # on by default
        layout.addWidget(tr_reset_t0)

        if len(self.cpt_list) > 0:
            # --- Mark selection ---
            cpt_layout = QHBoxLayout()
            cpt_layout.addWidget(QLabel("Mark #"))

            cpt_idx = QSpinBox()
            cpt_idx.setRange(0, len(self.cpt_list) - 1)
            cpt_layout.addWidget(cpt_idx)

            cpt_val_label = QLabel(f"= {self.cpt_list[0]:.2f} s")
            cpt_layout.addWidget(cpt_val_label)

            # update the displayed time whenever the SpinBox changes
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
        t_max_val = self.original_data.data[idxs[0]][0][-1]  # the last element of the t array

        tr_max.setValue(t_max_val)
        tr_min.setRange(0, t_max_val)
        tr_max.setRange(0, t_max_val)
        tr_min.setValue(0)
        tr_max.setValue(t_max_val)  # initial value is the data's max time
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
                    self.ds_freq_all.setValue(new_fs // 2)  # default value is half the current Fs
                else:
                    self.current_fs_label[idxs[0]].setText(f"Current Fs: {new_fs} Hz")
                    self.ds_freq[idxs[0]].setValue(new_fs // 2)  # default value is half the current Fs
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
            # Only the SignalFilter class; no function/dict is needed.
            sf = SignalFilter(self.original_data.data[idx])
            self.data.data[idx] = sf.apply(self.history[idx]).data
            # self.data.data[idx] = cont_calc_filters(self.original_data.data[idx], self.history[idx])
            txt = tr('pu.history_prefix') + \
                '+'.join(set_bg_color(f'{method}{param}') for method, param in self.history[idx])
            self.history_label[idx].setText(txt)
            # update the plot
            self.update_plot(idx)

        # also update the All tab's history label
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
            self.apply_history(idx)  # apply_history also reverts to the original data when the history becomes empty

        # after the loop, bring the All tab's label up to date
        if is_all and 'all' in self.history_label:
            # decide based on whether idxs[0]'s history is still non-empty
            if len(self.history[idxs[0]]) > 0:
                txt = tr('pu.history_prefix') + \
                    '+'.join(set_bg_color(f'{m}{p}') for m, p in self.history[idxs[0]])
                self.history_label['all'].setText(txt)
            else:
                self.history_label['all'].setText(tr('pu.history_prefix'))
                # also hide the filtered_plot corresponding to the All tab
                for idx in idxs:
                    self.filtered_plot[idx].hide()

    def apply_history(self, idxs):
        idxs = [idxs] if isinstance(idxs, int) else idxs
        for idx in idxs:
            if len(self.history[idx]) == 0:
                # If self.data stayed at the last filtered result while the
                # history is empty, that's a contradiction ("history=[] but
                # data is still filtered") -- reproducible right after Undo
                # removes the last entry, or after Load with an empty
                # history. Revert to the original data and keep the display consistent.
                self.data.data[idx] = self.original_data.data[idx]
                self.history_label[idx].setText(tr('pu.history_prefix'))
                if self.filtered_plot[idx]:
                    self.filtered_plot[idx].hide()
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
        # Regression fix: this used to always write a hardcoded
        # "history.json" in the current directory with no dialog at all
        # -- asymmetric with load_parameters()'s file picker, and silently
        # overwrote any existing file of that name with no confirmation.
        filename, _ = QFileDialog.getSaveFileName(
            self, "Save Parameters", "history.json", "JSON Files (*.json)")
        if not filename:
            return  # user cancelled
        with open(filename, "w", encoding="utf-8") as f:
            json.dump(self.history, f, ensure_ascii=False, separators=(",", ":"))
        print(f'Save {self.history=}')

    def load_parameters(self):
        filename, _ = QFileDialog.getOpenFileName(
            self, "Load Parameters", "", "JSON Files (*.json)")
        if not filename:
            return  # user cancelled -- getOpenFileName returns '' here,
            # which used to be passed straight to open() and crash with
            # an uncaught FileNotFoundError
        try:
            with open(filename, "r", encoding="utf-8") as f:
                dt = json.load(f)
            loaded = {int(k): v for k, v in dt.items()}
        except (OSError, ValueError) as e:
            QMessageBox.warning(self, "Load Parameters", f"Could not load {filename}:\n{e}")
            return

        # A history file saved from a recording with a different channel
        # count would otherwise crash apply_history() below with an
        # IndexError on the first out-of-range channel; drop those
        # entries instead and tell the user, rather than lose the ones
        # that do apply.
        valid_idxs = set(range(len(self.data.data)))
        skipped = sorted(set(loaded) - valid_idxs)
        self.history = {idx: v for idx, v in loaded.items() if idx in valid_idxs}
        if skipped:
            QMessageBox.warning(
                self, "Load Parameters",
                f"This file has entries for channel(s) {skipped} which don't "
                f"exist in the current recording ({len(valid_idxs)} channel(s)); "
                "those were skipped.")

        print(f'Load {self.history=}')
        for idx in self.history.keys():
            self.apply_history(idx)


class WaveletParamWindow(QWidget):
    """Small editor for the continuous-wavelet-transform parameters
    (frequency range + omega0), so they can be adjusted while a
    recording is open instead of only via plot.py's --wlrange/--wlomega0/
    --wpconfig startup flags. Deliberately does *not* recompute on every
    spin-box change -- the wavelet transform is slow -- only when Apply
    is pressed, matching SignalSmoothingWindow's Exec-button pattern."""
    execTriggered = pyqtSignal(object)  # emits a new WaveletParams

    def __init__(self, params: WaveletParams):
        super().__init__()
        self.setWindowTitle(tr('pu.wavelet_param_window_title'))

        layout = QVBoxLayout()

        button_layout = QHBoxLayout()
        apply_button = QPushButton(tr('pu.btn_apply'))
        load_button = QPushButton(tr('pu.btn_load'))
        save_button = QPushButton(tr('pu.btn_save'))
        apply_button.clicked.connect(self.on_apply)
        load_button.clicked.connect(self.load_parameters)
        save_button.clicked.connect(self.save_parameters)
        button_layout.addWidget(apply_button)
        button_layout.addWidget(load_button)
        button_layout.addWidget(save_button)
        layout.addLayout(button_layout)

        range_group = QGroupBox(tr('pu.wavelet_range_group'))
        range_layout = QHBoxLayout()
        range_layout.addWidget(QLabel(tr('pu.wavelet_range_min')))
        self.range_min = QDoubleSpinBox()
        self.range_min.setDecimals(4)
        self.range_min.setRange(0.0001, 1e6)
        range_layout.addWidget(self.range_min)
        range_layout.addWidget(QLabel(tr('pu.wavelet_range_max')))
        self.range_max = QDoubleSpinBox()
        self.range_max.setDecimals(4)
        self.range_max.setRange(0.0001, 1e6)
        range_layout.addWidget(self.range_max)
        range_layout.addWidget(QLabel(tr('pu.wavelet_range_step')))
        self.range_step = QDoubleSpinBox()
        self.range_step.setDecimals(4)
        self.range_step.setRange(0.0001, 1e6)
        range_layout.addWidget(self.range_step)
        range_group.setLayout(range_layout)
        layout.addWidget(range_group)

        omega0_group = QGroupBox(tr('pu.wavelet_omega0_group'))
        omega0_layout = QHBoxLayout()
        self.omega0 = QDoubleSpinBox()
        self.omega0.setDecimals(4)
        self.omega0.setRange(0.0001, 1e6)
        omega0_layout.addWidget(self.omega0)
        omega0_group.setLayout(omega0_layout)
        layout.addWidget(omega0_group)

        self.setLayout(layout)
        self.set_params(params)

    def set_params(self, params: WaveletParams):
        self.range_min.setValue(params.range[0])
        self.range_max.setValue(params.range[1])
        self.range_step.setValue(params.range[2])
        self.omega0.setValue(params.omega0)

    def current_params(self):
        """Raises ValueError (via WaveletParams's own validation) if the
        current spin-box values don't form a valid range/omega0."""
        return WaveletParams(
            range=[self.range_min.value(), self.range_max.value(), self.range_step.value()],
            omega0=self.omega0.value())

    def on_apply(self):
        try:
            params = self.current_params()
        except ValueError as e:
            QMessageBox.warning(self, tr('pu.wavelet_param_window_title'), str(e))
            return
        self.execTriggered.emit(params)

    def save_parameters(self):
        try:
            params = self.current_params()
        except ValueError as e:
            QMessageBox.warning(self, tr('pu.wavelet_param_window_title'), str(e))
            return
        filename, _ = QFileDialog.getSaveFileName(
            self, tr('pu.btn_save'), 'wavelet_params.json', "JSON Files (*.json)")
        if not filename:
            return  # user cancelled
        params.to_json(filename)

    def load_parameters(self):
        filename, _ = QFileDialog.getOpenFileName(
            self, tr('pu.btn_load'), '', "JSON Files (*.json)")
        if not filename:
            return  # user cancelled
        try:
            params = WaveletParams.from_json(filename)
        except (OSError, ValueError, TypeError) as e:
            QMessageBox.warning(self, tr('pu.wavelet_param_window_title'),
                                f"Could not load {filename}:\n{e}")
            return
        self.set_params(params)


# The LIS3DH (accelerometer) register codes are not meaningful on their own,
# so map them to human-readable values for display in the Header Viewer.
# odr/fs are used by LIS3DH.ini; odr1/odr2/fs1/fs2 are the key names used by
# DPG_X95840W_LIS3DHx2.ini, which carries two LIS3DHs (both are the same
# LIS3DH register values).
_LIS3DH_ODR_LABELS = {
    '1': '1Hz', '2': '10Hz', '3': '25Hz', '4': '50Hz', '5': '100Hz',
    '6': '200Hz', '7': '400Hz', '8': '1.6kHz(LP only)', '9': '1.344kHz/5.376kHz(LP)',
}
_LIS3DH_FS_LABELS = {'0': '±2g', '1': '±4g', '2': '±8g', '3': '±16g'}

_LIS3DH_KEY_LABELS = {
    'odr': 'Output Data Rate', 'odr1': 'Output Data Rate', 'odr2': 'Output Data Rate',
    'fs': 'Full Scale', 'fs1': 'Full Scale', 'fs2': 'Full Scale',
}


def _describe_env_set_key(key):
    """For odr/fs-family keys, append what they're short for. Otherwise, just str(key)."""
    text = str(key)
    if text in _LIS3DH_KEY_LABELS:
        return f'{text} = {_LIS3DH_KEY_LABELS[text]}'
    return text


def _describe_env_set_value(key, value):
    """For odr/fs-family keys, append a human-readable description in
    parentheses next to the register code. Otherwise, just str(value)."""
    text = str(value)
    if key in ('odr', 'odr1', 'odr2') and text in _LIS3DH_ODR_LABELS:
        return f'{text} ({_LIS3DH_ODR_LABELS[text]})'
    if key in ('fs', 'fs1', 'fs2') and text in _LIS3DH_FS_LABELS:
        return f'{text} ({_LIS3DH_FS_LABELS[text]})'
    return text


class TabWindow(QDialog):
    """Separate window displaying the tab widget"""

    def __init__(self, header, data0):
        super().__init__()
        self.setWindowTitle("Header Viewer - Tabs")
        self.resize(800, 900)
        # main layout
        self.layout = QVBoxLayout(self)
        # tab widget
        self.tab_widget = QTabWidget()
        self.layout.addWidget(self.tab_widget)
        # load the header data
        self.header = header
        self.load_header_data()
        # Timeinterval Histogram
        self.time, _ = data0.data[0]
        _, win = init_pg('')
        plt = plot_timeinterval_histogram(win, self.time)
        self.tab_widget.addTab(win, 'timeinterval histogram')

    def load_header_data(self):
        """Read self.header's data and create the tabs"""
        current_index = -1
        for idx, (sheet, dic) in enumerate(self.header.__dict__.items()):
            if sheet == 'subject':
                current_index = idx
            # add the tab
            table_widget = QTableWidget()
            self.tab_widget.addTab(table_widget, sheet)

            # display the data in the table
            if sheet == "machine" and not isinstance(dic, dict):
                table_widget.setRowCount(1)
                table_widget.setColumnCount(1)
                table_widget.setItem(0, 0, QTableWidgetItem(str(dic)))
            else:
                self.display_dict_data(dic, table_widget)

        if current_index != -1:
            self.tab_widget.setCurrentIndex(current_index)

    def display_dict_data(self, dic, table_widget):
        """Display dict-type data in the table"""
        rows = len(dic)
        table_widget.setRowCount(rows)
        table_widget.setColumnCount(2)  # 2 columns: key and value

        for row_idx, (key, lst) in enumerate(dic.items()):
            table_widget.setItem(row_idx, 0, QTableWidgetItem(_describe_env_set_key(key)))  # e.g. odr -> 'odr = Output Data Rate'

            # check whether lst is a list
            if isinstance(lst, list):
                value = ", ".join(map(str, lst))  # if it's a list, join and display it
            else:
                value = _describe_env_set_value(key, lst)  # e.g. odr='7' -> '7 (400Hz)'
            table_widget.setItem(row_idx, 1, QTableWidgetItem(value))

#
# conversion-related functions
#
#
