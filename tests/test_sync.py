"""Tests for mylib/sync.py: the local-UDP "start/stop together" signal
used by get.py/get_camera.py's -sync flag and sync_trigger.py. Uses the
shared `qapp` fixture (see conftest.py) since SyncListener's cross-thread
signal needs a running Qt event loop to actually dispatch."""
import glob
import os
import time

import pytest

import mylib.sync as sync


@pytest.fixture(autouse=True)
def clean_registry():
    """Isolates each test from anything a real get.py/get_camera.py run
    (or a previous test) left in the shared registry directory."""
    for path in glob.glob(os.path.join(sync.REGISTRY_DIR, '*.json')):
        os.remove(path)
    yield
    for path in glob.glob(os.path.join(sync.REGISTRY_DIR, '*.json')):
        os.remove(path)


def _pump_until(qapp, condition, timeout=2.0):
    """Process Qt events until `condition()` is true or `timeout` seconds
    pass; returns whether it became true (a queued cross-thread signal
    only gets delivered while the event loop is being pumped)."""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        qapp.processEvents()
        if condition():
            return True
        time.sleep(0.01)
    return False


class TestRegistry:
    def test_send_trigger_with_no_listeners_returns_zero(self):
        assert sync.list_listeners() == []
        assert sync.send_trigger('start') == 0

    def test_listener_registers_and_unregisters_itself(self, qapp):
        listener = sync.SyncListener(label='my window')
        try:
            entries = sync.list_listeners()
            assert len(entries) == 1
            assert entries[0]['pid'] == os.getpid()
            assert entries[0]['label'] == 'my window'
            assert entries[0]['port'] == listener._port
        finally:
            listener.close()
        assert sync.list_listeners() == []


class TestTrigger:
    def test_send_trigger_reaches_a_connected_listener(self, qapp):
        received = []
        listener = sync.SyncListener(label='board A')
        listener.triggered.connect(received.append)
        try:
            n = sync.send_trigger('start')
            assert n == 1
            assert _pump_until(qapp, lambda: received == ['start'])
        finally:
            listener.close()

    def test_send_trigger_reaches_multiple_listeners_at_once(self, qapp):
        received_a, received_b = [], []
        a = sync.SyncListener(label='board A')
        b = sync.SyncListener(label='board B')
        a.triggered.connect(received_a.append)
        b.triggered.connect(received_b.append)
        try:
            n = sync.send_trigger('stop')
            assert n == 2
            assert _pump_until(qapp, lambda: received_a == ['stop'] and received_b == ['stop'])
        finally:
            a.close()
            b.close()
