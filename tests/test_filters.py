"""Tests for mylib/plot_utils/filters.py: SignalFilter's individual filter
methods, the apply()/apply_default_filters() pipelines, and the checkpoint
('mark') substitution used by trim filters."""
import numpy as np
import pytest
import scipy.signal as scisig

from mylib.plot_utils.filters import (
    SignalFilter, apply_default_filters, apply_filters, resolve_filter_params)


def make_signal(n=1000, fs=100.0):
    t = np.arange(n) / fs
    y = np.sin(2 * np.pi * 2 * t) + 0.3 * np.sin(2 * np.pi * 20 * t)
    return t, y


class TestSignalFilterProperties:
    def test_fs_and_nyquist(self):
        t, y = make_signal(fs=100.0)
        sf = SignalFilter((t, y))
        assert sf.fs == pytest.approx(100.0)
        assert sf.nyq == pytest.approx(50.0)


class TestTrim:
    def test_trim_range(self):
        t, y = make_signal()
        sf = SignalFilter((t.copy(), y.copy())).trim(2.0, 8.0)
        assert sf.t[0] >= 2.0
        assert sf.t[-1] <= 8.0

    def test_trim_reset_t0(self):
        t, y = make_signal()
        sf = SignalFilter((t.copy(), y.copy())).trim(2.0, 8.0, reset_t0=True)
        assert sf.t[0] == pytest.approx(0.0, abs=1e-9)


class TestLowpass:
    def test_matches_manual_scipy_filtfilt(self):
        t, y = make_signal()
        sf = SignalFilter((t.copy(), y.copy())).lowpass(5.0)
        b, a = scisig.butter(4, 5.0 / 50.0, btype="low")
        expected = scisig.filtfilt(b, a, y)
        assert np.allclose(sf.y, expected)

    def test_out_of_range_cutoff_raises(self):
        t, y = make_signal()
        with pytest.raises(ValueError):
            SignalFilter((t, y)).lowpass(999.0)


class TestApplyPipeline:
    def test_apply_matches_chained_manual_calls(self):
        t, y = make_signal()
        history = [["TR", [1.0, 9.0, True]], ["LP", [10]], ["MA", [5]]]
        piped = SignalFilter((t.copy(), y.copy())).apply(history)
        manual = (
            SignalFilter((t.copy(), y.copy()))
            .trim(1.0, 9.0, True)
            .lowpass(10)
            .moving_average(5)
        )
        assert np.allclose(piped.y, manual.y)
        assert np.allclose(piped.t, manual.t)

    def test_unsupported_method_is_skipped_not_raised(self, capsys):
        t, y = make_signal()
        sf = SignalFilter((t.copy(), y.copy())).apply([["ZZ", []]])
        assert np.array_equal(sf.y, y)  # untouched


class TestResolveFilterParams:
    def test_mark_substitution_uses_checkpoint_time(self):
        history = [["TR", [{"mark": 0}, None, True]]]
        resolved = resolve_filter_params(history, cpt_lst=[3.5, 7.2])
        assert resolved[0][1][0] == 3.5

    def test_empty_checkpoint_list_falls_back_to_zero(self):
        history = [["TR", [{"mark": 0}, None, True]]]
        resolved = resolve_filter_params(history, cpt_lst=[])
        assert resolved[0][1][0] == 0.0

    def test_out_of_range_mark_index_falls_back_to_last_checkpoint(self):
        history = [["TR", [{"mark": 5}, None, True]]]
        resolved = resolve_filter_params(history, cpt_lst=[1.0, 2.0])
        assert resolved[0][1][0] == 2.0


class TestApplyDefaultFilters:
    def test_list_form_applies_same_filter_to_every_channel(self):
        t, y = make_signal()
        data_list = [(t.copy(), y.copy()), (t.copy(), y.copy() * 2)]
        history, filtered = apply_default_filters(data_list, [["LP", [10]]], cpt_lst=[])
        assert history[0] == history[1]
        expected = SignalFilter((t.copy(), y.copy())).lowpass(10).y
        assert np.allclose(filtered[0][1], expected)

    def test_dict_form_applies_per_channel(self):
        t, y = make_signal()
        data_list = [(t.copy(), y.copy()), (t.copy(), y.copy())]
        default_filter = {"0": [["LP", [10]]], "1": []}
        history, filtered = apply_default_filters(data_list, default_filter, cpt_lst=[])
        assert not np.allclose(filtered[0][1], y)  # channel 0 filtered
        assert np.allclose(filtered[1][1], y)       # channel 1 untouched

    def test_no_default_filter_leaves_data_untouched(self):
        t, y = make_signal()
        data_list = [(t.copy(), y.copy())]
        history, filtered = apply_default_filters(data_list, None, cpt_lst=[])
        assert history == {0: []}
        assert np.array_equal(filtered[0][1], y)


class TestApplyFilters:
    def test_apply_filters_resolves_marks_then_runs_pipeline(self):
        t, y = make_signal()
        history = [["TR", [{"mark": 0}, None, False]]]
        t_out, y_out = apply_filters((t.copy(), y.copy()), history, cpt_lst=[2.0])
        assert t_out[0] >= 2.0
