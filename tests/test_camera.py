"""Tests for mylib/camera.py: the frame/timestamp bookkeeping in
CameraCapture, and list_cameras()'s index-probing loop. Mocks cv2's
VideoCapture/VideoWriter so these run without a real camera, consistent
with the rest of the test suite (no hardware needed) -- skipped entirely
if opencv isn't installed, since get_camera.py is an optional companion
script, not a get.py/plot.py dependency (see requirements-camera.txt)."""
import csv

import numpy as np
import pytest

cv2 = pytest.importorskip("cv2")

import mylib.camera as camera


class _FakeVideoCapture:
    """Only "camera 0" exists; every other index fails to open, mirroring
    what a real backend does when probing indices with nothing attached."""

    def __init__(self, index):
        self.index = index
        self._opened = index == 0

    def isOpened(self):
        return self._opened

    def get(self, prop):
        return {
            cv2.CAP_PROP_FRAME_WIDTH: 640,
            cv2.CAP_PROP_FRAME_HEIGHT: 480,
            cv2.CAP_PROP_FPS: 30.0,
        }.get(prop, 0)

    def read(self):
        if not self._opened:
            return False, None
        return True, np.zeros((480, 640, 3), dtype='uint8')

    def release(self):
        self._opened = False


class _FakeVideoWriter:
    def __init__(self, path, fourcc, fps, size):
        self.path = path
        self.frames_written = 0

    def write(self, frame):
        self.frames_written += 1

    def release(self):
        pass


class TestListCameras:
    def test_finds_only_openable_indices(self, monkeypatch):
        monkeypatch.setattr(cv2, "VideoCapture", _FakeVideoCapture)
        assert camera.list_cameras(max_index=3) == [0]


class TestCameraCapture:
    def test_read_frame_returns_a_frame(self, monkeypatch):
        monkeypatch.setattr(cv2, "VideoCapture", _FakeVideoCapture)
        cap = camera.CameraCapture(0)
        frame = cap.read_frame()
        assert frame is not None
        assert frame.shape == (480, 640, 3)

    def test_opening_a_camera_that_fails_to_open_raises(self, monkeypatch):
        monkeypatch.setattr(cv2, "VideoCapture", _FakeVideoCapture)
        with pytest.raises(RuntimeError):
            camera.CameraCapture(1)

    def test_write_frame_before_recording_is_a_noop(self, monkeypatch):
        monkeypatch.setattr(cv2, "VideoCapture", _FakeVideoCapture)
        cap = camera.CameraCapture(0)
        cap.write_frame(cap.read_frame())
        assert cap.timestamps == []
        assert not cap.is_recording()

    def test_recording_writes_one_timestamp_row_per_frame(self, monkeypatch, tmp_path):
        monkeypatch.setattr(cv2, "VideoCapture", _FakeVideoCapture)
        monkeypatch.setattr(cv2, "VideoWriter", _FakeVideoWriter)
        cap = camera.CameraCapture(0)
        cap.start_recording(str(tmp_path), "testhost")
        assert cap.is_recording()
        for _ in range(5):
            cap.write_frame(cap.read_frame())
        assert len(cap.timestamps) == 5

        csv_path = cap.stop_recording()
        assert not cap.is_recording()

        with open(csv_path, newline='') as f:
            rows = list(csv.reader(f))
        assert rows[0] == ['frame_index', 'elapsed_sec_host', 'wall_clock_iso']
        assert [r[0] for r in rows[1:]] == ['0', '1', '2', '3', '4']

    def test_stop_recording_without_starting_is_a_noop(self, monkeypatch):
        monkeypatch.setattr(cv2, "VideoCapture", _FakeVideoCapture)
        cap = camera.CameraCapture(0)
        assert cap.stop_recording() is None
