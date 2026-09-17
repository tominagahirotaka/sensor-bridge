"""Regression tests for the GUI-freeze fix: once a board has legitimately
gone quiet (e.g. an X95840W calibration run converging or reaching
calib_max_iters -- see mylib/communicate.py's get_data_no_write()/
get_data_and_write()), neither Board.data_stream() nor FigureQtPG.update()
may block indefinitely. data_stream() is consumed by FigureQtPG.update(),
itself called from window.py's update() -- a slot on a 0ms-interval
QTimer running on the Qt *main* thread -- so an unbounded wait()
anywhere in this chain freezes the entire application (no repaints, no
button clicks, OS "Not Responding"), not just delays the reader thread's
own shutdown (which get_data_no_write()/get_data_and_write() already
handle separately -- see tests/test_communicate.py's TestShortReadHandling)."""
import struct
import threading
import time
from types import SimpleNamespace

import mylib.communicate as comm
from mylib.Qtutils import FigureQtPG


class TestDataStreamTimeoutYieldsNone:
    def _make_board(self):
        board = comm.Board.__new__(comm.Board)  # skip __init__ (no real port needed)
        board._struct = struct.Struct('<I')
        board._total_size = board._struct.size
        board._func_list = [lambda v: float(v)]
        board.structure = [None]  # only its length is used by data_stream()
        board._data_ready = threading.Event()
        board._new_data_event = threading.Event()
        board.ser_data = struct.pack('<I', 100)
        board._data_ready.set()
        return board

    def _produce_one_sample(self, board, value):
        """Mimics what the real reader thread (get_data_and_write()/
        get_data_no_write()) does: set new bytes, then signal. Run on a
        background thread, like the real thing -- data_stream()'s first
        loop pass captures the board's *current* ser_data as its baseline
        synchronously, before ever waiting, so a same-thread caller could
        never make the first yield see "changed" data."""
        def produce():
            time.sleep(0.05)
            board.ser_data = struct.pack('<I', value)
            board._new_data_event.set()
        threading.Thread(target=produce, daemon=True).start()

    def test_first_yield_is_always_real_data(self):
        # FigureQtPG.update() relies on this: the very first value ever
        # pulled from the stream must never be the "nothing new" sentinel.
        board = self._make_board()
        stream = board.data_stream()
        self._produce_one_sample(board, 200)
        assert next(stream) is not None

    def test_later_timeout_yields_none_instead_of_blocking_forever(self):
        board = self._make_board()
        stream = board.data_stream()
        self._produce_one_sample(board, 200)
        assert next(stream) is not None
        # No new data event this time -- must time out (well under a
        # second, not the original unbounded wait) and yield None.
        assert next(stream) is None

    def test_stale_wrong_sized_buffer_is_skipped_not_crashed_on(self):
        # Regression test: self._data_ready/self.ser_data are Board-level
        # state shared across sessions, but a fresh data_stream() generator
        # is created on every Test/Run/caliBrate button press (see
        # ReceiveCommon.start_read_thread()). caliBrate's wire-protocol
        # struct is *larger* than Test/Run's (it appends per-sample dpm
        # fields), so switching modes leaves self.ser_data holding a
        # buffer sized for the *previous* mode until the reader thread
        # delivers a first sample in the new size. Before this fix,
        # data_stream() trusted whatever self.ser_data held as soon as
        # self._data_ready was set (already true from the old session) and
        # crashed in convert() with a struct.error -- permanently killing
        # the generator, so every later next(stream) raised StopIteration
        # instead and the whole GUI (plot, HR, dpm) froze forever.
        board = self._make_board()  # _struct expects 4 bytes
        board.ser_data = b'\x01\x02\x03'  # stale 3-byte leftover from a
                                           # differently-sized previous mode
        stream = board.data_stream()

        def produce():
            time.sleep(0.05)
            # First correctly-sized sample: unblocks the stale-buffer skip
            # and becomes data_stream()'s baseline (ser_data0) -- by
            # design this one is never itself yielded as "new".
            board.ser_data = struct.pack('<I', 200)
            board._data_ready.set()
            time.sleep(0.05)
            # A second, distinct sample so the main loop sees a genuine
            # change and yields.
            board.ser_data = struct.pack('<I', 201)
            board._new_data_event.set()
        threading.Thread(target=produce, daemon=True).start()

        assert next(stream) is not None  # must not raise struct.error


class TestFigureUpdateHandlesNone:
    def test_returns_cached_result_without_touching_plot_state(self):
        stub = SimpleNamespace(_last_result=("cached_data_t", "cached_peak_interval"))
        result = FigureQtPG.update(stub, iter([None]))
        assert result == ("cached_data_t", "cached_peak_interval")
