"""pyqtgraph plotting layer: InitPlots (subplot grid setup), the
plot_timeseries/plot_scalogram family that draws PlotData/PlotImageData onto
it, and the CrossHairManager/RegionManager mouse-interaction helpers."""

import time

import numpy as np
import pyqtgraph as pg
import scipy.signal as signal
from PyQt5.QtWidgets import QGraphicsProxyWidget, QPushButton
from pyqtgraph.Qt import QtCore

from mylib.i18n import t as tr
from mylib.plot_utils.common import (COLORS, add_right_axis, decimate_fixed,
                                     decimate_for_range, mk_image0, mk_label,
                                     mk_plot, mouseMoved, mouseMovedImage,
                                     set_axis_label, style_dict)
from mylib.plot_utils.reading import PlotData

# Initialize plots
# Prepare num_plots plots plus one control plot (p_base); rows start at 1 since the label is row=0


class InitPlots:
    def __init__(self, win, num_plots):
        self.title = ''
        # Leave col=0 as a narrow gutter column reserved for the Full Range
        # button; the actual plots are placed starting at col=1 (the second
        # element of both mk_label's and mk_plot's layout is the column).
        self.label = mk_label(win, layout=[0, 1, 1], justify='left')  # right')  # make label
        self.plts, self.plts_right = [], []
        for i in range(num_plots):
            p1 = mk_plot(win, layout=[i + 1, 1, 4])
            p2 = add_right_axis(p1)
            self.plts.append(p1)
            self.plts_right.append(p2)
        self.color = COLORS[:num_plots]
        self.p_base = mk_plot(win, layout=[num_plots + 1, 1, 1])
        # The tick values themselves carry no meaning here (this is just an
        # overview plot), so hide them. Removing the whole axis area with
        # hideAxis, though, would misalign this Y axis width with p1/p2's,
        # making the X axis look shifted relative to the plots above -- so
        # only the tick value display is hidden, and the axis still occupies
        # its usual width.
        self.p_base.getAxis('left').setStyle(showValues=False)

        # Place the Full Range toggle button in the empty space to the left
        # of the bottom row (p_base). This addresses the request to place it
        # next to the top toolbar's Full Range button for easier access.
        self.full_range_button = QPushButton("F")
        self.full_range_button.setFixedWidth(24)
        self.full_range_button.setToolTip(tr('plot.gui.full_range_tip'))
        self.full_range_button.setCheckable(True)
        self.full_range_button.setStyleSheet(
            "QPushButton:checked { background-color: #ffca28; }")
        proxy = QGraphicsProxyWidget()
        proxy.setWidget(self.full_range_button)
        win.addItem(proxy, row=num_plots + 1, col=0)

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

    # Hide the axis
    def toggle_right_axis(self, visible):
        for p1 in self.plts:
            p1.getAxis('right').setStyle(showValues=visible)  # hide the tick values
            p1.getAxis('right').setVisible(visible)           # show/hide the axis itself

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

    assert len(xy.data) == len(xy.labels) == len(plots.plts), "lengths do not match"
    for (x, y), l, p, col in zip(xy.data, xy.labels, plots.plts, COLORS):
        set_axis_label(p, l)              # y-axis label
        x_d, y_d = decimate_fixed(x, y)  # decimate
        print(tr('pu.decimate_points', before=len(x), after=len(x_d)))
        curves.append(p.plot(x_d, y_d, pen=pg.mkPen(color=col, width=5), skipFiniteCheck=True))

    # Region select
    set_axis_label(plots.p_base, xy.xlabel)  # x-axis label
    x_d0, y_d0 = decimate_fixed(xy.data[0][0], xy.data[0][1])
    p_base_plot = plots.p_base.plot(x_d0, y_d0, pen="black", skipFiniteCheck=True)

    region_mgr = RegionManager(plots.p_base, p_base_plot, plots.plts, curves=curves, xy=xy)

    cross_hair = CrossHairManager(mouseMoved, plots, xy)

    return curves, p_base_plot, region_mgr, cross_hair

# additional timeseries plot


def add_timeseries(plots, xy):
    curves = []
    assert len(xy.data) == len(xy.labels) == len(plots.plts), "lengths do not match"
    for (x, y), l, p, col in zip(xy.data, xy.labels, plots.plts, COLORS[1:]):
        # set_axis_label(p, l)              # y-axis label
        x_d, y_d = decimate_fixed(x, y)  # decimate
        curves.append(p.plot(x_d, y_d, pen=pg.mkPen(color=col, width=5)))
    return curves

# plot right axis (supports multiple curves)


def plot_right_axis(plts_right, xys):
    curves_all = []
    for num, xy in enumerate(xys):
        curves = []
        assert len(xy.data) == len(xy.labels) == len(plts_right), "lengths do not match"
        for (x, y), l, p, col in zip(xy.data, xy.labels, plts_right, COLORS[num + 1:]):
            # set_axis_label(p, l)              # y-axis label
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
        # 10% of y's variation range as the prominence
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
    set_axis_label(plots.p_base, xyz.xlabel)  # x-axis label (set explicitly each time, same as plot_timeseries)

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
    # Pass the unit through as seconds. pyqtgraph's AxisItem auto-picks an
    # SI prefix (ms/us/etc.) to display from units='s', so pre-converting to
    # ms and setting the unit to 'ms' here would double up the 'm' prefix
    # into a wrong "(mms)" label whenever the interval is under 1ms (e.g. at
    # a high ODR).
    diff_timeinterval = np.diff(time)
    title = tr('pu.time_interval_histogram_title')
    plt = win.addPlot(title=title)               # add the plot area
    # Including a rare large gap (e.g. from a checkpoint) as-is in the
    # equal-width bin range pushes the vast majority of sample intervals,
    # which span less than 1% of the total width, into a single bin -- the
    # plot ends up looking like a single thin needle despite being labeled a
    # histogram. A histogram's bin area (width x height) is what should
    # carry meaning, so the displayed range is restricted to the main body
    # of the distribution (the 1st-99th percentile) and outliers are folded
    # into the end bins (via np.clip), so the actual shape of the data's
    # distribution remains visible.
    lo, hi = np.percentile(diff_timeinterval, [1, 99])
    display_data = np.clip(diff_timeinterval, lo, hi) if hi > lo else diff_timeinterval
    optimal_bins = auto_bins(display_data)  # or get_optimal_bins(display_data)
    y, x = np.histogram(display_data, bins=optimal_bins)
    # Setting only the brush to red without also specifying a pen leaves
    # pyqtgraph's default opaque gray (200,200,200) as each bin's border, so
    # when there are many/narrow bins, that opaque gray outline visually
    # dominates over the translucent red fill and the whole plot ends up
    # looking grayish. Set the pen to a matching red as well.
    plt.plot(x, y, stepMode=True, fillLevel=0,
              pen=(150, 0, 0), brush=(255, 0, 0, 150))                  # draw the histogram (red stands out against the gray background)
    plt.setLabels(left='Count', bottom=('Time Interval', 's'))         # set axis labels
    plt.showGrid(x=True, y=True)                                       # show the grid
    return plt


def find_peaks_in_timeseries(t, y, height=None, distance=None, prominence=None):
    """
    Detect peak positions and values from time-series data

    Parameters:
        t (array-like): array of timestamps
        y (array-like): array of values
        height (float or tuple, optional): minimum/maximum peak height
        distance (int, optional): minimum distance between peaks (in samples)
        prominence (float, optional): peak prominence

    Returns:
        peaks_t (np.ndarray): peak timestamps
        peaks_y (np.ndarray): peak values
    """
    peaks, _ = signal.find_peaks(y, height=height, distance=distance, prominence=prominence)
    peaks_t = np.array(t)[peaks]
    peaks_y = np.array(y)[peaks]
    return peaks_t, peaks_y


# For Histogram
# When near-constant-interval data has a few outliers mixed in, the bin
# width collapses toward 0 and the bin count explodes, which can make
# np.histogram run out of memory -- so an upper bound is set.
MAX_AUTO_BINS = 1000


def auto_bins(data):
    # Freedman-Diaconis method
    iqr = np.percentile(data, 75) - np.percentile(data, 25)
    data_range = np.max(data) - np.min(data)
    if iqr <= 0 or data_range <= 0:
        return 10
    h = 2 * iqr / (len(data) ** (1 / 3))  # bin width
    bins = int(data_range / h)
    return min(max(10, bins), MAX_AUTO_BINS)  # minimum 10 bins, maximum MAX_AUTO_BINS bins

# or


def get_optimal_bins(data):
    # Method based on Scott's standard deviation rule
    std = np.std(data)
    data_range = np.max(data) - np.min(data)
    if std <= 0 or data_range <= 0:
        return 10
    h = 3.49 * std * (len(data) ** (-1 / 3))
    bins = int(data_range / h)
    return min(max(10, bins), MAX_AUTO_BINS)


class CrossHairManager:
    """Class managing crosshair creation and mouse tracking"""

    THROTTLE_MS = 16  # roughly 60fps

    def __init__(self, funcMouseMoved, plots, xy):
        """
        funcMouseMoved : function to call on mouse movement
        plots          : the plots object
        xy             : the display object (labels, etc.)
        """
        # --- keep state as instance variables ---
        self.funcMouseMoved = funcMouseMoved
        self.plots = plots
        self.xy = xy
        self._last_update = 0          # timestamp used for throttling

        # Create the crosshair and connect signals
        self.vLine, self.hLine = self._mk_cross_hair()
        self._connect_signals()

    # -------------------------------------------------- #
    #  Create the crosshair                              #
    # -------------------------------------------------- #
    def _mk_cross_hair(self):
        """Add and return a crosshair line for each plot"""
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
    #  Connect signals                                    #
    # -------------------------------------------------- #
    def _connect_signals(self):
        """Connect each plot's mouse-move signal"""
        for p in self.plots.plts:
            p.scene().sigMouseMoved.connect(self._on_mouse_moved)

    # -------------------------------------------------- #
    #  Mouse-move handler (throttled)                     #
    # -------------------------------------------------- #
    def _on_mouse_moved(self, evt):
        """Method called directly from the signal"""
        now = time.monotonic() * 1000
        if now - self._last_update < self.THROTTLE_MS:
            return                        # skip
        self._last_update = now

        # Call the original funcMouseMoved
        self.funcMouseMoved(
            evt,
            self.plots,
            self.vLine,
            self.hLine,
            self.xy
        )

    def cleanup(self):
        """Safely remove the crosshair from the scene"""
        for p, vl, hl in zip(self.plots.plts, self.vLine, self.hLine):
            try:
                if vl.scene() is not None:
                    p.removeItem(vl)
                if hl.scene() is not None:
                    p.removeItem(hl)
            except Exception:
                pass


class RegionManager:
    """Class managing LinearRegion creation and updates"""

    THROTTLE_MS = 32  # ~30fps (the region can be lower than the crosshair)

    def __init__(self, p_base, plotted_data, plt, curves=None, xy=None):
        self.curves = curves  # added
        self.xy = xy      # added (for referencing the original data)
        self.x_shift = 0.0
        self.p_base = p_base
        self.plotted_data = plotted_data
        self.plt = plt
        self._last_region_update = 0
        self._last_range_update = 0
        self._updating = False  # flag to prevent recursive updates
        self._initialized = False  # added
        self._data_min_x = None       # for the full-range button: the full x range of the data
        self._data_max_x = None
        self._saved_region = None     # for the full-range button: the previously selected range
        self._full_range_active = False

        # Create the region and connect signals
        self.region = self._mk_region()
        self._connect_signals()

        # Set the initial range on a delay
        QtCore.QTimer.singleShot(0, self._set_initial_region)

    # -------------------------------------------------- #
    #  Create the region                                  #
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
    #  Connect signals                                    #
    # -------------------------------------------------- #
    def _connect_signals(self):
        # region-changed signal
        self.region.sigRegionChanged.connect(self._on_region_changed)

        # each plot's range-changed signal
        for p in self.plt:
            if not hasattr(p, '_region_update_connected'):
                p.sigRangeChanged.connect(self._on_range_changed)
                p._region_update_connected = True

    # -------------------------------------------------- #
    #  Set the initial region range                       #
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
        self._data_min_x, self._data_max_x = min_x, max_x
        self._initialized = True  # setup complete

    def set_x_shift(self, shift):
        self.x_shift = shift

    # -------------------------------------------------- #
    #  Toggle full-range display                          #
    # -------------------------------------------------- #
    def toggle_full_range(self):
        """Toggle between full-range display and the previously selected
        range each time this is called.
        Returns: True if full-range display is active after the toggle
        (used by the caller to sync the button's appearance)."""
        if self._full_range_active:
            if self._saved_region is not None:
                self.region.setRegion(self._saved_region)
            self._full_range_active = False
        else:
            if self._data_min_x is None or self._data_max_x is None:
                return False  # the initial region hasn't been set up yet
            self._saved_region = self.region.getRegion()
            self.region.setRegion([self._data_min_x, self._data_max_x])
            self._full_range_active = True
        return self._full_range_active

    # -------------------------------------------------- #
    #  When the region moves -> update the plots' x range  #
    # -------------------------------------------------- #
    def _on_region_changed(self):
        # throttling
        now = time.monotonic() * 1000
        if now - self._last_region_update < self.THROTTLE_MS:
            return
        self._last_region_update = now

        # prevent recursion
        if self._updating:
            return
        self._updating = True

        try:
            min_x, max_x = self.region.getRegion()
            for p in self.plt:
                p.setXRange(min_x, max_x, padding=0)

            # Redraw the data within the displayed range at higher resolution
            if self.curves and self.xy:
                for cur, (x, y) in zip(self.curves, self.xy.data):
                    x_shifted = x - self.x_shift  # apply the shift
                    x_d, y_d = decimate_for_range(x_shifted, y, min_x, max_x)
                    cur.setData(x_d, y_d)

        finally:
            self._updating = False

    def _on_range_changed(self, view, range_):
        # ignore until initialization is complete
        if not self._initialized:
            return

        # throttling
        now = time.monotonic() * 1000
        if now - self._last_range_update < self.THROTTLE_MS:
            return
        self._last_range_update = now

        # prevent recursion
        if self._updating:
            return
        self._updating = True

        try:
            x_range = range_[0]  # [[xmin,xmax],[ymin,ymax]]
            self.region.setRegion(x_range)
        finally:
            self._updating = False

    def cleanup(self):
        """Safely remove the item from the scene"""
        try:
            if self.region.scene() is not None:
                self.p_base.removeItem(self.region)
        except Exception:
            pass
