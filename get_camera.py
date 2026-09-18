#!/usr/bin/env python3
"""
sensor-bridge companion: live USB webcam preview + recording.

Runs as its own process, independent of get.py -- a webcam (USB Video
Class) and a Pico board (USB CDC-ACM/serial) are different USB device
classes with separate OS driver stacks, so running this alongside one or
more `python get.py` processes needs no special coordination between them
(unlike get.py's own multi-board case, where several *boards'* serial
handshakes do need to be serialized -- see mylib/communicate.py). See
README.md's "Webcam capture" section for what this script does and does
not guarantee about timing relative to sensor recordings.

With multiple cameras connected, `-a`/`--all` opens every detected one at
once, each in its own window/process, mirroring get.py's own
one-process-per-board pattern -- see main()/make_window() below.
"""

import argparse
import multiprocessing
import platform
import sys

from PyQt5.QtCore import Qt, QTimer
from PyQt5.QtGui import QIcon, QImage, QPixmap
from PyQt5.QtWidgets import (QApplication, QHBoxLayout, QLabel, QMainWindow,
                             QPushButton, QStatusBar, QVBoxLayout, QWidget)

from mylib.camera import CameraCapture, list_cameras
from mylib.sync import SyncListener
from version import __version__


class CameraWindow(QMainWindow):
    def __init__(self, camera_index, dir_name, sync=False):
        super().__init__()
        self.dir_name = dir_name
        self.cam = CameraCapture(camera_index)
        self.setWindowTitle(f'sensor-bridge webcam (camera {camera_index})')
        # Opt-in "start/stop together" listener (see mylib/sync.py and
        # sync_trigger.py) -- off by default so a plain
        # `python get_camera.py` behaves exactly as before.
        self.sync = SyncListener(label=self.windowTitle()) if sync else None
        if self.sync:
            self.sync.triggered.connect(self.on_sync_command)
        self._build_ui()
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.update_frame)
        # Unlike get.py's boards, a webcam frame is usually already sitting
        # in a driver-side buffer when polled, so an interval of 0 here
        # (as get.py uses, where the actual pacing comes from the serial
        # data's own arrival rate) just busy-spins read_frame() far faster
        # than any camera's frame rate, pegging a CPU core for no benefit.
        self.timer.start(33)  # ~30 Hz, matching a typical webcam's own frame rate

    def _build_ui(self):
        self.preview = QLabel()
        self.preview.setMinimumSize(320, 240)
        self.preview.setAlignment(Qt.AlignCenter)
        self.status = QStatusBar()
        self.setStatusBar(self.status)
        self.start_btn = QPushButton('Run')
        self.start_btn.clicked.connect(self.on_start)
        self.stop_btn = QPushButton('Stop')
        self.stop_btn.clicked.connect(self.on_stop)
        self.mark_btn = QPushButton('Mark')
        self.mark_btn.clicked.connect(self.on_mark)
        buttons = QHBoxLayout()
        buttons.addWidget(self.start_btn)
        buttons.addWidget(self.stop_btn)
        buttons.addWidget(self.mark_btn)
        central = QWidget()
        layout = QVBoxLayout(central)
        layout.addWidget(self.preview)
        layout.addLayout(buttons)
        self.setCentralWidget(central)
        self.resize(800, 640)

    def update_frame(self):
        frame = self.cam.read_frame()
        if frame is None:
            return
        if self.cam.is_recording():
            self.cam.write_frame(frame)
        h, w, ch = frame.shape
        img = QImage(frame.data, w, h, ch * w, QImage.Format_BGR888)
        self.preview.setPixmap(QPixmap.fromImage(img).scaled(
            self.preview.width(), self.preview.height(), Qt.KeepAspectRatio))
        if self.cam.is_recording():
            self.status.showMessage(
                f'Run (recording) -- {len(self.cam.timestamps)} frames, '
                f'{len(self.cam.marks)} marks')
        else:
            self.status.showMessage('Preview (not recording)')

    def on_start(self):
        if self.cam.is_recording():
            return
        node = platform.uname().node
        self.cam.start_recording(self.dir_name, node)

    def on_stop(self):
        if not self.cam.is_recording():
            return
        self.cam.stop_recording()

    def on_mark(self):
        self.cam.mark()  # no-op while not recording; update_frame()'s status text reflects it

    def on_sync_command(self, command):
        """Handles a run/stop/mark/quit trigger from sync_trigger.py (see
        mylib/sync.py); only bound when this window was launched with
        -sync. 'test' and 'calibrate' (meaningful only for get.py boards)
        are simply not handled here and are ignored, same as any other
        unrecognized command."""
        if command == 'run':
            self.on_start()
        elif command == 'stop':
            self.on_stop()
        elif command == 'mark':
            self.on_mark()
        elif command == 'quit':
            self.close()  # triggers closeEvent() -> cam/sync cleanup

    def closeEvent(self, event):
        if self.sync:
            self.sync.close()
        self.cam.close()


def make_window(argv, camera_index, out_dir, sync=False):
    """Create and run one camera's QApplication/window/event loop. Called
    directly for the single-camera case, or as a multiprocessing.Process
    target (one process per camera, mirroring get.py's own
    one-process-per-board pattern in make_window()/main() there) for -a."""
    app = QApplication(['sensor-bridge-camera'] + list(argv[1:]))
    app.setDesktopFileName('sensor-bridge-camera')
    app.setWindowIcon(QIcon('icon.png'))
    window = CameraWindow(camera_index, out_dir, sync=sync)
    window.show()
    sys.exit(app.exec_())


def main():
    parser = argparse.ArgumentParser(description='sensor-bridge webcam capture companion')
    parser.add_argument('-c', '--camera', type=int, default=0,
                        help='camera index to open (default: 0); ignored if -a is given')
    parser.add_argument('-a', '--all', action='store_true',
                        help='open every detected camera at once (see --list), each in '
                             'its own window/process, instead of a single -c index')
    parser.add_argument('-o', '--out', default='data_camera',
                        help='output directory for recordings (default: data_camera)')
    parser.add_argument('-v', '--version', action='version', version=f'%(prog)s {__version__}')
    parser.add_argument('--list', action='store_true',
                        help='list available camera indices and exit')
    parser.add_argument('-sync', '--sync', action='store_true',
                        help='listen for run/stop/mark/quit triggers from sync_trigger.py '
                             '(to run/stop/mark/quit this window together with other '
                             'sync-enabled get.py/get_camera.py windows)')
    args = parser.parse_args()

    if args.list:
        cams = list_cameras()
        print(f'Available cameras: {cams}' if cams else 'No cameras found.')
        return

    if args.all:
        # 'spawn', not the Linux default 'fork': a forked child inheriting
        # this process's already-initialized Qt/OpenCV state is exactly
        # the kind of thing get.py's own multiprocessing setup (see its
        # main()) avoids for pyserial, for the same reason -- a fresh
        # interpreter per camera is the safer default here too.
        multiprocessing.set_start_method('spawn')
        cams = list_cameras()
        if not cams:
            print('No cameras found.')
            return
        print(f'Opening {len(cams)} camera(s): {cams}')
        for idx in cams:
            multiprocessing.Process(
                target=make_window, args=(sys.argv, idx, args.out, args.sync)).start()
        return

    make_window(sys.argv, args.camera, args.out, args.sync)


if __name__ == '__main__':
    main()
