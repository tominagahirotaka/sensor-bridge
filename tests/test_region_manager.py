"""Tests for RegionManager's "Full Range" toggle (mylib/plot_utils/plotting.py):
jumping the bottom overview plot's selected range to the full data extent
and back to whatever was selected before, repeatably."""
import numpy as np
import pyqtgraph as pg

from mylib.plot_utils.plotting import RegionManager


def make_region_manager(qapp):
    win = pg.GraphicsLayoutWidget()
    p_base = win.addPlot()
    x = np.linspace(0, 100, 1000)
    y = np.sin(x)
    plotted = p_base.plot(x, y)
    rm = RegionManager(p_base, plotted, plt=[])
    rm._set_initial_region()  # run the normally-deferred (QTimer.singleShot(0, ...)) call now
    # RegionManager.__init__ also scheduled that same call via singleShot(0, ...);
    # flush it here (harmless/idempotent) so it can't fire later, unpredictably,
    # against objects a subsequent test may have already torn down.
    qapp.processEvents()
    # Return `win` too and keep it referenced for the test's lifetime: pyqtgraph's
    # PlotItem/ViewBox C++ objects are owned by their containing widget, so if
    # `win` itself is garbage-collected while `rm` still references its children,
    # later calls raise "wrapped C/C++ object has been deleted" even though the
    # Python-side objects are still around (the same object-lifetime issue noted
    # elsewhere in this codebase).
    return win, rm


class TestInitialRegion:
    def test_defaults_to_70_percent_of_full_range(self, qapp):
        win, rm = make_region_manager(qapp)
        start, end = rm.region.getRegion()
        assert start == 0
        assert end == 70  # 70% of [0, 100]


class TestToggleFullRange:
    def test_first_toggle_expands_to_full_range(self, qapp):
        win, rm = make_region_manager(qapp)
        is_full = rm.toggle_full_range()
        assert is_full is True
        assert rm.region.getRegion() == (0, 100)

    def test_second_toggle_restores_the_original_region(self, qapp):
        win, rm = make_region_manager(qapp)
        original = rm.region.getRegion()
        rm.toggle_full_range()
        is_full = rm.toggle_full_range()
        assert is_full is False
        assert rm.region.getRegion() == original

    def test_repeated_toggling_keeps_alternating(self, qapp):
        win, rm = make_region_manager(qapp)
        states = [rm.toggle_full_range() for _ in range(4)]
        assert states == [True, False, True, False]

    def test_restores_a_manually_dragged_region_not_the_default(self, qapp):
        win, rm = make_region_manager(qapp)
        rm.region.setRegion([20, 40])  # user manually drags before ever toggling
        rm.toggle_full_range()          # saves [20, 40], expands to full
        assert rm.region.getRegion() == (0, 100)
        rm.toggle_full_range()          # restores exactly the dragged range
        assert rm.region.getRegion() == (20, 40)
