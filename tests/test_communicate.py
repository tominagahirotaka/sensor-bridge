"""Tests for mylib/communicate.py: env_set value coercion and the PC<->board
wire-protocol parsing (key=value;key=value;...), including the split('=', 1)
regression that a real LIS3DH handshake broke earlier (its 'func' field's
lambda body contains 'x>=32768', which collides with a naive split('=') )."""
import threading
from types import SimpleNamespace

import pytest

import mylib.communicate as comm


class TestCoerceEnvValue:
    def test_integer(self):
        assert comm._coerce_env_value("5") == 5

    def test_float(self):
        assert comm._coerce_env_value("0.4") == 0.4

    def test_tuple_of_ints_evaluates_as_python(self):
        assert comm._coerce_env_value("(0, 1, 2)") == (0, 1, 2)

    def test_plain_board_name_is_not_python_evaluable(self):
        # "SHT35" raises NameError under eval() (undefined name) -> falls
        # back to the raw string, not a crash.
        assert comm._coerce_env_value("SHT35") == "SHT35"

    def test_comma_separated_raw_strings_become_a_tuple(self):
        assert comm._coerce_env_value("a,b") == ("a", "b")

    def test_trailing_comma_numeric_value_evaluates_as_a_python_tuple_literal(self):
        # ".ini" convention: a single-element list ends with a comma ("20,")
        # so it round-trips as a tuple. For a numeric value this is valid
        # Python syntax on its own (a 1-tuple literal), so eval() succeeds
        # directly -- the NameError fallback below is never reached.
        assert comm._coerce_env_value("20,") == (20,)

    def test_trailing_comma_non_numeric_value_falls_back_to_string_tuple(self):
        # A non-numeric single value (e.g. a sensor_id like "wire0_0x50")
        # is not a valid Python literal, so eval() raises NameError and the
        # comma-fallback path produces a tuple of the raw string(s).
        assert comm._coerce_env_value("wire0_0x50,") == ("wire0_0x50",)

    def test_lambda_expression_with_comparison_operator(self):
        # The real LIS3DH 'func' field: a lambda whose body contains '>=',
        # evaluated as genuine Python (this is why ast.literal_eval can't be
        # used here -- lambdas aren't a literal).
        value = "[ (lambda x:(x-65536 if x>=32768 else x)*0.001,16, 'g') ]"
        result = comm._coerce_env_value(value)
        assert isinstance(result, list)
        fn, bits, unit = result[0]
        assert unit == "g" and bits == 16
        assert fn(100) == 100 * 0.001          # below threshold: unchanged
        assert fn(40000) == (40000 - 65536) * 0.001  # >=32768: wraps to signed


class TestWireProtocolSplitLimit:
    """dict([k.split('=', 1) for k in board_params.split(';')]) -- the exact
    expression used in connect_serial()/init_serial() to parse the board's
    response. Must not choke on a value that itself contains '='."""

    def test_split_with_limit_handles_embedded_equals_sign(self):
        # A miniature but faithful slice of a real LIS3DH handshake response.
        board_params = "odr=5;func=lambda x:x>=32768;fs=0"
        parsed = dict(k.split("=", 1) for k in board_params.split(";"))
        assert parsed == {
            "odr": "5",
            "func": "lambda x:x>=32768",
            "fs": "0",
        }

    def test_naive_split_without_limit_would_have_broken_this(self):
        # Regression guard: demonstrates *why* split('=', 1) is required --
        # the unlimited split('=') this codebase used to use produces a
        # 3-element list for the 'func' entry, which dict() rejects.
        board_params = "func=lambda x:x>=32768"
        naive_parts = board_params.split("=")
        assert len(naive_parts) == 3  # ['func', 'lambda x:x>', '32768']
        limited_parts = board_params.split("=", 1)
        assert len(limited_parts) == 2


class _FakeSerial:
    """Minimal stand-in for pyserial's Serial, just enough for
    Board.get_data_no_write()'s read/write/reset_*_buffer calls.

    .timeout is a property, not a plain attribute: on real pyserial,
    assigning it triggers a termios reconfiguration that can itself raise
    if the device has just disconnected -- raise_on_timeout_set lets a
    test simulate exactly that."""

    def __init__(self, read_return, raise_on_timeout_set=False, raise_on_reset_buffer=False,
                 raise_on_write=False):
        self.read_return = read_return
        self.read_calls = 0
        self._timeout = 16
        self.raise_on_timeout_set = raise_on_timeout_set
        self.raise_on_reset_buffer = raise_on_reset_buffer
        self.raise_on_write = raise_on_write
        self.written = []

    @property
    def timeout(self):
        return self._timeout

    @timeout.setter
    def timeout(self, value):
        if self.raise_on_timeout_set:
            raise comm.serial.SerialException("device disconnected")
        self._timeout = value

    def read(self, size):
        self.read_calls += 1
        return self.read_return

    def write(self, data):
        if self.raise_on_write:
            raise comm.serial.SerialException("device disconnected")
        self.written.append(data)

    def reset_output_buffer(self):
        if self.raise_on_reset_buffer:
            raise comm.serial.SerialException("device disconnected")

    def reset_input_buffer(self):
        if self.raise_on_reset_buffer:
            raise comm.serial.SerialException("device disconnected")


class TestShortReadHandling:
    """get_data_no_write() must not pass a short/empty read (fewer bytes
    than one_data_size) on to convert() via the data-ready events. A real
    board that finishes a one-shot operation (e.g. X95840W calibration
    converging, or reaching calib_max_iters) legitimately stops sending
    anything; self.ser.read()'s own timeout then returns whatever
    partial/empty buffer it has, which used to crash the reader thread
    with a struct.error instead of just waiting."""

    def _run_one_iteration(self, read_return):
        board = comm.Board.__new__(comm.Board)  # skip __init__ (no real port needed)
        board.ser = _FakeSerial(read_return)
        board.one_data_size = 13
        board._data_ready = threading.Event()
        board._new_data_event = threading.Event()
        board.loop_th = True

        # Stop the loop after exactly one read (short or full), so the
        # while loop terminates deterministically for the test.
        original_read = board.ser.read

        def read_once(size):
            result = original_read(size)
            board.loop_th = False
            return result
        board.ser.read = read_once

        board.get_data_no_write()
        return board

    def test_short_read_is_skipped_not_signaled(self):
        board = self._run_one_iteration(b'')
        assert board.ser.read_calls == 1
        assert not board._data_ready.is_set()
        assert not board._new_data_event.is_set()

    def test_full_read_is_signaled_normally(self):
        board = self._run_one_iteration(b'\x00' * 13)
        assert board._data_ready.is_set()
        assert board._new_data_event.is_set()
        assert board.ser_data == b'\x00' * 13

    def test_timeout_shrinks_after_first_short_read_so_stop_stays_responsive(self):
        # reset()'s th.join() (see window.py) blocks the GUI thread until
        # this loop notices loop_th=False, which is only checked between
        # read() calls -- so once the board's gone idle, a Stop click
        # must not have to wait out the full, normally-generous read
        # timeout (16s) before the thread can exit. Regression test for
        # exactly this: the app appeared to hang after Stop once the
        # short-read skip (above) kept the thread alive but still using
        # the original long timeout on every subsequent attempt.
        board = comm.Board.__new__(comm.Board)
        board.ser = _FakeSerial(b'')  # always a short/empty read
        board.one_data_size = 13
        board._data_ready = threading.Event()
        board._new_data_event = threading.Event()
        board.loop_th = True

        seen_timeouts = []
        original_read = board.ser.read

        def read_and_record(size):
            seen_timeouts.append(board.ser.timeout)
            result = original_read(size)
            if len(seen_timeouts) >= 2:
                board.loop_th = False  # stop after the 2nd attempt
            return result
        board.ser.read = read_and_record

        board.get_data_no_write()

        assert seen_timeouts[0] == 16   # first attempt: still the original timeout
        assert seen_timeouts[1] <= 1    # second attempt: shrunk once idle was detected
        assert board.ser.timeout == 16  # restored once the thread actually exits

    def test_first_read_already_uses_the_steady_state_timeout(self):
        # Regression test: sizing the timeout to the board's own
        # configured sample interval (real_time_interval, always in
        # microseconds) from the very *first* read -- not just after the
        # first slow detection -- is what actually fixes the "6 second
        # wait" symptom: a user who reacts (Stop, or Test/Run right after
        # caliBrate finishes) before a second read ever happens must not
        # still be stuck behind the old flat 16s default.
        board = comm.Board.__new__(comm.Board)
        board.ser = _FakeSerial(b'')
        board.one_data_size = 13
        board._data_ready = threading.Event()
        board._new_data_event = threading.Event()
        board.loop_th = True
        board.real_time_interval = 2000  # 2ms, e.g. X95840W's default

        seen_timeouts = []
        original_read = board.ser.read

        def read_and_record(size):
            seen_timeouts.append(board.ser.timeout)
            board.loop_th = False  # stop after exactly one attempt
            return original_read(size)
        board.ser.read = read_and_record

        board.get_data_no_write()

        assert seen_timeouts[0] <= 1  # not the flat 16s default
        assert board.ser.timeout == 16  # still restored to the true original on exit

    def test_went_idle_flag_is_set_on_first_short_read(self):
        # Regression test for the "please show a message when caliBrate
        # finishes" request: window.py's update() polls Board.went_idle
        # (Qt main thread) to show a one-shot status message; the reader
        # thread must actually set it the moment it first detects the
        # board's gone quiet.
        board = comm.Board.__new__(comm.Board)
        board.ser = _FakeSerial(b'')
        board.one_data_size = 13
        board._data_ready = threading.Event()
        board._new_data_event = threading.Event()
        board.loop_th = True
        board.went_idle = False

        original_read = board.ser.read

        def read_once(size):
            result = original_read(size)
            board.loop_th = False
            return result
        board.ser.read = read_once

        board.get_data_no_write()

        assert board.went_idle is True

    def test_timeout_restore_failure_after_read_error_does_not_crash(self):
        # Regression test: on real hardware, a board disconnect makes
        # self.ser.read() fail with a SerialException (correctly caught,
        # see the except clause above) -- but restoring self.ser.timeout
        # during cleanup right afterward was, until this fix, itself
        # capable of raising an uncaught SerialException/termios.error
        # from that same already-broken port (setting pyserial's .timeout
        # triggers a real termios reconfiguration, not a plain attribute
        # write), crashing the reader thread with a traceback instead of
        # just stopping cleanly.
        board = comm.Board.__new__(comm.Board)
        board.ser = _FakeSerial(b'', raise_on_timeout_set=True)
        board.one_data_size = 13
        board._data_ready = threading.Event()
        board._new_data_event = threading.Event()
        board.loop_th = True

        def read_raises(size):
            raise comm.serial.SerialException("device disconnected")
        board.ser.read = read_raises

        board.get_data_no_write()  # must not raise


class TestSteadyStateTimeout:
    """Board._steady_state_timeout(): a read() timeout sized to the
    board's own configured sample interval (real_time_interval, always
    microseconds), with a 1s floor (so normal jitter never false-triggers
    idle detection) and a 16s ceiling (so a board with a genuinely slow
    configured interval never waits longer than the old flat default)."""

    def _make_board(self, real_time_interval=None, ser_timeout=16):
        board = comm.Board.__new__(comm.Board)
        board.ser = _FakeSerial(b'')
        board.ser.timeout = ser_timeout
        if real_time_interval is not None:
            board.real_time_interval = real_time_interval
        return board

    def test_fast_board_hits_the_one_second_floor(self):
        board = self._make_board(real_time_interval=2000)  # 2ms
        assert board._steady_state_timeout() == 1.0

    def test_slow_board_is_capped_at_the_sixteen_second_ceiling(self):
        board = self._make_board(real_time_interval=5_000_000)  # 5s
        assert board._steady_state_timeout() == 16.0

    def test_missing_real_time_interval_falls_back_to_current_ser_timeout(self):
        board = self._make_board(real_time_interval=None, ser_timeout=16)
        assert board._steady_state_timeout() == 16


class TestConnectSerialToleratesDeadPort:
    def test_reset_buffer_failure_does_not_crash_stop(self):
        # Regression test: on real hardware, connect_serial(b'r') (sent by
        # every button handler's reset() -> stop_running(), i.e. on every
        # Test/Run/caliBrate/Stop press) used to crash uncaught if the
        # board had just disconnected -- reset_output_buffer()/
        # reset_input_buffer() do a real termios.tcflush() under the hood,
        # which raises on an already-dead port, and that ran before the
        # write() whose failure would actually be expected/catchable.
        board = comm.Board.__new__(comm.Board)
        board.ser = _FakeSerial(b'', raise_on_reset_buffer=True)

        board.connect_serial(b'r')  # must not raise

        assert board.ser.written == [b'r']  # write still happens after the tolerated reset failure

    def test_write_failure_raises_a_clean_runtime_error(self):
        # Regression test: on real hardware, a board that drops out right
        # as a button is pressed made self.ser.write(marker) itself raise
        # a SerialException/OSError -- unlike the read side (see
        # get_data_no_write()), nothing up this call chain
        # (connect_serial() <- stop_running()/start_running() <-
        # reset()/window.py's button handlers) caught it, so it crashed
        # straight through the Qt button-click slot with a raw traceback
        # instead of a clean, catchable, user-facing message.
        board = comm.Board.__new__(comm.Board)
        board.ser = _FakeSerial(b'', raise_on_write=True)
        board.p = SimpleNamespace(board={'device': ['/dev/ttyACM0']})

        with pytest.raises(RuntimeError):
            board.connect_serial(b's')


class TestOpenSerialChipId:
    """open_serial() must parse the optional third handshake field (the
    board's factory-burned unique ID, appended by newer firmware) without
    breaking on older firmware's plain ':name:@@' announcement."""

    def _make_board(self, waiting_return):
        board = comm.Board.__new__(comm.Board)
        board.ser = SimpleNamespace(open=lambda: None,
                                     reset_output_buffer=lambda: None,
                                     reset_input_buffer=lambda: None)
        board._waiting = lambda ch, timeout=None: waiting_return
        return board

    def test_new_firmware_reports_program_name_and_chip_id(self):
        board = self._make_board(b':LIS3DH_SPI:E660C4D2C1234567:@@')
        program, chip_id = board.open_serial()
        assert program == 'LIS3DH_SPI'
        assert chip_id == 'E660C4D2C1234567'

    def test_old_firmware_with_no_chip_id_field_still_works(self):
        board = self._make_board(b':LIS3DH_SPI:@@')
        program, chip_id = board.open_serial()
        assert program == 'LIS3DH_SPI'
        assert chip_id is None
