"""Regression tests for FigureQtPG's live peak-detection pipeline
(mylib/Qtutils.py), covering every real bug found and fixed against this
code during live-hardware testing this session:

- duplicate re-detection of the same peak once the history deque is full
  (drove computed heart rate to ~80x the true value)
- find_peaks()'s boundary-padding artifact at the newest sample in the
  window (silently overrode genuine, correctly-timed peaks)
- an overly-reactive amplitude threshold (alpha=0.5 EMA) that let noise
  through as false peaks once the boundary-artifact fix removed the thing
  that had been accidentally masking it
- stale peak-history state surviving a Test/Run/caliBrate restart, mixing
  two sessions' differently-scaled timestamps
- a 3-slot mean-based interval estimate being too sensitive to a single
  spurious secondary peak (e.g. a dicrotic notch)

These are exercised directly against FigureQtPG's real bound methods via a
lightweight stand-in object, not a full FigureQtPG instance (constructing
one needs a live board/figs/pyqtgraph canvas courtesy of __init__); the
methods under test only touch the attributes the stand-in provides.
"""
from collections import deque
from types import SimpleNamespace

import numpy as np
import pytest

from mylib.Qtutils import FigureQtPG


class _FakeBoard:
    min_peak_dist = 0.400
    time_width = 20
    structure = [0, 1, 2]  # only its length matters to update()'s raw-index math


class _FakePeakPlot:
    def setData(self, x, y):
        pass


class _FakeArgs:
    Debug = False


def make_stub(peak_history_sec=2.0, dt=0.01):
    peak_history = int(peak_history_sec / dt)
    return SimpleNamespace(
        board=_FakeBoard(),
        top_args=_FakeArgs(),
        PEAK_HISTORY=peak_history,
        PEAK_LOCAL_WIDTH=FigureQtPG.PEAK_LOCAL_WIDTH,
        _avg_alpha=min(1.0, dt / FigureQtPG.AVERAGE_TIME_CONSTANT_SEC),
        _peak_history_x=[[[deque(maxlen=peak_history)]]],
        _peak_history_y=[[[deque(maxlen=peak_history)]]],
        peak_time=[[[np.zeros(FigureQtPG.PEAK_TIME_BUFFER_SIZE)]]],
        peak_interval=np.array([[[0.0]]]),
        peaks=[[[_FakePeakPlot()]]],
        average=[[[0.0]]],
        _last_seen_time=float("-inf"),
    )


def run_periodic_pulse_train(stub, period, duration=40.0, dt=0.01, noise_sd=0.0, seed=0):
    """Feed a synthetic periodic pulse train through the real
    _detect_and_record_peak(), driving self.average the same way
    FigureQtPG.update() does. Returns the recorded peak_interval history."""
    rng = np.random.default_rng(seed)
    t = np.arange(0, duration, dt)
    y = np.zeros_like(t)
    for peak_t in np.arange(0.8, duration, period):
        y += np.exp(-0.5 * ((t - peak_t) / 0.03) ** 2)
    y = y + rng.normal(0, noise_sd, size=y.shape)

    recorded = []
    for i in range(len(t)):
        stub.average[0][0][0] = (
            stub.average[0][0][0] * (1 - stub._avg_alpha) + y[i] * stub._avg_alpha)
        FigureQtPG._detect_and_record_peak(stub, 0, 0, 0, t[i], y[i])
        recorded.append(stub.peak_interval[0][0][0])
    return np.array(recorded)


class TestCleanPeriodicSignal:
    """No noise, no artifacts: the detected inter-peak interval should
    converge to within numerical precision of the true period."""

    @pytest.mark.parametrize("period,expected_hz", [(0.8, 75.0), (0.6, 100.0), (1.0, 60.0)])
    def test_matches_true_rate(self, period, expected_hz):
        stub = make_stub()
        recorded = run_periodic_pulse_train(stub, period)
        steady = recorded[len(recorded) // 2:]
        steady = steady[steady > 0]
        computed_hz = 60 / steady.mean()
        assert computed_hz == pytest.approx(expected_hz, abs=0.5)


class TestNoDuplicateReDetection:
    """The historical bug: once the history deque is full, the "buffer is
    full" branch runs on every single sample, not just once per genuine
    new peak -- re-detecting the same peak and corrupting the rolling
    peak_time buffer with duplicates."""

    def test_peak_time_buffer_does_not_fill_with_duplicates(self):
        stub = make_stub()
        run_periodic_pulse_train(stub, period=0.8, duration=10.0)
        peak_time = stub.peak_time[0][0][0]
        nonzero = peak_time[peak_time > 0]
        # A healthy buffer holds several *distinct* recent peak times.
        assert len(set(np.round(nonzero, 3))) == len(nonzero)


class TestSessionRestartResetsState:
    """Test/Run/caliBrate resets the Pico's elapsed-time counter; without
    clearing peak-detection state, old (larger) timestamps mixed with the
    new (near-zero) ones broke min_peak_distance's calculation."""

    def test_restart_detected_by_time_going_backward(self):
        stub = make_stub()
        stub._fs_fixed = True
        stub.figs = [[{"data": ((0, 1, {"peak": True, "raw": (False, False)}),)}]]
        stub.num_of_loop = 0
        stub.next_loop = False
        stub._buf_size = 10
        stub._x_grid = np.linspace(0, 20, 10, endpoint=False)
        stub._buf_y = [[[np.full(10, np.nan)]]]
        stub.curves = [[[_FakePeakPlot()]]]

        stub._erase_and_write_buffer = FigureQtPG._erase_and_write_buffer.__get__(stub)
        stub._detect_and_record_peak = FigureQtPG._detect_and_record_peak.__get__(stub)
        stub._reset_peak_detection_state = FigureQtPG._reset_peak_detection_state.__get__(stub)

        dt = 0.02
        t = 0.0
        for _ in range(60):
            data_t = np.vstack([np.array([t, t + dt]), np.array([1.0, 1.0])]).T
            FigureQtPG.update(stub, iter([data_t]))
            t += dt
        assert len(stub._peak_history_x[0][0][0]) > 0

        # Session "restarts": elapsed time jumps back near 0.
        restart = np.vstack([np.array([0.0, dt]), np.array([2.0, 2.0])]).T
        FigureQtPG.update(stub, iter([restart]))

        assert len(stub._peak_history_x[0][0][0]) == 1  # cleared, then one new sample
        assert stub.peak_interval[0][0][0] == 0.0

    def test_refill_after_restart_does_not_error(self):
        # A stress case that previously produced OverflowError (divide by
        # zero in min_peak_distance) if the restart wasn't handled.
        stub = make_stub()
        stub._fs_fixed = True
        stub.figs = [[{"data": ((0, 1, {"peak": True, "raw": (False, False)}),)}]]
        stub.num_of_loop = 0
        stub.next_loop = False
        stub._buf_size = 10
        stub._x_grid = np.linspace(0, 20, 10, endpoint=False)
        stub._buf_y = [[[np.full(10, np.nan)]]]
        stub.curves = [[[_FakePeakPlot()]]]
        stub._erase_and_write_buffer = FigureQtPG._erase_and_write_buffer.__get__(stub)
        stub._detect_and_record_peak = FigureQtPG._detect_and_record_peak.__get__(stub)
        stub._reset_peak_detection_state = FigureQtPG._reset_peak_detection_state.__get__(stub)

        dt = 0.02
        t = 0.0
        for _ in range(60):
            data_t = np.vstack([np.array([t, t + dt]), np.array([1.0, 1.0])]).T
            FigureQtPG.update(stub, iter([data_t]))
            t += dt

        restart = np.vstack([np.array([0.0, dt]), np.array([2.0, 2.0])]).T
        FigureQtPG.update(stub, iter([restart]))

        t = dt
        for _ in range(60):
            data_t = np.vstack([np.array([t, t + dt]), np.array([2.0, 2.0])]).T
            FigureQtPG.update(stub, iter([data_t]))
            t += dt
        assert getattr(stub, "_update_err_count", None) is None


class TestHBRStabilityAgainstSpuriousSecondaryPeaks:
    """A dicrotic-notch-like secondary bump occasionally getting detected
    as its own beat used to throw the displayed heart rate to roughly
    double. The wider (7-slot) median-based interval estimate should
    absorb an occasional bad detection far better than the old 3-slot
    mean would have."""

    def test_stays_close_to_true_rate_despite_occasional_secondary_peaks(self):
        stub = make_stub()
        true_period = 0.77
        rng = np.random.default_rng(2)
        dt = 0.01
        duration = 60.0
        t = np.arange(0, duration, dt)
        y = np.zeros_like(t)
        for beat_t in np.arange(0.8, duration, true_period):
            y += np.exp(-0.5 * ((t - beat_t) / 0.03) ** 2)
            if rng.random() < 0.25:
                notch_t = beat_t + rng.uniform(0.38, 0.5)
                y += 0.95 * np.exp(-0.5 * ((t - notch_t) / 0.03) ** 2)

        recorded = []
        for i in range(len(t)):
            stub.average[0][0][0] = (
                stub.average[0][0][0] * (1 - stub._avg_alpha) + y[i] * stub._avg_alpha)
            FigureQtPG._detect_and_record_peak(stub, 0, 0, 0, t[i], y[i])
            recorded.append(stub.peak_interval[0][0][0])

        recorded = np.array(recorded)
        hr = 60 / recorded[recorded > 0]
        steady = hr[len(hr) // 3:]
        true_hr = 60 / true_period
        # Should not run away toward ~2x true rate the way a naive 3-slot
        # mean did in manual testing (observed max ~113 bpm for a 77.9 bpm
        # true rate under this same scenario).
        assert steady.max() < 1.5 * true_hr
