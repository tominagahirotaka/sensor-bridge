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
        lcd.setDigitCount(digitcount)     # change digit count to 7 (default is 5? digits)
    if style is not None:
        lcd.setSegmentStyle(eval('QLCDNumber.' + style))
    return lcd


def setQComboBox(self, items, data=None):
    """items: list of displayed text. data: list of the actual value tied to
    each item (when omitted, the text itself is the value, the previous
    behavior). Example: setQComboBox(self, ['1Hz', '10Hz'], data=['1', '2'])
    keeps '1Hz'/'10Hz' displayed while the selected result (via setQDialog)
    becomes '1'/'2'."""
    cbox = QComboBox(self)
    if data is not None:
        for text, value in zip(items, data):
            cbox.addItem(text, value)
    else:
        cbox.addItems(items)
    return cbox


def setQAction(self, name, func, Icon=None):
    action = QAction(Icon, '&' + name, self) if Icon is not None else QAction('&' + name, self)
    # Convention: assign a Ctrl+<letter> shortcut for each uppercase letter
    # in `name` (e.g. "MArk" -> both Ctrl+M and Ctrl+A trigger this action).
    # For a name with no uppercase letters (e.g. Japanese text), no shortcut
    # is assigned (the menu item itself still works).
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
        self.setWindowTitle(self.title)   # set the title
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
                # A ComboBox with data (setQComboBox(..., data=[...])) restores
                # its current value via findData; a plain text-as-value
                # ComboBox restores it via findText.
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
    A pyqtgraph-compatible implementation of FigureQt.
    Keeps the same interface so window.py can use it unmodified.
    """

    PEAK_HISTORY_WINDOW_SEC = 2.0  # seconds of history kept by the peak-detection buffer
    PEAK_LOCAL_WIDTH = 2  # find_peaks' local_width; also used as the edge-exclusion width
    AVERAGE_TIME_CONSTANT_SEC = 3.0  # time constant of the moving average used for the peak-detection threshold (self.average)
    PEAK_TIME_BUFFER_SIZE = 7  # number of recent peak times kept for computing peak_interval

    def __init__(self, board, figs, args):
        self.board = board
        self.next_loop = False
        self.num_of_loop = 0
        self.top_args = args
        # Every time Test/Run/caliBrate is pressed, the Pico's elapsed time
        # starts counting again from near 0. self (FigureQtPG) is reused for
        # the whole lifetime of get.py (initCanvas() is only called once),
        # so this is used to detect "time jumped backward" and reset the
        # peak-detection state.
        self._last_seen_time = float('-inf')
        print(f"{args=}")

        pg.setConfigOptions(antialias=False, useOpenGL=False)  # prioritize stability first
        self.win = pg.GraphicsLayoutWidget()
        self.fig = self.win
        self._init_fig(figs)

    # ------------------------------------------------------------------
    def _mpl_fargs_to_pg(self, fargs, color):
        """Convert matplotlib's fargs to pyqtgraph's pen/symbol parameters"""
        # line width
        lw = fargs.get('lw', fargs.get('linewidth', 1))

        # linestyle → pen style
        ls_map = {
            '-': Qt.SolidLine,
            '--': Qt.DashLine,
            '-.': Qt.DashDotLine,
            ':': Qt.DotLine,
            '': Qt.NoPen,   # no line
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
        # symbol must always be None when ms=0 or marker=''
        if ms == 0 or marker == '' or marker is None:
            symbol = None
            symbol_size = 0        # explicit 0 to avoid NaN
            symbol_brush = None
        else:
            symbol = marker_map.get(marker, None)
            symbol_size = int(ms)  # convert float -> int
            symbol_brush = pg.mkBrush(color) if symbol else None

        return pen, symbol, symbol_size, symbol_brush

    def _mpl_pargs_to_pg(self, pargs):
        """Convert matplotlib's pargs to pyqtgraph's peak marker parameters"""
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

        # Temporarily added at the top of _init_fig
        debug_print(self.top_args, f'    {self.board.__dict__=}')

        # Buffer size (a placeholder until _init_buffers overwrites it based on the measured dt)
        self._buf_size = 1      # placeholder, since None would error in np.full
        self._x_grid = np.array([0.0])
        self._buf_y = None
        self._fs_fixed = False
        self._range_fixed = False

        # --- Create PlotItem / curve / peak / buffer to match the figs structure
        self.plots = []
        self.curves = []
        self.peaks = []
        self._buf_y = []

        # peak_time / peak_interval / average
        self.peak_time = [[[np.zeros(self.PEAK_TIME_BUFFER_SIZE) for _ in dic['data']]
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
                # --- Create the PlotItem
                p = self.win.addPlot(row=k, col=j)

                # sharex
                if sharex_item is None:
                    sharex_item = p
                elif 'sharex' in self.args.get('subplots', {}):
                    p.setXLink(sharex_item)

                    # grid
                p.showGrid(x=dic['grid'], y=dic['grid'], alpha=0.3)

                # label
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

                # to also allow for data_num having 2 elements (x, y)
                ylim = tmp[-1]  # the last element is always the y range
                if ylim is not None:
                    p.setYRange(float(ylim[0]), float(ylim[1]), padding=0)
                    p.disableAutoRange()

                # disable zoom/pan (fixed display, same as the matplotlib version)
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
                    # color
                    color = COLORS_SET1[(j * len(lst) + i + 1) % len(COLORS_SET1)]

                    # curve
                    fargs = dic.get('fargs', {})
                    pen, symbol, symbol_size, symbol_brush = self._mpl_fargs_to_pg(fargs, color)

                    if dic['legend']:
                        curve = p.plot(pen=pen, symbol=symbol, symbolSize=symbol_size,
                                       symbolBrush=symbol_brush, symbolPen=pg.mkPen(
                                           None),   # no symbol outline
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

                    # y buffer (initialized to nan)
                    self._buf_y[k][j].append(np.full(self._buf_size, np.nan))

    def _init_buffers(self, dt):
        """Initialize the buffers and peak-detection history using the measured dt on the first update() call."""
        self._buf_size = int(self.board.time_width / dt) + 1
        self._x_grid = np.linspace(0, self.board.time_width, self._buf_size, endpoint=False)
        self._buf_y = [
            [[np.full(self._buf_size, np.nan) for _ in dic['data']] for dic in lst]
            for lst in self.figs]

        # Moving-average coefficient for the peak-detection threshold
        # (self.average), derived from dt so it matches the intended time
        # constant. (The old implementation used a fixed alpha=0.5, which
        # tracked the signal almost instantly and let the threshold fall
        # near zero during quiet periods, picking up even slight noise as a peak.)
        self._avg_alpha = min(1.0, dt / self.AVERAGE_TIME_CONSTANT_SEC)

        # history buffer for peak detection
        self.PEAK_HISTORY = int(self.PEAK_HISTORY_WINDOW_SEC / dt)
        debug_print(self.top_args, f'PEAK_HISTORY={self.PEAK_HISTORY}, dt={dt:.6f}')
        self._peak_history_x = [
            [[deque(maxlen=self.PEAK_HISTORY) for _ in dic['data']] for dic in lst]
            for lst in self.figs]
        self._peak_history_y = [
            [[deque(maxlen=self.PEAK_HISTORY) for _ in dic['data']] for dic in lst]
            for lst in self.figs]
        self._fs_fixed = True

    def _reset_peak_detection_state(self):
        """Reset the peak-detection buffers (history, threshold, recent peak
        times/interval) to their initial state when Test/Run/caliBrate is
        restarted and the Pico's elapsed time jumps backward."""
        for k, lst in enumerate(self.figs):
            for j, dic in enumerate(lst):
                for i, dat in enumerate(dic['data']):
                    self._peak_history_x[k][j][i].clear()
                    self._peak_history_y[k][j][i].clear()
                    self.average[k][j][i] = 0.0
                    self.peak_time[k][j][i][:] = 0.0
                    self.peak_interval[k][j][i] = 0.0

    def update(self, stream):
        data_t = next(stream).transpose()

        # Fix the buffer size from the measured dt, only on the first call
        if not self._fs_fixed:
            dt = (data_t[0][-1] - data_t[0][0]) / (data_t.shape[1] - 1)
            self._init_buffers(dt)
        elif data_t[0][-1] < self._last_seen_time - 1.0:
            # Test/Run/caliBrate was pressed again, and the Pico's elapsed
            # time started counting again from near 0. Without clearing the
            # history buffer, the previous session's old (differently
            # scaled) timestamps would mix with the new ones, breaking the
            # min_peak_distance calculation (e.g. producing a negative
            # value) and making peak detection garbage for a few seconds.
            self._reset_peak_detection_state()
        self._last_seen_time = data_t[0][-1]

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
                        try:
                            plot_data = data_t[
                                np.array(dat[:-1]) +
                                np.array(dat[-1]['raw']) * len(self.board.structure)
                            ]

                            # current x position (0 to time_width)
                            x_now = plot_data[0][-1] % self.board.time_width
                            x_prev = plot_data[0][-2] % self.board.time_width
                            y_now = plot_data[1][-1]   # added
                            y_prev = plot_data[1][-2]   # added

                            self._erase_and_write_buffer(k, j, i, x_prev, x_now, y_prev, y_now)

                            self.average[k][j][i] = (self.average[k][j][i] * (1 - self._avg_alpha)
                                                     + y_now * self._avg_alpha)

                            if dat[-1]['peak']:
                                self._detect_and_record_peak(k, j, i, plot_data[0][-1], y_now)
                        except Exception:
                            # PyQt swallows exceptions raised inside a slot
                            # (e.g. QTimer.timeout) by default without
                            # displaying them, so the failure otherwise looks
                            # like silent "nothing happens" with no visible
                            # cause. Print the traceback explicitly here, and
                            # cap it to the first few occurrences so it
                            # doesn't spam every sample as long as the
                            # underlying condition persists.
                            err_count = getattr(self, '_update_err_count', None)
                            if err_count is None:
                                err_count = self._update_err_count = {}
                            ekey = (k, j, i)
                            err_count[ekey] = err_count.get(ekey, 0) + 1
                            if err_count[ekey] <= 3:
                                import traceback
                                print(f'[ERROR] update() failed for k={k} j={j} i={i} '
                                      f'(occurrence #{err_count[ekey]}):')
                                traceback.print_exc()

        return data_t.T[[0, -1]].T, self.peak_interval.transpose()[0][0]

    def _erase_and_write_buffer(self, k, j, i, x_prev, x_now, y_prev, y_now):
        """For plot (k,j,i)'s y buffer, nan-clear a short span just ahead of
        the current position, then write the new two points into the grid
        via linear interpolation and push them to the curve."""
        # (1) equivalent of "squares": decide the nan-clear span just ahead of the current position
        erase_width = self.board.time_width / 20
        erase_end = (x_now + erase_width) % self.board.time_width

        # (2) convert to grid indices
        def x_to_idx(x):
            return int(x / self.board.time_width * self._buf_size)

        idx_prev = x_to_idx(x_prev)
        idx_now = x_to_idx(x_now)
        idx_erase_end = x_to_idx(erase_end)

        # (3) look-ahead clear (replacement for squares)
        if idx_erase_end > x_to_idx(x_now):
            self._buf_y[k][j][i][x_to_idx(x_now):idx_erase_end] = np.nan
        else:
            # wrap around
            self._buf_y[k][j][i][x_to_idx(x_now):] = np.nan
            self._buf_y[k][j][i][:idx_erase_end] = np.nan

        # (4) write the new two points (into the grid via interpolation)
        if idx_prev != idx_now:
            # interpolate between the two points to fill the grid
            x_range = self._x_grid[idx_prev:idx_now + 1]
            if len(x_range) > 1 and (x_now - x_prev) > 0:
                y_interp = np.interp(x_range, [x_prev, x_now], [y_prev, y_now])
                self._buf_y[k][j][i][idx_prev:idx_now + 1] = y_interp
            else:
                self._buf_y[k][j][i][idx_now] = y_now

        # (5) setData (x is the fixed grid; only y is updated)
        self.curves[k][j][i].setData(x=self._x_grid, y=self._buf_y[k][j][i])

    def _detect_and_record_peak(self, k, j, i, x_raw, y_now):
        """Append a new point to plot (k,j,i)'s peak history, and once
        PEAK_HISTORY points have accumulated, detect peaks and update
        peak_time/peak_interval/the scatter marker."""
        # Append to the history (a deque with maxlen=PEAK_HISTORY, so anything over the limit is auto-discarded oldest-first)
        self._peak_history_x[k][j][i].append(x_raw)
        self._peak_history_y[k][j][i].append(y_now)

        # Once PEAK_HISTORY points have accumulated, run peak detection
        if len(self._peak_history_y[k][j][i]) == self.PEAK_HISTORY:
            hy = np.array(self._peak_history_y[k][j][i])
            hx = np.array(self._peak_history_x[k][j][i])

            min_peak_distance = int(
                self.board.min_peak_dist / (hx[-1] - hx[0]) * self.PEAK_HISTORY)
            p_idxs = utils.find_peaks(
                hy, amp_thre=self.average[k][j][i], local_width=self.PEAK_LOCAL_WIDTH,
                min_peak_distance=min_peak_distance)
            n_raw = len(p_idxs)

            # Near the window's right edge (the last local_width points),
            # find_peaks' edge padding (which duplicates the rightmost value
            # local_width times) can make a point that hasn't actually
            # started to descend yet tie with its own duplicate and be
            # misjudged as a local max/min. Exclude these as untrustworthy candidates.
            if len(p_idxs) > 0:
                p_idxs = p_idxs[p_idxs < len(hy) - self.PEAK_LOCAL_WIDTH]

            # --debug only: a lightweight log to trace why a peak isn't
            # found / HR isn't updating. Printed roughly once per second per
            # (k,j,i) (once every PEAK_HISTORY/2 calls).
            cnt_dict = getattr(self, '_peak_debug_count', None)
            if cnt_dict is None:
                cnt_dict = self._peak_debug_count = {}
            key = (k, j, i)
            cnt_dict[key] = cnt_dict.get(key, 0) + 1
            if cnt_dict[key] % max(1, self.PEAK_HISTORY // 2) == 0:
                debug_print(
                    self.top_args,
                    f'peak k={k} j={j} i={i}: y_range=({hy.min():.3f},{hy.max():.3f}) '
                    f'amp_thre={self.average[k][j][i]:.4f} min_peak_distance={min_peak_distance} '
                    f'n_candidates_raw={n_raw} n_after_edge_filter={len(p_idxs)} '
                    f'peak_interval={self.peak_interval[k][j][i]:.4f}')

            if len(p_idxs) > 0:
                # use only the most recent peak (near the middle of the history)
                p_idx = p_idxs[-1]
                # Since PEAK_HISTORY is a deque(maxlen), this branch stays
                # true on every sample once the buffer is full. Without
                # checking here whether this is actually a *new* peak, the
                # same peak would be re-detected every time, duplicating
                # entries in the peak_time history (the most recent
                # PEAK_TIME_BUFFER_SIZE entries) and making peak_interval
                # (and hence the heart rate) come out much shorter than it
                # actually is.
                if hx[p_idx] > self.peak_time[k][j][i][-1]:
                    peak_x = hx[p_idx] % self.board.time_width
                    peak_y = hy[p_idx]
                    self.peak_time[k][j][i][:-1] = self.peak_time[k][j][i][1:]
                    self.peak_time[k][j][i][-1] = hx[p_idx]
                    # If a secondary bump in the pulse wave (e.g. a dicrotic
                    # notch) is spuriously detected once as a separate peak,
                    # that single occurrence would badly skew a plain diff
                    # average. A simple mean would let the HBR display get
                    # pulled by that one occurrence, producing a "sometimes
                    # doubles" kind of instability, so an outlier-resistant
                    # median is used instead.
                    self.peak_interval[k][j][i] = np.median(
                        np.diff(self.peak_time[k][j][i]))
                    self.peaks[k][j][i].setData(x=[peak_x], y=[peak_y])
