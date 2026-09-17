#!/usr/bin/env python3
"""USB webcam capture for get_camera.py: device enumeration and a small
recorder that pairs an MP4 video with a per-frame host-side timestamp CSV.

Unlike the Pico sensor boards, a webcam has no device-side clock get.py can
read -- each frame's timestamp here is stamped by the host at the moment
OpenCV hands it back, so it carries the same PC-side scheduling/USB jitter
that sensor-bridge's device-side timestamping (see mylib/communicate.py)
exists specifically to avoid for sensor data. Treat this module's timing as
useful for a rough visual record, not as a precise synchronization signal
against sensor recordings.
"""

import csv
import datetime
import os
import time

import cv2


def list_cameras(max_index=8):
    """Return the indices of cameras that can actually be opened, by
    probing 0..max_index-1 (OpenCV/the OS give no direct enumeration API
    that works identically across platforms). Probing an index with no
    camera logs a harmless backend warning to stderr for each miss --
    expected, not diagnostic of anything wrong."""
    found = []
    for i in range(max_index):
        cap = cv2.VideoCapture(i)
        if cap.isOpened():
            found.append(i)
        cap.release()
    return found


class CameraCapture:
    def __init__(self, index=0):
        self.index = index
        self.cap = cv2.VideoCapture(index)
        if not self.cap.isOpened():
            # A common cause: a single USB camera (e.g. many UVC webcams)
            # exposes more than one /dev/videoN node -- one for the real
            # video stream, one or more for metadata-only that OpenCV
            # can't open as a camera. So with two physical cameras
            # connected, indices don't necessarily run 0, 1, 2, 3 as
            # "camera 1, camera 2, camera 3, camera 4"; they might be
            # 0, 2 (or similar) once the unopenable metadata nodes are
            # skipped. `--list` (see list_cameras() below) reports only
            # the indices that actually open, which is what -c should be
            # given -- not a raw sequential guess.
            raise RuntimeError(
                f'Could not open camera index {index}. If you have more '
                f'than one camera connected, note that indices are not '
                f'necessarily sequential per camera (a single USB webcam '
                f'can expose more than one /dev/videoN node); run '
                f'`python get_camera.py --list` to see which indices '
                f'actually open, and use one of those.')
        self.writer = None
        self.timestamps = []
        self.start_time = None
        self.dir_name = None
        self.base_name = None

    def frame_size(self):
        return (int(self.cap.get(cv2.CAP_PROP_FRAME_WIDTH)),
                int(self.cap.get(cv2.CAP_PROP_FRAME_HEIGHT)))

    def read_frame(self):
        """Grab one frame (BGR numpy array) or None if the read failed."""
        ok, frame = self.cap.read()
        return frame if ok else None

    def start_recording(self, dir_name, node_name, fourcc='mp4v', fps=None):
        os.makedirs(dir_name, exist_ok=True)
        fps = fps or self.cap.get(cv2.CAP_PROP_FPS) or 30.0
        w, h = self.frame_size()
        format_time = "{:%Y%m%d_%H%M%S}".format(datetime.datetime.now())
        self.base_name = f'{node_name}_{format_time}'
        self.dir_name = dir_name
        video_path = os.path.join(dir_name, self.base_name + '.mp4')
        self.writer = cv2.VideoWriter(video_path, cv2.VideoWriter_fourcc(*fourcc), fps, (w, h))
        self.timestamps = []
        self.start_time = time.monotonic()

    def write_frame(self, frame):
        if self.writer is None:
            return
        self.writer.write(frame)
        self.timestamps.append((len(self.timestamps),
                                 time.monotonic() - self.start_time,
                                 datetime.datetime.now().isoformat()))

    def is_recording(self):
        return self.writer is not None

    def stop_recording(self):
        if self.writer is None:
            return
        self.writer.release()
        self.writer = None
        csv_path = os.path.join(self.dir_name, self.base_name + '.csv')
        with open(csv_path, 'w', newline='') as f:
            w = csv.writer(f)
            w.writerow(['frame_index', 'elapsed_sec_host', 'wall_clock_iso'])
            w.writerows(self.timestamps)
        return csv_path

    def close(self):
        if self.writer is not None:
            self.stop_recording()
        self.cap.release()
