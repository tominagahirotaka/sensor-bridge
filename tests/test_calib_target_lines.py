"""Tests for FigureQtPG._calib_target_half_width(): the +-half-width (in
volts) of the calibration target-amplitude reference lines drawn on each
port's plot during caliBrate (see mylib/Qtutils.py's _init_fig()/update()),
requested so convergence can be judged directly against the graph instead
of only from the numeric dpm/HBR readout."""
from mylib.Qtutils import FigureQtPG


class TestCalibTargetHalfWidth:
    def test_converts_percentage_of_full_scale_to_volts(self):
        # 10% of a 5V supply's full-scale swing -> 0.5V peak-to-peak,
        # so +-0.25V around the trace's rolling average.
        assert FigureQtPG._calib_target_half_width((10, 20, 30), 5.0, 0) == 0.25

    def test_uses_the_right_channel_index(self):
        assert FigureQtPG._calib_target_half_width((10, 20, 30), 5.0, 2) == 0.75

    def test_out_of_range_index_returns_none(self):
        assert FigureQtPG._calib_target_half_width((10, 20, 30), 5.0, 5) is None

    def test_non_numeric_volt_returns_none_instead_of_raising(self):
        # A board without a usable calib_amplitude_max/volt (or a
        # malformed one) must not crash figure setup -- just skip the
        # reference lines for that port.
        assert FigureQtPG._calib_target_half_width((10, 20, 30), 'n/a', 0) is None
