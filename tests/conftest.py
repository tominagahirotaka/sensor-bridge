"""Shared pytest fixtures.

Sets QT_QPA_PLATFORM=offscreen before any PyQt5/pyqtgraph import so the
whole suite (including get.py/plot.py's GUI-adjacent modules) can run
headless in CI with no display server.
"""
import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest  # noqa: E402


@pytest.fixture(scope="session")
def qapp():
    """A single QApplication for the whole test session (PyQt5 allows only one)."""
    from PyQt5.QtWidgets import QApplication

    app = QApplication.instance() or QApplication([])
    yield app
