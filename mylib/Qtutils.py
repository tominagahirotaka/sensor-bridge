#!/usr/bin/env python
"""Qt widget-factory helpers used by mylib/window.py and board .ini [code]
sections, plus FigureQtPG: the pyqtgraph-based realtime plot widget behind
get.py's live view."""

import re
import sys
from collections import deque

import numpy as np
import pyqtgraph as pg
from PyQt5.QtCore import QDate, Qt
from PyQt5.QtWidgets import (QAction, QCalendarWidget, QComboBox, QDialog,
                             QGridLayout, QHBoxLayout, QLabel, QLCDNumber,
                             QPushButton, QSizePolicy, QSpinBox, QVBoxLayout,
                             QWidget)

import mylib.utils as utils
from mylib.debug_utils import debug_print


def setQLabel(str, style=None, align=None):
    text = QLabel(str)
    if style is not None:
        text.setStyleSheet(style)
    if align is not None:
        text.setAlignment(align)
    return text


def setQPushButton(str, func, self=None, sizepolicy=None, move=None):
    if self is not None:
        btn = QPushButton(str, self)
    else:
        btn = QPushButton(str)
    if sizepolicy is not None:
        btn.setSizePolicy(sizepolicy[0], sizepolicy[1])
    if move is not None:
        btn.move(move[0], move[1])
    btn.clicked.connect(func)
    return btn


def setQLCDNumber(self, style=None, digitcount=None):
    lcd = QLCDNumber(self)
    if digitcount is not None:
        lcd.setDigitCount(digitcount)     # 表示桁数を7に変更(default 5?桁)
    if style is not None:
        lcd.setSegmentStyle(eval('QLCDNumber.' + style))
    return lcd


def setQComboBox(self, items, data=None):
    """items: 表示Textのlist。data: 各項目に紐づける実際の値のlist(省略時はTextがそのまま値になる、
    従来通りの挙動)。例: setQComboBox(self, ['1Hz', '10Hz'], data=['1', '2'])とすると、
    表示は'1Hz'/'10Hz'のまま、選択結果(setQDialog経由)は'1'/'2'になる。"""
    cbox = QComboBox(self)
    if data is not None:
        for text, value in zip(items, data):
            cbox.addItem(text, value)
    else:
        cbox.addItems(items)
    return cbox


def setQAction(self, name, func, Icon=None):
    action = QAction(Icon, '&' + name, self) if Icon is not None else QAction('&' + name, self)
    # nameに含まれる大文字1文字ごとにCtrl+<文字>のShortcutを割り当てる慣習
    # （例: "MArk"->Ctrl+M と Ctrl+A の両方でこのActionを実行できる）。
    # 日本語等、大文字を含まないnameの場合はShortcutを割り当てない（Menu自体は使える）。
    modifier = 'Meta+' if sys.platform == 'darwin' else 'Ctrl+'
    shortcuts = [modifier + letter for letter in re.findall('[A-Z]', name)]
    if shortcuts:
        action.setShortcuts(shortcuts)
    action.setStatusTip(name)
    action.triggered.connect(func)
    return action


def setQSpinBox(self, param):
    sbox = QSpinBox(self)
    sbox.setRange(param[0], param[1])
    sbox.setValue(int((param[1] - param[1]) / 2))
    return sbox


def setQCalendarWidget(self, func):
    cal = QCalendarWidget(self)
    cal.clicked[QDate].connect(func)
    return cal


def setQHBoxLayout(layouts):
    HBox = QHBoxLayout()
    for no, lay in enumerate(layouts):
        HBox.addLayout(lay[0])
        HBox.setStretch(no, lay[1])
    return HBox


def setQVBoxLayout(layouts):
    VBox = QVBoxLayout()
    for no, lay in enumerate(layouts):
        if type(lay) is int:
            VBox.addStretch(lay)
        else:
            VBox.addLayout(lay)
    return VBox


def setWidQHBox(wid, stretch=None):
    HBox = QHBoxLayout()
    if stretch == 'left' or stretch == 'both':
        HBox.addStretch()
    for w in wid:
        HBox.addWidget(w)
    if stretch == 'right' or stretch == 'both':
        HBox.addStretch()
    return HBox


def setWidQVBox(wid):
    VBox = QVBoxLayout()
    for key, cont in wid.items():
        if cont[1] == 'Label':
            VBox.addWidget(cont[0])
        elif cont[1] == 'PushButton':
            VBox.addWidget(setQPushButton(key, cont[0]))
    return VBox


def setWidQGrid(wid, columnstretch=None):
    Grid = QGridLayout()
    if columnstretch is not None:
        for k, s in enumerate(columnstretch):
            Grid.setColumnStretch(k, s)
    for k, wlst in enumerate(wid):
        for j, w in enumerate(wlst):
            if isinstance(wlst, dict):
                w = wlst[w]
            if w is not None:
                Grid.addWidget(w, k, j)
    return Grid


class setQDialog(QDialog):
    def __init__(self, receiver, args, template=None, title=None, fixedwidth=160):
        super().__init__()
        self.result, self.args, self.template, self.title, self.fixedwidth = receiver, args, template, title, fixedwidth
        self.initUI()

    def initUI(self):
        self.setWindowTitle(self.title)   # title設定
        param = []
        for key, cont in self.template.items():
            if 'Multi' in cont[2]:
                param += [setWidQGrid([[QLabel(k) for k in cont[0]]] + cont[1])]
            else:
                ql = QLabel(cont[0])
                ql.setFixedWidth(self.fixedwidth)
                param += [setWidQHBox([ql, cont[1]], stretch='right')]
        # OK button
        param += [setWidQHBox([setQPushButton('OK', self.on_ok_button, self,
                              [QSizePolicy.Fixed, QSizePolicy.Fixed], [50, 50])], stretch='both')]
        self.setLayout(setQVBoxLayout(param))

        debug_print(self.args, f'IN {self.result=}')
        for key, val in self.result.items():
            if key not in self.template.keys():
                continue
            if 'ComboBox' in self.template[key][2]:
                cbox = self.template[key][1]
                # data付きComboBox(setQComboBox(..., data=[...]))はfindDataで、
                # 従来通りTextがそのまま値のComboBoxはfindTextで現在値を復元する。
                idx = cbox.findData(val)
                if idx < 0:
                    idx = cbox.findText(val)
                cbox.setCurrentIndex(idx)
            elif 'DateEdit' in self.template[key][2]:
                self.template[key][1].setDate(QDate(int(val[0:4]), int(val[5:7]), int(val[8:10])))
            elif 'Calendar' in self.template[key][2]:
                self.template[key][1].setSelectedDate(
                    QDate(int(val[0:4]), int(val[4:6]), int(val[6:8])))
            elif 'MultiSpinBox' in self.template[key][2]:
                if type(val) is str:
                    val = [list(val.split(','))]
                for i, edit_line in enumerate(val):
                    for j, val in enumerate(edit_line):
                        # debug_print(self.args, f'{i=},{j=},{val=},{edit_line=}')
                        self.template[key][1][i][j].setValue(int(val))
            elif 'SpinBox' in self.template[key][2]:
                self.template[key][1].setValue(int(val))
            elif 'MultiLineEdit' in self.template[key][2]:
                for i, edit_line in enumerate(val):
                    for j, val in enumerate(edit_line):
                        self.template[key][1][i][j].setText(val)
            else:
                self.template[key][1].setText(val)

    def on_ok_button(self):
        tmp = {}
        for key, cont in self.template.items():
            if 'ComboBox' in cont[2]:
                data = cont[1].currentData()
                tmp[key] = data if data is not None else cont[1].currentText()
            elif 'Calendar' in cont[2]:
                tmp[key] = cont[1].selectedDate().toString("yyyyMMdd")
            elif 'MultiSpinBox' in cont[2]:
                tmp[key] = ','.join([','.join([k.text() for k in j]) for j in cont[1]])
            elif 'Multi' in cont[2]:
                tmp[key] = [[k.text() for k in j] for j in cont[1]]
            else:
                tmp[key] = cont[1].text()
        self.result = tmp
        debug_print(self.args, f'OUT {self.result=}')
        self.close()


class FigureQtPG:
    """
    FigureQt の pyqtgraph 互換実装。
    window.py を無変更で使えるよう、インターフェースを統一。
    """

    PEAK_HISTORY_WINDOW_SEC = 2.0  # Peak検出用の履歴バッファが保持する秒数
    PEAK_LOCAL_WIDTH = 2  # find_peaksのlocal_width。境界除外幅としても使う
    AVERAGE_TIME_CONSTANT_SEC = 3.0  # Peak検出の閾値(self.average)に使う移動平均の時定数

    def __init__(self, board, figs, args):
        self.board = board
        self.next_loop = False
        self.num_of_loop = 0
        self.top_args = args
        print(f"{args=}")

        pg.setConfigOptions(antialias=False, useOpenGL=False)  # まず安定優先
        self.win = pg.GraphicsLayoutWidget()
        self.fig = self.win
        self._init_fig(figs)

    # ------------------------------------------------------------------
    def _mpl_fargs_to_pg(self, fargs, color):
        """matplotlib の fargs → pyqtgraph の pen/symbol パラメータに変換"""
        # 線幅
        lw = fargs.get('lw', fargs.get('linewidth', 1))

        # linestyle → pen style
        ls_map = {
            '-': Qt.SolidLine,
            '--': Qt.DashLine,
            '-.': Qt.DashDotLine,
            ':': Qt.DotLine,
            '': Qt.NoPen,   # 線なし
        }
        ls = fargs.get('ls', fargs.get('linestyle', '-'))
        pen = pg.mkPen(color, width=lw, style=ls_map.get(ls, Qt.SolidLine))

        # marker → symbol
        marker_map = {
            'o': 'o',
            's': 's',
            '^': 't',
            'v': 't1',
            'd': 'd',
            '+': '+',
            'x': 'x',
            '': None,
        }
        ms = fargs.get('ms', fargs.get('markersize', 0))
        marker = fargs.get('marker', '')
        # ms=0 または marker='' のときは必ず symbol=None
        if ms == 0 or marker == '' or marker is None:
            symbol = None
            symbol_size = 0        # ← NaN回避のため 0 を明示
            symbol_brush = None
        else:
            symbol = marker_map.get(marker, None)
            symbol_size = int(ms)  # ← float→int に変換
            symbol_brush = pg.mkBrush(color) if symbol else None

        return pen, symbol, symbol_size, symbol_brush

    def _mpl_pargs_to_pg(self, pargs):
        """matplotlib の pargs → pyqtgraph の peak marker パラメータに変換"""
        marker_map = {
            'o': 'o',
            's': 's',
            '^': 't',
            'v': 't1',
            'd': 'd',
            '+': '+',
            'x': 'x',
            '': 'o',
        }
        color = pargs.get('color', 'r')
        marker = pargs.get('marker', 'o')
        ms = pargs.get('ms', pargs.get('markersize', 8))
        symbol = marker_map.get(marker, 'o')
        return (pg.mkPen(color), pg.mkBrush(color), ms, symbol)

    def _init_fig(self, figs):
        self.figs, self.args = figs[:-1], figs[-1]
        n_rows, n_cols = np.array(self.figs).shape

        # _init_fig の先頭に一時追加
        debug_print(self.top_args, f'    {self.board.__dict__=}')

        # バッファサイズ（_init_buffers で実測dtを基に上書きされるまでの仮初期化）
        self._buf_size = 1      # ← None だと np.full でエラーになるため仮値
        self._x_grid = np.array([0.0])
        self._buf_y = None
        self._fs_fixed = False
        self._range_fixed = False

        # --- PlotItem / curve / peak / buffer を figs 構造に合わせて生成
        self.plots = []
        self.curves = []
        self.peaks = []
        self._buf_y = []

        # peak_time / peak_interval / average
        self.peak_time = [[[np.zeros(3) for _ in dic['data']]
                           for dic in lst] for lst in self.figs]
        self.peak_interval = np.array([[[0.0 for _ in dic['data']]
                                        for dic in lst] for lst in self.figs])
        self.average = [[[0.0 for _ in dic['data']]
                         for dic in lst] for lst in self.figs]

        COLORS_SET1 = [
            (228, 26, 28),
            (55, 126, 184),
            (77, 175, 74),
            (152, 78, 163),
            (255, 127, 0),
            (255, 255, 51),
            (166, 86, 40),
            (247, 129, 191),
        ]

        sharex_item = None
        for k, lst in enumerate(self.figs):
            self.plots.append([])
            self.curves.append([])
            self.peaks.append([])
            self._buf_y.append([])

            for j, dic in enumerate(lst):
                # --- PlotItem 生成
                p = self.win.addPlot(row=k, col=j)

                # sharex
                if sharex_item is None:
                    sharex_item = p
                elif 'sharex' in self.args.get('subplots', {}):
                    p.setXLink(sharex_item)

                    # grid
                p.showGrid(x=dic['grid'], y=dic['grid'], alpha=0.3)

                # ラベル
                xlabel, ylabel = dic['label']
                if ylabel:
                    p.setLabel('left', ylabel)
                    if xlabel:
                        show_xlabel = (
                            'sharex' not in self.args.get('subplots', {})
                            or k == n_rows - 1
                        )
                        if show_xlabel:
                            p.setLabel('bottom', xlabel)

                # x/y limit
                data_num = dic['data'][0][:-1]
                tmp = []
                for i_lim, num in enumerate(data_num):
                    if dic['limit'][i_lim] == 'auto':
                        raw_flag = dic['data'][0][-1]['raw'][i_lim]
                        if raw_flag:
                            tmp.append(self.board.lim_auto_raw[
                                self.board.structure[num][2]])
                        else:
                            tmp.append(self.board.lim_auto_func[
                                self.board.structure[num][2]])
                    elif dic['limit'][i_lim] is not None:
                        tmp.append(dic['limit'][i_lim])

                p.setXRange(0, self.board.time_width, padding=0)

                # if len(tmp) >= 1 and tmp[0] is not None:
                #     p.setYRange(float(tmp[0][0]), float(tmp[0][1]), padding=0)
                #     p.disableAutoRange()

                # data_num が2要素（x, y）の場合も考慮するなら
                ylim = tmp[-1]  # 最後の要素が常にy範囲
                if ylim is not None:
                    p.setYRange(float(ylim[0]), float(ylim[1]), padding=0)
                    p.disableAutoRange()

                # ズーム・パン無効（matplotlib版と同じ固定表示）
                p.setMouseEnabled(x=False, y=False)
                p.hideButtons()

                self.plots[k].append(p)
                self.curves[k].append([])
                self.peaks[k].append([])
                self._buf_y[k].append([])

                # legend
                if dic['legend']:
                    p.addLegend(offset=(0, 0))

                for i, dat in enumerate(dic['data']):
                    # 色
                    color = COLORS_SET1[(j * len(lst) + i + 1) % len(COLORS_SET1)]

                    # curve
                    fargs = dic.get('fargs', {})
                    pen, symbol, symbol_size, symbol_brush = self._mpl_fargs_to_pg(fargs, color)

                    if dic['legend']:
                        curve = p.plot(pen=pen, symbol=symbol, symbolSize=symbol_size,
                                       symbolBrush=symbol_brush, symbolPen=pg.mkPen(
                                           None),   # シンボルの枠線なし
                                       name=dat[-1].get('leg_lab', ''))
                    else:
                        curve = p.plot(pen=pen, symbol=symbol, symbolSize=symbol_size,
                                       symbolBrush=symbol_brush, symbolPen=pg.mkPen(None),)
                    self.curves[k][j].append(curve)

                    # peak marker
                    pargs = dic.get('pargs', {})
                    pk_pen, pk_brush, pk_size, pk_symbol = self._mpl_pargs_to_pg(pargs)
                    peak_plot = p.plot(pen=None, symbol=pk_symbol, symbolPen=pk_pen,
                                       symbolBrush=pk_brush, symbolSize=pk_size)
                    self.peaks[k][j].append(peak_plot)

                    # y バッファ（nan 初期化）
                    self._buf_y[k][j].append(np.full(self._buf_size, np.nan))

    def _init_buffers(self, dt):
        """初回 update() 時に実測 dt でバッファ・Peak検出用履歴を初期化する。"""
        self._buf_size = int(self.board.time_width / dt) + 1
        self._x_grid = np.linspace(0, self.board.time_width, self._buf_size, endpoint=False)
        self._buf_y = [
            [[np.full(self._buf_size, np.nan) for _ in dic['data']] for dic in lst]
            for lst in self.figs]

        # Peak検出の閾値(self.average)用の移動平均係数。dtから時定数を逆算する。
        # (旧実装は alpha=0.5 固定で信号にほぼ即座に追従してしまい、静穏区間で閾値が
        #  ゼロ近くまで落ちて僅かなノイズもPeakとして拾ってしまっていた)
        self._avg_alpha = min(1.0, dt / self.AVERAGE_TIME_CONSTANT_SEC)

        # peak検出用履歴バッファ
        self.PEAK_HISTORY = int(self.PEAK_HISTORY_WINDOW_SEC / dt)
        debug_print(self.top_args, f'PEAK_HISTORY={self.PEAK_HISTORY}, dt={dt:.6f}')
        self._peak_history_x = [
            [[deque(maxlen=self.PEAK_HISTORY) for _ in dic['data']] for dic in lst]
            for lst in self.figs]
        self._peak_history_y = [
            [[deque(maxlen=self.PEAK_HISTORY) for _ in dic['data']] for dic in lst]
            for lst in self.figs]
        self._fs_fixed = True

    def update(self, stream):
        data_t = next(stream).transpose()

        # 初回のみ実測 dt でバッファを確定
        if not self._fs_fixed:
            dt = (data_t[0][-1] - data_t[0][0]) / (data_t.shape[1] - 1)
            self._init_buffers(dt)

        lp_tmp = int(data_t[0][-1] / self.board.time_width)
        if lp_tmp == self.num_of_loop:
            self.next_loop = False
        else:
            self.num_of_loop = lp_tmp
            self.next_loop = True

        if not self.next_loop:
            for k, lst in enumerate(self.figs):
                for j, dic in enumerate(lst):
                    for i, dat in enumerate(dic['data']):
                        plot_data = data_t[
                            np.array(dat[:-1]) +
                            np.array(dat[-1]['raw']) * len(self.board.structure)
                        ]

                        # 現在の x 位置（0〜time_width）
                        x_now = plot_data[0][-1] % self.board.time_width
                        x_prev = plot_data[0][-2] % self.board.time_width
                        y_now = plot_data[1][-1]   # ← 追加
                        y_prev = plot_data[1][-2]   # ← 追加

                        self._erase_and_write_buffer(k, j, i, x_prev, x_now, y_prev, y_now)

                        self.average[k][j][i] = (self.average[k][j][i] * (1 - self._avg_alpha)
                                                 + y_now * self._avg_alpha)

                        if dat[-1]['peak']:
                            self._detect_and_record_peak(k, j, i, plot_data[0][-1], y_now)

        return data_t.T[[0, -1]].T, self.peak_interval.transpose()[0][0]

    def _erase_and_write_buffer(self, k, j, i, x_prev, x_now, y_prev, y_now):
        """プロット(k,j,i)のyバッファについて、現在位置より少し先を
        nanクリアしてから新しい2点を線形補間でグリッドへ書き込み、Curveに反映する。"""
        # ① squares相当：現在位置より少し先のnanクリア範囲を決定
        erase_width = self.board.time_width / 20
        erase_end = (x_now + erase_width) % self.board.time_width

        # ② グリッドインデックスに変換
        def x_to_idx(x):
            return int(x / self.board.time_width * self._buf_size)

        idx_prev = x_to_idx(x_prev)
        idx_now = x_to_idx(x_now)
        idx_erase_end = x_to_idx(erase_end)

        # ③ 先読みクリア（squares の代替）
        if idx_erase_end > x_to_idx(x_now):
            self._buf_y[k][j][i][x_to_idx(x_now):idx_erase_end] = np.nan
        else:
            # wrap around
            self._buf_y[k][j][i][x_to_idx(x_now):] = np.nan
            self._buf_y[k][j][i][:idx_erase_end] = np.nan

        # ④ 新しい2点を書き込み（線形補間でグリッドへ）
        if idx_prev != idx_now:
            # 2点間を補間してグリッドに埋める
            x_range = self._x_grid[idx_prev:idx_now + 1]
            if len(x_range) > 1 and (x_now - x_prev) > 0:
                y_interp = np.interp(x_range, [x_prev, x_now], [y_prev, y_now])
                self._buf_y[k][j][i][idx_prev:idx_now + 1] = y_interp
            else:
                self._buf_y[k][j][i][idx_now] = y_now

        # ⑤ setData（x は固定グリッド、y だけ更新）
        self.curves[k][j][i].setData(x=self._x_grid, y=self._buf_y[k][j][i])

    def _detect_and_record_peak(self, k, j, i, x_raw, y_now):
        """プロット(k,j,i)のPeak履歴に新しい点を追加し、PEAK_HISTORY点たまったら
        Peakを検出してpeak_time/peak_interval/散布図マーカーに反映する。"""
        # 履歴に追加（maxlen=PEAK_HISTORYのdequeなので、超えた分は古いものから自動的に破棄される）
        self._peak_history_x[k][j][i].append(x_raw)
        self._peak_history_y[k][j][i].append(y_now)

        # PEAK_HISTORY点たまったらpeak検出
        if len(self._peak_history_y[k][j][i]) == self.PEAK_HISTORY:
            hy = np.array(self._peak_history_y[k][j][i])
            hx = np.array(self._peak_history_x[k][j][i])

            min_peak_distance = int(
                self.board.min_peak_dist / (hx[-1] - hx[0]) * self.PEAK_HISTORY)
            p_idxs = utils.find_peaks(
                hy, amp_thre=self.average[k][j][i], local_width=self.PEAK_LOCAL_WIDTH,
                min_peak_distance=min_peak_distance)

            # ウィンドウの右端付近(直近local_width点)はfind_peaksの端点パディング
            # (右端をlocal_width回複製する)により、まだ下降が確認できていない点でも
            # 自分自身の複製とtieして極大/極小と誤判定されうる。信頼できない候補として除外する。
            if len(p_idxs) > 0:
                p_idxs = p_idxs[p_idxs < len(hy) - self.PEAK_LOCAL_WIDTH]

            if len(p_idxs) > 0:
                # 最新のpeakのみ使用（履歴の中央付近）
                p_idx = p_idxs[-1]
                # PEAK_HISTORYがdeque(maxlen)である以上この分岐はバッファが埋まった
                # 後も毎サンプル真になるため、「新しいPeakかどうか」をここで判定しない
                # と、同一Peakを毎回再検出してpeak_time(直近3件)の履歴を重複で埋め潰し、
                # peak_interval(ひいては心拍数)が実際より大幅に短く算出されてしまう。
                if hx[p_idx] > self.peak_time[k][j][i][-1]:
                    peak_x = hx[p_idx] % self.board.time_width
                    peak_y = hy[p_idx]
                    self.peak_time[k][j][i][:-1] = self.peak_time[k][j][i][1:]
                    self.peak_time[k][j][i][-1] = hx[p_idx]
                    self.peak_interval[k][j][i] = np.average(
                        np.diff(self.peak_time[k][j][i]))
                    self.peaks[k][j][i].setData(x=[peak_x], y=[peak_y])
