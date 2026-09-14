"""Dialog widgets driven by the filter/plotting layers: SignalSmoothingWindow
(the interactive per-series filter-pipeline editor) and TabWindow (the
tabbed header/metadata + sampling-interval-histogram viewer)."""

import copy
import json

import pyqtgraph as pg
from PyQt5.QtCore import pyqtSignal
from PyQt5.QtWidgets import (QCheckBox, QDialog, QDoubleSpinBox, QFileDialog,
                             QGroupBox, QHBoxLayout, QLabel, QPushButton,
                             QSpinBox, QTabWidget, QTableWidget,
                             QTableWidgetItem, QVBoxLayout, QWidget)

from mylib.i18n import t as tr
from mylib.plot_utils.common import COLORS, bg_colors, init_pg, set_bg_color
from mylib.plot_utils.filters import SignalFilter
from mylib.plot_utils.plotting import plot_timeinterval_histogram


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
                self.apply_history(idx)
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

    def apply_history(self, idxs):
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
            self.apply_history(idx)


# LIS3DH(加速度センサー)のRegister Codeそのままでは意味が分からないため、Header Viewerでの
# 表示用に人が読める値を対応付ける。odr/fs はLIS3DH.ini、odr1/odr2/fs1/fs2は2台のLIS3DHを
# 積んだDPG_X95840W_LIS3DHx2.iniが使うKey名(どちらも同じLIS3DHのRegister値)。
_LIS3DH_ODR_LABELS = {
    '1': '1Hz', '2': '10Hz', '3': '25Hz', '4': '50Hz', '5': '100Hz',
    '6': '200Hz', '7': '400Hz', '8': '1.6kHz(LP only)', '9': '1.344kHz/5.376kHz(LP)',
}
_LIS3DH_FS_LABELS = {'0': '±2g', '1': '±4g', '2': '±8g', '3': '±16g'}


def _describe_env_set_value(key, value):
    """odr/fs系のKeyはRegister Codeの横に人が読める説明を括弧書きで加える。それ以外はstr(value)のまま。"""
    text = str(value)
    if key in ('odr', 'odr1', 'odr2') and text in _LIS3DH_ODR_LABELS:
        return f'{text} ({_LIS3DH_ODR_LABELS[text]})'
    if key in ('fs', 'fs1', 'fs2') and text in _LIS3DH_FS_LABELS:
        return f'{text} ({_LIS3DH_FS_LABELS[text]})'
    return text


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
                value = _describe_env_set_value(key, lst)  # 例: odr='7' -> '7 (400Hz)'
            table_widget.setItem(row_idx, 1, QTableWidgetItem(value))

#
# 変換系関数
#
#
