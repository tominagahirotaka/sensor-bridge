"""Tests for WaveletParamWindow (mylib/plot_utils/smoothing_gui.py): the
in-window editor for the continuous-wavelet-transform parameters, added
so range/omega0 no longer require relaunching plot.py with different
--wlrange/--wlomega0 flags."""
import json

import pytest
from PyQt5.QtWidgets import QFileDialog, QMessageBox

from mylib.plot_utils.smoothing_gui import WaveletParamWindow
from mylib.plot_utils.wavelet import WaveletParams


class TestInitialValues:
    def test_spin_boxes_reflect_the_given_params(self, qapp):
        params = WaveletParams(range=[1.2, 3.0, 0.01], omega0=6, data_skip=4)
        win = WaveletParamWindow(params)
        assert win.range_min.value() == pytest.approx(1.2)
        assert win.range_max.value() == pytest.approx(3.0)
        assert win.range_step.value() == pytest.approx(0.01)
        assert win.omega0.value() == pytest.approx(6)
        assert win.data_skip.value() == 4


class TestApply:
    def test_apply_emits_a_waveletparams_with_the_edited_values(self, qapp):
        win = WaveletParamWindow(WaveletParams())
        win.range_min.setValue(1.0)
        win.range_max.setValue(2.0)
        win.range_step.setValue(0.05)
        win.omega0.setValue(8)
        win.data_skip.setValue(3)

        received = []
        win.execTriggered.connect(lambda p: received.append(p))
        win.on_apply()

        assert len(received) == 1
        params = received[0]
        assert isinstance(params, WaveletParams)
        assert params.range == [1.0, 2.0, 0.05]
        assert params.omega0 == 8
        assert params.data_skip == 3

    def test_invalid_range_shows_a_warning_and_does_not_emit(self, qapp, monkeypatch):
        win = WaveletParamWindow(WaveletParams())
        win.range_min.setValue(5.0)
        win.range_max.setValue(1.0)  # min >= max -> WaveletParams.__post_init__ raises

        warned = []
        monkeypatch.setattr(QMessageBox, 'warning', staticmethod(lambda *a, **k: warned.append(True)))
        received = []
        win.execTriggered.connect(lambda p: received.append(p))
        win.on_apply()

        assert warned
        assert received == []


class TestSaveParameters:
    def test_cancelled_dialog_does_not_crash_or_write(self, qapp, monkeypatch, tmp_path):
        win = WaveletParamWindow(WaveletParams())
        monkeypatch.setattr(QFileDialog, 'getSaveFileName', staticmethod(lambda *a, **k: ('', '')))
        win.save_parameters()  # must not raise
        assert list(tmp_path.iterdir()) == []

    def test_saves_the_current_values(self, qapp, monkeypatch, tmp_path):
        path = tmp_path / 'wavelet_params.json'
        win = WaveletParamWindow(WaveletParams(range=[1.0, 2.0, 0.1], omega0=5))
        monkeypatch.setattr(QFileDialog, 'getSaveFileName',
                            staticmethod(lambda *a, **k: (str(path), '')))
        win.save_parameters()

        saved = json.loads(path.read_text())
        assert saved == {'range': [1.0, 2.0, 0.1], 'omega0': 5, 'data_skip': 1}


class TestLoadParameters:
    def test_cancelled_dialog_does_not_crash(self, qapp, monkeypatch):
        win = WaveletParamWindow(WaveletParams())
        monkeypatch.setattr(QFileDialog, 'getOpenFileName', staticmethod(lambda *a, **k: ('', '')))
        win.load_parameters()  # must not raise

    def test_loads_and_updates_the_spin_boxes(self, qapp, monkeypatch, tmp_path):
        path = tmp_path / 'wavelet_params.json'
        path.write_text(json.dumps({'range': [2.0, 4.0, 0.02], 'omega0': 7, 'data_skip': 5}))

        win = WaveletParamWindow(WaveletParams())
        monkeypatch.setattr(QFileDialog, 'getOpenFileName',
                            staticmethod(lambda *a, **k: (str(path), '')))
        win.load_parameters()

        assert win.range_min.value() == pytest.approx(2.0)
        assert win.range_max.value() == pytest.approx(4.0)
        assert win.range_step.value() == pytest.approx(0.02)
        assert win.omega0.value() == pytest.approx(7)
        assert win.data_skip.value() == 5

    def test_malformed_json_shows_a_warning_not_a_crash(self, qapp, monkeypatch, tmp_path):
        path = tmp_path / 'bad.json'
        path.write_text('{not valid json')

        win = WaveletParamWindow(WaveletParams())
        monkeypatch.setattr(QFileDialog, 'getOpenFileName',
                            staticmethod(lambda *a, **k: (str(path), '')))
        warned = []
        monkeypatch.setattr(QMessageBox, 'warning',
                            staticmethod(lambda *a, **k: warned.append(True)))
        win.load_parameters()  # must not raise

        assert warned
