#!/usr/bin/env python3
"""Same-machine "start/stop together" signal for get.py board windows and
get_camera.py.

Each of these runs as its own OS process with its own Qt event loop (see
get.py's make_window() and get_camera.py), so a single Qt keyboard
shortcut can only ever fire inside whichever one currently has focus --
there is no such thing as a shortcut shared across independent processes.
Instead: a window that opts in (via the -sync flag) listens on its own
ephemeral local UDP port and registers that port, under its own PID,
under a small directory in the system temp dir. sync_trigger.py reads
that directory and sends one command ("start" or "stop") to every
registered port at once. The intended use is to bind an OS-level global
keyboard shortcut (outside this codebase, in the OS's own settings) to
running `python sync_trigger.py start` -- from the user's perspective,
one keypress starts every currently-open, sync-enabled window together.

This is deliberately unauthenticated, loopback-only (127.0.0.1) local
IPC -- not a network protocol -- matching the trust model of a single
user's own machine running their own recording software.
"""

import glob
import json
import os
import socket
import tempfile
import threading
import uuid

from PyQt5.QtCore import QObject, pyqtSignal

REGISTRY_DIR = os.path.join(tempfile.gettempdir(), 'sensor-bridge-sync')


class SyncListener(QObject):
    """Binds an ephemeral local UDP port, registers it (PID, port, label)
    under REGISTRY_DIR, and emits `triggered(command)` -- on the Qt main
    thread, via Qt's automatic queued cross-thread connection -- whenever
    a UDP datagram arrives on that port."""

    triggered = pyqtSignal(str)

    def __init__(self, label='', parent=None):
        super().__init__(parent)
        self._sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self._sock.bind(('127.0.0.1', 0))          # OS picks a free port
        self._port = self._sock.getsockname()[1]
        self._running = True
        os.makedirs(REGISTRY_DIR, exist_ok=True)
        # Named by a random id, not just the PID: get.py's boards and
        # get_camera.py each run in their own process in practice, but the
        # registry itself should stay correct even if two listeners were
        # ever created in the same process (two same-PID files would
        # otherwise collide, silently dropping the first one).
        self._registry_path = os.path.join(REGISTRY_DIR, f'{uuid.uuid4().hex}.json')
        with open(self._registry_path, 'w') as f:
            json.dump({'pid': os.getpid(), 'port': self._port, 'label': label}, f)
        self._thread = threading.Thread(target=self._listen, daemon=True)
        self._thread.start()

    def _listen(self):
        while self._running:
            try:
                data, _addr = self._sock.recvfrom(64)
            except OSError:
                break                              # socket closed -> exit thread
            command = data.decode('utf-8', 'ignore').strip()
            if command:
                self.triggered.emit(command)

    def close(self):
        """Stop listening and remove this process's registry entry. Safe
        to call more than once."""
        self._running = False
        try:
            self._sock.close()
        except OSError:
            pass
        try:
            os.remove(self._registry_path)
        except OSError:
            pass


def _pid_alive(pid):
    if os.name == 'nt':
        # os.kill(pid, 0) isn't a liveness check on Windows; a stray
        # registry entry just costs one harmless extra send attempt, so
        # assume alive rather than risk pruning a live entry.
        return True
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True                                # exists, just owned by someone else
    return True


def list_listeners():
    """Return [{'pid', 'port', 'label'}, ...] for every currently
    registered listener, pruning entries whose process is no longer
    alive as they're found."""
    result = []
    for path in glob.glob(os.path.join(REGISTRY_DIR, '*.json')):
        try:
            with open(path) as f:
                entry = json.load(f)
            pid = int(entry['pid'])
        except (OSError, ValueError, KeyError):
            continue
        if not _pid_alive(pid):
            try:
                os.remove(path)
            except OSError:
                pass
            continue
        result.append({'pid': pid, 'port': entry.get('port'), 'label': entry.get('label', '')})
    return result


def send_trigger(command):
    """Send `command` (e.g. "start"/"stop") to every currently registered
    listener. Returns the number of listeners it was sent to."""
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        listeners = list_listeners()
        for entry in listeners:
            sock.sendto(command.encode('utf-8'), ('127.0.0.1', entry['port']))
        return len(listeners)
    finally:
        sock.close()
