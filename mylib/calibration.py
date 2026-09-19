#!/usr/bin/env python3
"""Optional per-unit absolute-time calibration, keyed by each board's
factory-burned unique ID (see communicate.py's open_serial()).

See calibration.json at the repo root for the file format, the
ppm_offset sign convention, and how to actually measure a ppm_offset for
one physical board (a one-time comparison against an external time
reference -- this is a per-unit measurement, not a general property of
the board type; see README.md's timing-precision discussion for why).
"""
import json
import os

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CALIBRATION_PATH = os.path.join(REPO_ROOT, 'calibration.json')


def load_calibration(path=CALIBRATION_PATH):
    """Return {chip_id: ppm_offset}. Empty if calibration.json is
    missing or has no entries yet -- calibration is opt-in per board."""
    if not os.path.isfile(path):
        return {}
    with open(path, encoding='utf-8') as f:
        data = json.load(f)
    return {chip_id: entry['ppm_offset'] for chip_id, entry in data.get('boards', {}).items()}


def ppm_offset_for(chip_id, calibration=None):
    """None if this board has no calibration entry -- including when
    chip_id itself is None (data recorded before the unique-ID handshake
    field existed, or an older firmware build)."""
    if chip_id is None:
        return None
    if calibration is None:
        calibration = load_calibration()
    return calibration.get(chip_id)


def apply_time_correction(t, ppm_offset):
    """t: array-like of device-reported elapsed-time values. See
    calibration.json's "_readme" entry for the ppm_offset sign
    convention. A no-op (returns t unchanged) if ppm_offset is None."""
    if ppm_offset is None:
        return t
    return t / (1.0 + ppm_offset / 1e6)
