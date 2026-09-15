"""Tests for mylib/utils.py: the board 'struct' mini-language, age/heart-rate
helpers, and the peak-finding primitive used by the live-acquisition GUI."""
import datetime

import numpy as np
import pytest

import mylib.utils as utils


class TestJoinDict:
    def test_join_dict_basic(self):
        assert utils.join_dict({"a": 1, "b": "x"}, ";", "=") == "a=1;b=x"

    def test_join_dict_empty(self):
        assert utils.join_dict({}, ";", "=") == ""


class TestStructMiniLanguage:
    """Real struct strings captured from live LIS3DH/DPG_X95840W hardware handshakes."""

    def test_repeat_interpret_single_channel(self):
        # LIS3DH: time + 3 plain (non-repeated) fields.
        tokens = utils.repeat_interpret(
            "time(u4:func0), x(u2:func1), y(u2:func1), z(u2:func1)")
        assert tokens == [
            "time(u4:func0)", "x(u2:func1)", "y(u2:func1)", "z(u2:func1)"]

    def test_repeat_interpret_indexed_repeat_group(self):
        # DPG_X95840W: time + one repeated 'port' field per detected channel.
        tokens = utils.repeat_interpret(
            "time(u4:func0), [(0,1,2)]port(u2:func1)")
        assert tokens == [
            "time(u4:func0)", "port(u2:func1)0", "port(u2:func1)1", "port(u2:func1)2"]

    def test_content_process_label(self):
        assert utils.content_process("port(u2:func1)0", kind="label") == ("port", "0")
        assert utils.content_process("time(u4:func0)", kind="label") == ("time", "")

    def test_content_process_byte(self):
        assert utils.content_process("port(u2:func1)0", kind="byte") == 2
        assert utils.content_process("time(u4:func0)", kind="byte") == 4

    def test_content_process_func(self):
        assert utils.content_process("port(u2:func1)0", kind="func") == 1
        assert utils.content_process("time(u4:func0)", kind="func") == 0

    def test_make_struct_list(self):
        tokens = ["time(u4:func0)", "port(u2:func1)0", "port(u2:func1)1", "port(u2:func1)2"]
        assert utils.make_struct_list(tokens) == [
            [("time", ""), (0, 4), 0],
            [("port", "0"), (4, 6), 1],
            [("port", "1"), (6, 8), 1],
            [("port", "2"), (8, 10), 1],
        ]


class TestAge:
    def test_calc_age_before_birthday_this_year(self):
        # Born 2000/06/15, "today" is 2026/01/01 -> not yet had this year's birthday.
        assert utils.calc_age("2000/06/15", datetime.datetime(2026, 1, 1)) == 25

    def test_calc_age_after_birthday_this_year(self):
        assert utils.calc_age("2000/06/15", datetime.datetime(2026, 12, 31)) == 26

    def test_calc_age_invalid_birthday_returns_zero(self):
        # QDateEdit's untouched default / a blank field must not raise.
        assert utils.calc_age("", datetime.datetime(2026, 1, 1)) == 0
        assert utils.calc_age("not-a-date", datetime.datetime(2026, 1, 1)) == 0


class TestCalbonenTargetAge:
    def test_with_numeric_resting_heart_rate(self):
        # Karvonen formula: (220 - age - HR) * strength/100 + HR
        result = utils.calc_target_Calbonen_age(age=25, resting_heart_rate=60, strength=70)
        assert result == pytest.approx((220 - 25 - 60) * 0.70 + 60)

    def test_with_none_resting_heart_rate_falls_back_to_zero(self):
        # average_heart_rate() returns 0 (not None) for exactly this reason;
        # verify the consumer side tolerates it too.
        result = utils.calc_target_Calbonen_age(age=25, resting_heart_rate=None, strength=70)
        assert result == pytest.approx((220 - 25 - 0) * 0.70 + 0)

    def test_with_non_numeric_resting_heart_rate_falls_back_to_zero(self):
        result = utils.calc_target_Calbonen_age(age=25, resting_heart_rate="", strength=70)
        assert result == pytest.approx((220 - 25) * 0.70)


class TestAverageHeartRate:
    def test_all_numeric_rows(self):
        blood_p = [[None, "sys", "dia", "70"], [None, "sys", "dia", "80"]]
        assert utils.average_heart_rate(blood_p) == 75

    def test_no_numeric_rows_returns_zero_not_none(self):
        # A blank subject-dialog field must not propagate NaN/None downstream
        # (this is what broke get.py's live "{heart_rate:.0f}" formatting earlier).
        blood_p = [[None, "sys", "dia", ""]]
        assert utils.average_heart_rate(blood_p) == 0

    def test_empty_list_returns_zero(self):
        assert utils.average_heart_rate([]) == 0


class TestFindPeaks:
    def test_finds_isolated_positive_peak(self):
        a = np.array([0.0, 0.0, 5.0, 0.0, 0.0])
        idxs = utils.find_peaks(a, amp_thre=1.0, local_width=1, min_peak_distance=1)
        assert list(idxs) == [2]

    def test_finds_isolated_negative_peak(self):
        a = np.array([0.0, 0.0, -5.0, 0.0, 0.0])
        idxs = utils.find_peaks(a, amp_thre=1.0, local_width=1, min_peak_distance=1)
        assert list(idxs) == [2]

    def test_amplitude_threshold_filters_small_peaks(self):
        a = np.array([0.0, 0.5, 0.0, 5.0, 0.0])
        idxs = utils.find_peaks(a, amp_thre=1.0, local_width=1, min_peak_distance=1)
        assert list(idxs) == [3]

    def test_min_peak_distance_rejects_close_same_sign_peaks(self):
        # Two positive peaks only 2 samples apart; min_peak_distance=5 should
        # keep only the first one. Both peaks are placed well past index 0,
        # since find_peaks tracks "distance since the last accepted peak"
        # starting from index 0 -- a peak too close to the array start would
        # be rejected on that basis alone, independent of this test's intent.
        a = np.zeros(20)
        a[10] = 5.0
        a[12] = 5.0
        idxs = utils.find_peaks(a, amp_thre=1.0, local_width=1, min_peak_distance=5)
        assert list(idxs) == [10]

    def test_no_peaks_in_flat_signal(self):
        a = np.zeros(10)
        idxs = utils.find_peaks(a, amp_thre=1.0, local_width=1, min_peak_distance=1)
        assert len(idxs) == 0
