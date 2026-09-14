"""pyqtgraph plotting layer: InitPlots (subplot grid setup), the
plot_timeseries/plot_scalogram family that draws PlotData/PlotImageData onto
it, and the CrossHairManager/RegionManager mouse-interaction helpers."""

import time

import numpy as np
import pyqtgraph as pg
import scipy.signal as signal
from pyqtgraph.Qt import QtCore

from mylib.i18n import t as tr
from mylib.plot_utils.common import (COLORS, add_right_axis, decimate_fixed,
                                     decimate_for_range, mk_image0, mk_label,
                                     mk_plot, mouseMoved, mouseMovedImage,
                                     set_axis_label, style_dict)
from mylib.plot_utils.reading import PlotData

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
