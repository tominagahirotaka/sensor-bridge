"""Tests for mylib/calibration.py: the per-unit absolute-time correction
lookup (see calibration.json's "_readme" entry for the ppm_offset sign
convention this exercises)."""
import json

import numpy as np
import pytest

import mylib.calibration as calib


@pytest.fixture
def calibration_file(tmp_path):
    path = tmp_path / 'calibration.json'
    path.write_text(json.dumps({
        'boards': {
            'AAAA1111': {'ppm_offset': 50.0},
            'BBBB2222': {'ppm_offset': -20.0},
        }
    }))
    return path


class TestLoadCalibration:
    def test_missing_file_returns_empty_dict(self, tmp_path):
        assert calib.load_calibration(tmp_path / 'nope.json') == {}

    def test_loads_ppm_offset_per_chip_id(self, calibration_file):
        loaded = calib.load_calibration(calibration_file)
        assert loaded == {'AAAA1111': 50.0, 'BBBB2222': -20.0}

    def test_file_with_no_boards_entry_returns_empty_dict(self, tmp_path):
        path = tmp_path / 'calibration.json'
        path.write_text(json.dumps({}))
        assert calib.load_calibration(path) == {}


class TestPpmOffsetFor:
    def test_known_chip_id_returns_its_offset(self, calibration_file):
        table = calib.load_calibration(calibration_file)
        assert calib.ppm_offset_for('AAAA1111', table) == 50.0

    def test_unknown_chip_id_returns_none(self, calibration_file):
        table = calib.load_calibration(calibration_file)
        assert calib.ppm_offset_for('FFFFFFFF', table) is None

    def test_none_chip_id_returns_none_without_looking_up(self, calibration_file):
        # Recordings made before the unique-ID handshake field existed
        # (or with older firmware) have chip_id=None; this must not be
        # treated as a dict key lookup.
        table = calib.load_calibration(calibration_file)
        assert calib.ppm_offset_for(None, table) is None


class TestApplyTimeCorrection:
    def test_none_offset_is_a_no_op(self):
        t = np.array([1.0, 2.0, 3.0])
        assert calib.apply_time_correction(t, None) is t

    def test_positive_offset_shrinks_reported_time(self):
        # Device clock runs 100 ppm fast (reports more elapsed time than
        # actually passed) -> corrected time is smaller than raw.
        t = np.array([10.0])
        corrected = calib.apply_time_correction(t, 100.0)
        assert corrected[0] == pytest.approx(10.0 / 1.0001)

    def test_negative_offset_grows_reported_time(self):
        t = np.array([10.0])
        corrected = calib.apply_time_correction(t, -100.0)
        assert corrected[0] == pytest.approx(10.0 / 0.9999)

    def test_zero_offset_leaves_values_unchanged(self):
        t = np.array([1.0, 2.0, 3.0])
        corrected = calib.apply_time_correction(t, 0.0)
        np.testing.assert_array_equal(corrected, t)
