"""Tests for SignalSmoothingWindow's Load/Save Parameters buttons
(mylib/plot_utils/smoothing_gui.py). Regression coverage for bugs found
when these had never actually been exercised: a cancelled file dialog
crashed with an uncaught FileNotFoundError, Save had no dialog at all
(always overwrote a hardcoded "history.json"), and loading a history
file saved from a recording with a different channel count crashed
apply_history() with an IndexError instead of skipping the entries that
don't apply."""
import json

import numpy as np
import pyqtgraph as pg
import pytest
from PyQt5.QtWidgets import QFileDialog, QMessageBox

from mylib.plot_utils.reading import PlotData
from mylib.plot_utils.smoothing_gui import SignalSmoothingWindow


def make_window(qapp, n_channels=1):
    data = PlotData()
    data.xlabel = {'bottom': ('time', 's')}
    t = np.linspace(0, 1, 100)
    for i in range(n_channels):
        y = np.sin(2 * np.pi * (i + 1) * t)
        data.add_series(t, y, label={'left': (f'ch{i}', 'V')})
    plts = [pg.PlotItem() for _ in range(n_channels)]
    return SignalSmoothingWindow(plts, data, [])


class TestLoadParameters:
    def test_cancelled_dialog_does_not_crash(self, qapp, monkeypatch):
        win = make_window(qapp)
        monkeypatch.setattr(QFileDialog, 'getOpenFileName', staticmethod(lambda *a, **k: ('', '')))
        win.load_parameters()  # must not raise

    def test_round_trips_a_saved_history(self, qapp, monkeypatch, tmp_path):
        path = tmp_path / 'history.json'
        path.write_text(json.dumps({"0": [["MA", [5]]]}))

        win = make_window(qapp)
        monkeypatch.setattr(QFileDialog, 'getOpenFileName',
                            staticmethod(lambda *a, **k: (str(path), '')))
        win.load_parameters()

        assert win.history == {0: [["MA", [5]]]}

    def test_out_of_range_channel_is_skipped_not_crashed(self, qapp, monkeypatch, tmp_path):
        # Saved from a recording with 6 channels; loaded into one with 1.
        path = tmp_path / 'mismatch.json'
        path.write_text(json.dumps({"0": [], "5": [["MA", [3]]]}))

        win = make_window(qapp, n_channels=1)
        monkeypatch.setattr(QFileDialog, 'getOpenFileName',
                            staticmethod(lambda *a, **k: (str(path), '')))
        monkeypatch.setattr(QMessageBox, 'warning', staticmethod(lambda *a, **k: None))
        win.load_parameters()  # must not raise IndexError

        assert win.history == {0: []}

    def test_malformed_json_shows_a_warning_not_a_crash(self, qapp, monkeypatch, tmp_path):
        path = tmp_path / 'bad.json'
        path.write_text('{not valid json')

        win = make_window(qapp)
        monkeypatch.setattr(QFileDialog, 'getOpenFileName',
                            staticmethod(lambda *a, **k: (str(path), '')))
        warned = []
        monkeypatch.setattr(QMessageBox, 'warning',
                            staticmethod(lambda *a, **k: warned.append(True)))
        win.load_parameters()  # must not raise

        assert warned


class TestSaveParameters:
    def test_cancelled_dialog_does_not_crash_or_write(self, qapp, monkeypatch, tmp_path):
        win = make_window(qapp)
        monkeypatch.setattr(QFileDialog, 'getSaveFileName', staticmethod(lambda *a, **k: ('', '')))
        win.save_parameters()  # must not raise
        assert list(tmp_path.iterdir()) == []

    def test_saves_to_the_chosen_path(self, qapp, monkeypatch, tmp_path):
        path = tmp_path / 'my_history.json'
        win = make_window(qapp)
        win.history[0] = [["MA", [5]]]
        monkeypatch.setattr(QFileDialog, 'getSaveFileName',
                            staticmethod(lambda *a, **k: (str(path), '')))
        win.save_parameters()

        assert json.loads(path.read_text()) == {"0": [["MA", [5]]]}
