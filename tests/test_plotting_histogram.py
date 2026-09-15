"""Tests for mylib/plot_utils/plotting.py's time-interval histogram: the
outlier-percentile-clip fix (rare large gaps, e.g. from checkpoint marks,
used to stretch the axis so the real data collapsed into one needle-thin
bin) and the auto_bins()/get_optimal_bins() bin-count safety caps (an
unbounded formula could try to allocate hundreds of GB for near-uniform
timing data)."""
import numpy as np
import pyqtgraph as pg

from mylib.plot_utils.plotting import (
    MAX_AUTO_BINS, auto_bins, get_optimal_bins, plot_timeinterval_histogram)


def make_regular_timestamps_with_outliers(n=5000, interval=0.01, n_outliers=4, seed=0):
    rng = np.random.default_rng(seed)
    t = np.cumsum(np.full(n, interval) + rng.normal(0, 1e-5, n))
    gap_idx = rng.choice(n - 1, n_outliers, replace=False)
    for i in gap_idx:
        t[i:] += rng.uniform(0.2, 0.8)
    return t


class TestAutoBins:
    def test_returns_ten_for_degenerate_zero_iqr_data(self):
        assert auto_bins(np.zeros(100)) == 10

    def test_never_exceeds_max_auto_bins(self):
        # Near-uniform data with a tiny IQR historically produced billions
        # of bins via the raw Freedman-Diaconis formula.
        rng = np.random.default_rng(1)
        data = np.full(10000, 1.0) + rng.normal(0, 1e-12, 10000)
        assert auto_bins(data) <= MAX_AUTO_BINS

    def test_at_least_ten_bins_for_real_data(self):
        rng = np.random.default_rng(2)
        data = rng.normal(0, 1, 1000)
        assert auto_bins(data) >= 10


class TestGetOptimalBins:
    def test_returns_ten_for_degenerate_zero_std_data(self):
        assert get_optimal_bins(np.zeros(100)) == 10

    def test_never_exceeds_max_auto_bins(self):
        rng = np.random.default_rng(3)
        data = np.full(10000, 1.0) + rng.normal(0, 1e-12, 10000)
        assert get_optimal_bins(data) <= MAX_AUTO_BINS


class TestPlotTimeintervalHistogram:
    def test_outliers_do_not_collapse_real_data_into_one_bin(self, qapp):
        """Regression test: a handful of rare large gaps (checkpoint marks)
        used to stretch axis range so far that ~99.9% of samples landed in
        a single bin spanning ~0.1% of the plotted width. Percentile-
        clipping the binning range should keep the dominant bin's share of
        the axis width well above that."""
        t = make_regular_timestamps_with_outliers()
        win = pg.GraphicsLayoutWidget()
        plt = plot_timeinterval_histogram(win, t)
        curve = plt.listDataItems()[0]
        x = curve.xData
        y = curve.yData
        bin_width = x[1] - x[0]
        axis_span = x[-1] - x[0]
        peak_bin_frac_of_axis = bin_width / axis_span
        assert peak_bin_frac_of_axis > 0.01, (
            "dominant bin occupies too little of the axis width; "
            "outlier clipping regressed")

    def test_total_count_preserved_outliers_included(self, qapp):
        t = make_regular_timestamps_with_outliers(n=2000, n_outliers=3)
        win = pg.GraphicsLayoutWidget()
        plt = plot_timeinterval_histogram(win, t)
        curve = plt.listDataItems()[0]
        assert curve.yData.sum() == len(t) - 1  # every diff counted once

    def test_no_outliers_case_unaffected(self, qapp):
        rng = np.random.default_rng(4)
        t = np.cumsum(np.full(1000, 0.01) + rng.normal(0, 1e-4, 1000))
        win = pg.GraphicsLayoutWidget()
        plt = plot_timeinterval_histogram(win, t)
        curve = plt.listDataItems()[0]
        assert curve.yData.sum() == len(t) - 1

    def test_degenerate_constant_interval_does_not_crash(self, qapp):
        t = np.arange(100) * 0.01  # perfectly constant -> hi<=lo fallback path
        win = pg.GraphicsLayoutWidget()
        plt = plot_timeinterval_histogram(win, t)
        curve = plt.listDataItems()[0]
        assert curve.yData.sum() == len(t) - 1

    def test_bars_are_drawn_in_red_for_visibility(self, qapp):
        t = make_regular_timestamps_with_outliers(n=500, n_outliers=1)
        win = pg.GraphicsLayoutWidget()
        plt = plot_timeinterval_histogram(win, t)
        curve = plt.listDataItems()[0]
        assert curve.opts["fillBrush"][:3] == (255, 0, 0)
        pen = curve.opts["pen"]
        pen_rgb = pen if isinstance(pen, tuple) else pen.color().getRgb()[:3]
        assert pen_rgb[:3] == (150, 0, 0)
