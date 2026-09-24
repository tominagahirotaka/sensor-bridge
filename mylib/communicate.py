#!/usr/bin/env python3
"""USB-serial link to the Pico/Pico W board: board discovery, the
handshake protocol (parameters + binary 'struct' description), and the
background thread that streams decoded samples for get.py's GUI."""

import contextlib
import datetime
import json
import os
import platform
import struct
import tempfile
import threading
import time

import numpy as np
import serial.tools.list_ports

try:
    # termios is POSIX-only. Against an already-disconnected serial device,
    # calls like ser.reset_output_buffer() can raise termios.error (a direct
    # subclass of Exception, not OSError) instead of serial.SerialException,
    # so it needs to be caught separately. On Windows the module itself
    # doesn't exist, so this is left empty there.
    import termios
    _TERMIOS_ERRORS = (termios.error,)
except ImportError:
    _TERMIOS_ERRORS = ()

try:
    import fcntl                       # POSIX advisory file locking

    def _lock_file(f):
        fcntl.flock(f.fileno(), fcntl.LOCK_EX)

    def _unlock_file(f):
        fcntl.flock(f.fileno(), fcntl.LOCK_UN)
except ImportError:
    import msvcrt                      # Windows advisory file locking

    def _lock_file(f):
        # msvcrt.locking(LK_LOCK) is not a true blocking wait like
        # fcntl.flock(LOCK_EX): the underlying Windows CRT call retries
        # internally only ~10 times, 1 second apart, then raises OSError.
        # A sibling board's handshake retry loop can legitimately take
        # longer than that (see open_serial()'s up to ~17s worst case), so
        # retry here ourselves to get the same indefinite-wait behavior
        # POSIX gets from flock().
        while True:
            try:
                f.seek(0)
                msvcrt.locking(f.fileno(), msvcrt.LK_LOCK, 1)
                return
            except OSError:
                time.sleep(0.2)

    def _unlock_file(f):
        f.seek(0)
        msvcrt.locking(f.fileno(), msvcrt.LK_UNLCK, 1)

import mylib.fileIO as FIO
import mylib.i18n as i18n
import mylib.utils as utils
from mylib.debug_utils import debug_print
from mylib.i18n import t

# When multiple boards are connected at once, each runs in its own OS
# process (see get.py's make_window()); their initial handshakes (see
# ReceiveCommon.__init__ below) were observed on real hardware to corrupt
# each other if they run concurrently, even though each board has its own,
# entirely separate serial port. A plain OS-level file lock serializes this
# section across those processes regardless of how they were started
# (fork/spawn) or how long the process that launched them stays alive --
# unlike a multiprocessing.Lock passed down from that launcher, which
# depends on both and was found to be unreliable here for exactly that reason.
_HANDSHAKE_LOCK_PATH = os.path.join(tempfile.gettempdir(), 'sensor-bridge-handshake.lock')


@contextlib.contextmanager
def _handshake_lock():
    with open(_HANDSHAKE_LOCK_PATH, 'w') as f:
        _lock_file(f)
        try:
            yield
        finally:
            _unlock_file(f)


def _coerce_env_value(value_str):
    """Parse one board env_set value: the result of evaluating it as a Python
    expression (int/float/tuple of numbers/the board's `func` list of
    `lambda`s/...) when it resolves without NameError, otherwise the raw
    string, or a tuple of raw strings when comma-separated
    (e.g. "0,1,2" -> (0, 1, 2), "SHT35" -> "SHT35", "a,b," -> ("a", "b"))."""
    try:
        return eval(value_str)
    except NameError:
        if ',' in value_str:
            return tuple(value_str.rstrip(',').split(','))
        return value_str


class Header:
    def __init__(self):
        self.board = {}
        self.subject = {}
        self.time = {}
        self.machine = platform.uname()._asdict()                 # Get PC info


class ReceiveCommon:
    def __init__(self, args, board, num_boards=1):
        self.p = Header()                 # Instance of Header class (object holding the info written at the start of the saved file)
        self.init_flag, self.write_flag = False, False        # set flags
        self.p.board['device'] = board
        # Read by FileIO.write_open() to decide whether to disambiguate
        # recording filenames by port -- only needed when more than one
        # board was connected at once (see get.py's main()).
        self.p.board['multi_board'] = num_boards > 1
        self.board = Board(self.p, args, True)        # Instance of Board class
        self.board.loop_th = True         # Thread loop
        with _handshake_lock():
            board_program, chip_id = self.board.open_serial()  # open serial & get board_program name + unique ID
            self.p.board['chip_id'] = chip_id  # None for older firmware that doesn't report one
            ini_path = i18n.resolve_localized_path(
                board_program + '.ini')  # `_jp.ini` sibling when --lang ja
            if os.path.isfile(ini_path):                  # Get measurement environment info
                self.p.env_set, self.code = utils.read_setting_ini(ini_path)
            else:
                print(t('comm.ini_missing_use_default', ini=board_program + '.ini'))
                self.p.env_set, self.code = utils.read_setting_ini(
                    i18n.resolve_localized_path('default.ini'))
            if args.init is not None:
                # configparser.read() silently reads nothing (an empty dict)
                # instead of raising when the given file doesn't exist, so
                # forgetting the .ini extension silently disables -i entirely
                # (e.g. `-i MyBoard` looks for a nonexistent
                # 'MyBoard' instead of 'MyBoard.ini', and the
                # program starts with nothing overridden).
                init_path = args.init if os.path.isfile(args.init) else i18n.resolve_localized_path(
                    args.init if args.init.endswith('.ini') else args.init + '.ini')
                if os.path.isfile(init_path):
                    print(t('comm.additional_init', init=init_path))
                    env_set, code = utils.read_setting_ini(init_path)
                    self.p.env_set.update(env_set)
                    self.code.update(code)
                else:
                    print(t('comm.additional_init_not_found', init=args.init, tried=init_path))
            #
            cssfile = board_program + \
                '.css' if os.path.isfile(board_program + '.css') else 'default.css'
            with open(cssfile, 'r') as f:
                self.style = f.read()
            if args.style is not None:
                with open(args.style, 'r') as f:
                    self.style += f.read()
            #
            # initialize: put & get parameters between PC and board
            self.board.init_serial(b'i')
            print(f'[INFO] {self.p.env_set=}')

    # Start the USB-read-only thread
    def start_read_thread(self):
        if self.write_flag:
            self.file = FIO.FileIO()            # instance of fileIO class
            self.file.write_open(self.p)        # open the data file (for writing)
            self.th = threading.Thread(
                target=self.board.get_data_and_write, args=(
                    self.file.fwrite,))  # set up the thread
        else:
            print(t('comm.not_writing'))
            self.th = threading.Thread(target=self.board.get_data_no_write)  # set up the thread
        # Start the thread
        self.th.setDaemon(True)
        self.th.start()
        # Record the time the thread started
        self.p.time['th_start_time'] = datetime.datetime.now()
        # Data stream (the update function fetches data in turn via this function's yield statement)
        self.stream = self.board.data_stream()

    def check_points(self):
        now = datetime.datetime.now()
        lap_time = self.board.data[-1][0]
        self.p.time['check_points'].append([lap_time, now])
        self.check_point_txt = f"CP.{len(self.p.time['check_points']):03d}  {lap_time:.2f}(sec)"
        print(f'[INFO] {self.check_point_txt=}, {now=}')

    def query_temperature(self):
        """Best-effort: query the board's on-chip temperature (see
        Board.query_temperature()) and append it to self.p.board
        ['temperature_log'] (a new field, separate from check_points, so
        this can never collide with plot.py's mark-points Excel export,
        which expects exactly 2 columns per check_points entry). Returns
        the temperature (or None on failure/older firmware) so callers
        can report it immediately without re-reading the header."""
        temp_c = self.board.query_temperature()
        print(f'[INFO] query_temperature() -> {temp_c=}')
        if temp_c is not None:
            self.p.board.setdefault('temperature_log', []).append(
                {'when': datetime.datetime.now(), 'temp_c': temp_c})
        return temp_c


class Receive(ReceiveCommon):
    def __init__(self, args, board, num_boards=1):
        super().__init__(args, board, num_boards)

    # Start measurement (Qt)
    def start_running(self, marker):
        # Connect over USB, send the command, and apply the returned parameters
        # b"s"... start or test, b"c"... calibration
        self.board.connect_serial(marker)
        self.board.ser.read_until(b'OK\r\n')                 # Flush until OK\r\n
        self.p.time['start_time'] = datetime.datetime.now()  # Record the measurement start time
        self.start_read_thread()                             # Start thread

    # Send b'r' (Stop) to Board
    def stop_running(self):
        self.board.connect_serial(b'r')                      # Connect over USB, command b'r' (Stop)

    # setting informations from subject window to self.p
    def set_subject_info(self, subject):
        self.p.subject = subject

    # change env_set & send env_set to Board
    def change_env_set(self, result):
        self.p.env_set.update(result)
        # Again(ReInitialize): put & get parameters between PC and board
        self.board.init_serial(b'a')


def search_connected_boards():
    boards = []
    with open('VID_PID_list.json') as f:
        VID_PID_list = json.load(f)
    board_search_list = ['pico'] + list(set([k.split(':')[0] for k in VID_PID_list.keys()]))
    while True:
        for name in board_search_list:
            boards += list(serial.tools.list_ports.grep(name))
        if len(boards) > 0:
            break
        print(t('comm.board_not_connected'))
        ans = input(t('comm.prompt_connect_usb'))
        if ans:
            break
    return [list(usb) for usb in list(dict.fromkeys(boards))]   # remove duplicates


class Board:
    def __init__(self, p, args, isget):
        self.p = p
        self.args = args
        if isget:
            self.baud_rate_list = [9600, 19200, 38400, 57600, 115200, 230400, 460800, 921600]
            # 4...115200 == self.ser.BAUDRATES[21]
            self.p.board['baudrate'] = self.baud_rate_list[4]
            self.ser = serial.Serial(None, timeout=16, write_timeout=16)
            self.ser.baudrate = self.p.board['baudrate']
            self.ser.port = self.p.board['device'][0]
            self.ser_data = None          # explicitly initialize to None
            self._data_ready = threading.Event()
            self._new_data_event = threading.Event()
            # Set by get_data_no_write()/get_data_and_write() (reader
            # thread) the moment the board is first found to have gone
            # quiet -- e.g. a caliBrate run converging. Polled and
            # consumed by window.py's update() (Qt main thread) to show a
            # one-shot "calibration finished" status message; a plain
            # bool is safe here the same way self.ser_data/self.loop_th
            # already are shared across threads without a lock elsewhere
            # in this class.
            self.went_idle = False

            print(f'[INFO] {self.ser.port=}')

    def _build_struct(self):
        """Pre-compile a struct.Struct from `structure`."""
        # Check the actual value of self.endian
        # 'little' -> '<', 'big' -> '>'
        endian_map = {'little': '<', 'big': '>'}
        fmt = endian_map['little']
        fmt_map = {
            1: 'B',   # uint8
            2: 'H',   # uint16
            4: 'I',   # uint32
            8: 'Q',   # uint64
        }
        self._offsets = []
        self._sizes = []
        self._func_list = []

        for st in self.structure:
            start, end = st[1]
            size = end - start
            fmt += fmt_map[size]
            self._offsets.append((start, end))
            self._sizes.append(size)
            self._func_list.append(self.func[st[2]][0])  # add the function directly to the list

        self._struct = struct.Struct(fmt)
        self._total_size = self._struct.size

    def set_self_vars(self):
        """Turn the board's `struct`/other env_set values into self.<name> attributes.

        Example pipeline for "time(u4:func0), [(1,2,3)]port(u2:func1), [2]dpm(u1:func2)":
        `utils.repeat_interpret(...)` expands the [n]/[(a,b,c)] repeat groups:
            ['time(u4:func0)', 'port(u2:func1)0', 'port(u2:func1)1', 'port(u2:func1)2',
             'dpm(u1:func2)0', 'dpm(u1:func2)1']
        `utils.make_struct_list(...)` then turns each token into [label, (start, end), func_index]:
            [[('time', ''), (0, 4), 0], [('port', '0'), (4, 6), 1], [('port', '1'), (6, 8), 1],
             [('port', '2'), (8, 10), 1], [('dpm', '0'), (10, 11), 2], [('dpm', '1'), (11, 12), 2]]
        """
        for key, val in self.p.env_set.items():
            if 'struct' in (key + '=' + str(val)):
                continue
            setattr(self, key, _coerce_env_value(str(val)))
        struct_tokens = utils.repeat_interpret(
            self.p.env_set['struct'],
            sep=',',
            paren_count='[]',
            paren_content='{}')
        self.structure = utils.make_struct_list(struct_tokens)
        debug_print(self.args, f'{struct_tokens=}\n[Debug] {self.structure=}\n')
        self.one_data_size = self.structure[-1][1][-1]
        # Labels
        self.lab = [lst[0][0] for lst in self.structure]
        self.lab_sub = [lst[0][1] for lst in self.structure]
        debug_print(self.args, f'{self.lab=}, {self.lab_sub=}')
        # func, num_of_byte ->  (func(0), func(b'1'*num_of_byte)
        self.lim_auto_func = [(lst[0](0), lst[0](eval('0b' + '1' * int(lst[1]))))
                              for lst in self.func]
        self.lim_auto_raw = [(0, eval('0b' + '1' * int(lst[1]))) for lst in self.func]
        self.func_unit = [lst[2] for lst in self.func]
        debug_print(self.args, f'{self.lim_auto_func=}\n[Debug] {self.lim_auto_raw=}')

    def _waiting(self, ch, timeout=None):
        t0 = time.monotonic()
        while not self.ser.inWaiting() > 0:
            if timeout is not None and time.monotonic() - t0 > timeout:
                return b''          # let the caller decide how to react
            time.sleep(0.001)  # wait 1ms to free up the CPU

        if timeout is not None:
            # read_until() is itself bounded by self.ser.timeout (16s by
            # default), not the `timeout` given here -- without narrowing it
            # too, a partial/stray fragment already in the buffer (with no
            # '@@' ever following it) would block far longer than intended
            # before read_until() gives up and returns just that fragment.
            orig_ser_timeout = self.ser.timeout
            self.ser.timeout = timeout
        try:
            u_atmark = self.ser.read_until(b'@@')              # Flush buffer until @@
        finally:
            if timeout is not None:
                self.ser.timeout = orig_ser_timeout
        debug_print(self.args, f'{u_atmark=}')
        if self.ser.inWaiting() > 0:
            self.ser.readline()  # Flush \r\n after @@   <- IMPORTANT
        if ch == 'board_program':
            return u_atmark
        lines = ''
        for oneline in (u_atmark.decode('utf-8', "ignore")[:-1]).split('\r\n'):
            if (len(oneline) > 1) and (oneline[-1] == '@'):
                lines += oneline[:-1]
        return lines

    def _parse_setparams(self, raw):
        """key=value;key=value;... -> dict, or raises ValueError. Split on
        only the first '=' per entry: some values contain '=' themselves
        (e.g. LIS3DH's func field's lambda body has 'x>=32768')."""
        return dict(k.split('=', 1) for k in raw.split(';'))

    def _reset_buffers(self):
        """Best-effort self.ser.reset_output_buffer()/reset_input_buffer().
        Like _set_timeout() above, these aren't plain no-fail calls -- they
        do a real termios.tcflush() under the hood, which raises if the
        device has just disconnected. That's harmless to ignore here: they
        are only a pre-write cleanup of stale bytes, and a truly dead port
        is properly reported instead (a clean RuntimeError, not a raw
        exception) by _write_marker() below, which every caller of this
        method calls right afterward.
        Without this, a board hiccup at exactly this moment crashed every
        button handler uncaught (they all call this via reset() ->
        stop_running() -> connect_serial(b'r') first), not just the one
        actually reading/writing data."""
        try:
            self.ser.reset_output_buffer()
            self.ser.reset_input_buffer()
        except (serial.SerialException, OSError, *_TERMIOS_ERRORS):
            pass

    def _write_marker(self, marker):
        """self.ser.write(marker), converting a disconnect into a clean,
        catchable RuntimeError instead of letting the raw SerialException/
        OSError reach the caller uncaught. On real hardware, a board that
        drops out right as a button is pressed made this write() itself
        raise -- unlike the read side (get_data_no_write()/
        get_data_and_write()), which already handles a disconnect
        cleanly, nothing up this call chain (connect_serial() <-
        stop_running()/start_running() <- reset()/window.py's button
        handlers) caught it, so the exception crashed straight through the
        Qt button-click slot."""
        try:
            self.ser.write(marker)
        except (serial.SerialException, OSError, *_TERMIOS_ERRORS) as exc:
            raise RuntimeError(
                t('comm.write_failed', port=self.p.board['device'][0], err=exc))

    def query_temperature(self, timeout=1.0):
        """Send 'T' and parse the board's on-chip temperature reply
        ("temp_c=<float>", added alongside the chip_id handshake field --
        see firmware/Arduino/*/utils.cpp and the .ino sketches' 'T' case).
        Returns a float (Celsius, the RP2040/RP2350 die temperature -- not
        the same as the crystal oscillator's own temperature) or None if
        the board doesn't reply within `timeout` (e.g. older firmware
        without this command) or the reply doesn't parse. This is a
        best-effort diagnostic value only (used by
        scripts/calibrate_timing.py to log temperature alongside a clock
        calibration measurement) -- a failure here must never interrupt a
        recording, so it never raises.

        Best called while the board is idle (not streaming samples), so
        it can't perturb a recording's sampling cadence: calibrate_timing.py
        calls this once before 'run', and once more right after the
        end-of-run mark but still before 'stop' (not after -- see
        calibrate_timing.py's module docstring for why 'after stop' can't
        work: get.py's Stop handler writes the recording's .cpt header
        file, and nothing rewrites it afterward)."""
        self._reset_buffers()
        self._write_marker(b'T')
        orig_timeout = self.ser.timeout
        self.ser.timeout = timeout
        try:
            raw = self.ser.readline()
        except (serial.SerialException, OSError, *_TERMIOS_ERRORS) as exc:
            print(f'[INFO] query_temperature(): readline() raised {exc!r}')
            return None
        finally:
            self.ser.timeout = orig_timeout
        line = raw.decode('utf-8', 'ignore').strip()
        print(f'[INFO] query_temperature(): raw reply {raw!r}')
        if not line.startswith('temp_c='):
            return None
        try:
            return float(line[len('temp_c='):])
        except ValueError:
            return None

    def connect_serial(self, marker):
        # Flush *before* writing, not after: some boards (e.g. X95840W,
        # which echoes every received command character back immediately)
        # can start replying fast enough that a flush issued right after
        # the write races against -- and truncates -- the genuine response
        # to marker, instead of just clearing out-of-date leftovers from
        # before this call. Nothing has been requested yet at this point,
        # so it's always safe to discard whatever is currently buffered.
        self._reset_buffers()
        self._write_marker(marker)  # b"s"... start or test, b"c"... calibration
        if marker == b'r':
            return
        # Wait for the board's response. A truncated/garbled response here
        # (seen on real hardware despite the flush reordering above --
        # cause not fully pinned down, possibly USB-level timing outside
        # this code's control) used to crash with an unhandled
        # ValueError/IndexError; retry a couple of times instead.
        board_params = self._waiting('setparams')
        for attempt in range(3):
            try:
                parsed = self._parse_setparams(board_params)
                break
            except ValueError:
                print(t('comm.setparams_retry', attempt=attempt + 1, raw=board_params))
                if attempt == 2:
                    raise RuntimeError(
                        t('comm.setparams_failed', port=self.p.board['device'][0]))
                self._reset_buffers()
                self._write_marker(marker)
                board_params = self._waiting('setparams')
        self.p.env_set.update(parsed)
        # Turn the variables received from the board into self.<name> attributes
        self.set_self_vars()
        self._build_struct()

    def open_serial(self):
        print(t('comm.open_serial'))
        # serial port OPEN
        self.ser.open()
        # Wait for the board's response, obtain the 'board_program' name.
        #
        # Deliberately do NOT flush the input buffer before this first
        # read: some boards (e.g. the X95840W) answer check_serial_reconnect()
        # fast enough that their announcement can already be sitting in the
        # OS buffer the instant open() returns, and flushing here would
        # discard it in a race, leaving nothing to wait for until another
        # connection edge.
        #
        # If a previous host process was killed (rather than cleanly quit)
        # while the board was mid-stream, a burst of orphaned sample bytes
        # can still be draining out right around the reconnect (the
        # firmware stops streaming on disconnect, but bytes already queued
        # for transmission keep arriving after we open); that burst can
        # contain an incidental '@@' before the real announcement, causing
        # read_until() to stop short of it. When that happens (some data
        # arrived but didn't parse), we deliberately do NOT flush the input
        # buffer either -- the real announcement is likely queued right
        # behind what we just read, so the next attempt keeps reading
        # forward through the same stream instead of discarding it.
        #
        # Only a truly empty attempt (nothing arrived at all) is treated as
        # a dead link: that's when we flush (clearing any residual stale
        # bytes) and then explicitly drop/re-raise DTR to force the
        # firmware to see (or re-see) a connection edge and re-announce
        # itself (see check_serial_reconnect() in the firmware) -- nothing
        # is flushed *after* re-raising DTR, since the announcement can
        # arrive within the toggle's own settle time and the same race
        # would just discard it again.
        flag = b''
        for attempt in range(5):
            if attempt > 0 and flag == b'':
                self.ser.reset_input_buffer()
                self.ser.dtr = False
                time.sleep(0.2)
                self.ser.dtr = True
                time.sleep(0.2)
            flag = self._waiting('board_program', timeout=3)
            try:
                parts = flag.decode().split(':')
                board_program = parts[1]
                # Newer firmware appends the board's factory-burned unique
                # ID as a third field (":name:chip_id:@@" -> 4 parts after
                # split); older firmware's ":name:@@" (3 parts) has none.
                chip_id = parts[2] if len(parts) > 3 else None
                break
            except (UnicodeDecodeError, IndexError):
                print(t('comm.board_program_retry', attempt=attempt + 1, raw=flag))
                continue
        else:
            raise RuntimeError(t('comm.board_program_failed', port=self.p.board['device'][0]))
        self.ser.reset_output_buffer()
        self.ser.reset_input_buffer()
        print(f'[INFO] {board_program=} {chip_id=}')
        return board_program, chip_id

    def init_serial(self, marker):
        # Write parameters PC ===> board
        exclusion_list = [
            'title',
            'dir_name',
            'min_peak_dist',
            'time_width',
            'func',
            'struct',
            'one_data_byte',
            'serial_time_interval',
            'real_time_interval',
            'endian']
        dic = {key: val for key, val in self.p.env_set.items() if key not in exclusion_list}
        pc_params = utils.join_dict(dic, ';', '=')
        print(f'[INFO] {pc_params=}')
        self.ser.write(marker)     # b"i"... initialize, b"a" ... ReInitialize (Again)
        self.ser.write(bytes(pc_params, encoding="utf-8"))
        # Wait for the board's 'setparams' response. See connect_serial()
        # for why a truncated/garbled response is retried instead of
        # crashing outright.
        board_params = self._waiting('setparams')
        for attempt in range(3):
            try:
                parsed = self._parse_setparams(board_params)
                break
            except ValueError:
                print(t('comm.setparams_retry', attempt=attempt + 1, raw=board_params))
                if attempt == 2:
                    raise RuntimeError(
                        t('comm.setparams_failed', port=self.p.board['device'][0]))
                self.ser.reset_input_buffer()
                self.ser.write(marker)
                self.ser.write(bytes(pc_params, encoding="utf-8"))
                board_params = self._waiting('setparams')
        print(f'[INFO] {board_params=}')
        self.p.env_set.update(parsed)
        # Turn the variables received from the board into self.<name> attributes
        self.set_self_vars()
        self._build_struct()

    def _set_timeout(self, value):
        """Best-effort self.ser.timeout assignment. Setting pyserial's
        .timeout isn't a plain attribute write -- it triggers a real port
        reconfiguration (termios.tcsetattr under the hood), which can
        itself raise if the device has just disconnected (e.g. right
        after a read already failed with a SerialException, which is
        exactly when get_data_no_write()/get_data_and_write() below try
        to restore the original timeout during cleanup). Silently
        ignored, the same way the reset_*_buffer()/write(b"r") cleanup
        right after this already tolerates a broken port.
        """
        try:
            self.ser.timeout = value
        except (serial.SerialException, OSError, *_TERMIOS_ERRORS):
            pass

    def _steady_state_timeout(self):
        """A read() timeout sized to the board's own configured sample
        interval (self.real_time_interval, always in *microseconds* --
        see any firmware .ino's changeParam()/params["real_time_interval"]),
        instead of the flat default set once in __init__ (16s).

        get_data_no_write()/get_data_and_write() detect the board going
        idle (e.g. a calibration run converging) by a short/empty read
        after self.ser.read()'s own timeout elapses, then shrink the
        timeout so later idle checks are fast. But that shrink only
        happens *after* the first slow detection -- if the user reacts
        (presses Stop, or Test/Run right after caliBrate finishes)
        within that first window, reset()'s th.join() still has to wait
        out however much of the original 16s was left, which is exactly
        the "6 second wait" symptom this fixes. Sizing the timeout to
        the real sample interval up front (generous margin, 1s floor so
        normal jitter never false-triggers, 16s ceiling so a board with
        a genuinely slow configured interval never waits longer than
        before) makes even the *first* idle detection fast.
        """
        try:
            margin = 20 * self.real_time_interval / 1e6
        except (AttributeError, TypeError, ValueError):
            return self.ser.timeout
        return max(1.0, min(margin, 16.0))

    def get_data_no_write(self):
        print(t('comm.thread_no_write_start'))
        warned_idle = False
        original_timeout = self.ser.timeout
        steady_timeout = self._steady_state_timeout()
        self._set_timeout(steady_timeout)
        while self.loop_th:
            try:
                self.ser_data = self.ser.read(self.one_data_size)
            except serial.SerialException as exc:
                # USB disconnect, a brief dropout, etc. Don't crash the
                # thread; proceed to Stop-equivalent cleanup instead.
                print(t('comm.thread_serial_error', err=exc))
                self.loop_th = False
                break
            if len(self.ser_data) != self.one_data_size:
                # A short/empty read (most commonly: the board legitimately
                # stopped sending anything, e.g. a calibration run that
                # finished converging or exhausted calib_max_iters) after
                # self.ser.read()'s own timeout elapsed. Passing this
                # through to convert() would crash on the size mismatch;
                # skip it and keep waiting instead -- the board may resume,
                # and Stop is still the way to end this deliberately.
                if not warned_idle:
                    print(t('comm.thread_short_read', got=len(self.ser_data), expected=self.one_data_size))
                    warned_idle = True
                    self.went_idle = True
                    # reset()'s th.join() (see window.py) blocks the GUI
                    # thread until this loop notices loop_th=False, which
                    # only happens between read() calls -- so once the
                    # board's gone quiet, shrink the read timeout well
                    # below the steady-state one (generous, for real
                    # streaming) so Stop takes effect in about a second
                    # instead of however long that was.
                    self._set_timeout(min(steady_timeout, 1))
                continue
            if warned_idle:
                self._set_timeout(steady_timeout)
            warned_idle = False
            self._data_ready.set()      # to release the initial wait
            self._new_data_event.set()  # notify that new data has arrived
        self._set_timeout(original_timeout)
        try:
            self.ser.reset_output_buffer()
            self.ser.reset_input_buffer()
            self.ser.write(b"r")
        except (serial.SerialException, OSError, *_TERMIOS_ERRORS):
            # If the device has been physically disconnected,
            # termios.tcflush() inside reset_output_buffer() can raise
            # termios.error (a direct subclass of Exception, neither
            # serial.SerialException nor OSError); missing it would crash
            # the thread with an uncaught exception.
            pass
        print(t('comm.thread_no_write_stopped'))

    def get_data_and_write(self, f):
        warned_idle = False
        original_timeout = self.ser.timeout
        steady_timeout = self._steady_state_timeout()
        self._set_timeout(steady_timeout)
        while self.loop_th:
            try:
                self.ser_data = self.ser.read(self.one_data_size)
            except serial.SerialException as exc:
                print(t('comm.thread_serial_error', err=exc))
                self.loop_th = False
                break
            if len(self.ser_data) != self.one_data_size:
                # See get_data_no_write() for why this is skipped rather
                # than passed to convert() (which would crash) or written
                # to the recording (which expects fixed-width frames), and
                # for why the read timeout is shrunk once this happens.
                if not warned_idle:
                    print(t('comm.thread_short_read', got=len(self.ser_data), expected=self.one_data_size))
                    warned_idle = True
                    self.went_idle = True
                    self._set_timeout(min(steady_timeout, 1))
                continue
            if warned_idle:
                self._set_timeout(steady_timeout)
            warned_idle = False
            self._data_ready.set()
            self._new_data_event.set()  # notify that new data has arrived
            f.write(self.ser_data)
        self._set_timeout(original_timeout)
        try:
            self.ser.reset_output_buffer()
            self.ser.reset_input_buffer()
            self.ser.write(b"r")
        except (serial.SerialException, OSError, *_TERMIOS_ERRORS):
            # If the device has been physically disconnected,
            # termios.tcflush() inside reset_output_buffer() can raise
            # termios.error (a direct subclass of Exception, neither
            # serial.SerialException nor OSError); missing it would crash
            # the thread with an uncaught exception.
            pass
        print(t('comm.thread_write_stopped'))

    def convert(self, s):
        # Decode in one shot with struct.unpack_from (C-level, fast)
        raw = self._struct.unpack_from(s)

        # Call the conversion functions directly from the precomputed list
        fun = [f(v) for f, v in zip(self._func_list, raw)]
        out = np.empty(len(fun) + len(raw), dtype=np.float64)
        out[:len(fun)] = fun
        out[len(fun):] = raw
        return out.reshape(1, -1)

    def data_stream(self):
        # self._data_ready/self.ser_data are Board-level state that outlives
        # a single start_read_thread() session (a fresh data_stream()
        # generator is created on every Test/Run/caliBrate button press,
        # but the Event and buffer are the same objects throughout the
        # app's life). If the wire-protocol struct size just changed --
        # e.g. caliBrate appends 3 extra per-sample dpm(u1) fields that
        # Test/Run doesn't send, so one_data_size/_struct differ between
        # them -- self.ser_data can still hold a leftover buffer sized for
        # the *previous* mode at the moment this generator starts, before
        # the reader thread has delivered a first sample in the new size.
        # convert() would then crash on this very first line with a
        # struct.error, permanently killing this generator: every later
        # next(stream) call raises StopIteration instead, which
        # FigureQtPG.update() doesn't guard against, freezing the whole
        # GUI (plot, HR, dpm -- everything) until the next button press.
        # Loop past any stale, wrong-sized buffer instead of trusting
        # whatever self.ser_data happens to hold.
        while True:
            self._data_ready.wait()
            if len(self.ser_data) == self._total_size:
                break
            self._data_ready.clear()
        ser_data0 = self.ser_data
        init_val = self.convert(ser_data0)
        init_val[0][0] = init_val[0][len(self.structure)] = 0
        self.data = np.full((2, len(self.structure) * 2), init_val)
        got_first_sample = False
        while True:
            # Wait on an Event instead of polling. This generator is
            # driven by FigureQtPG.update() (mylib/Qtutils.py), called by
            # window.py's update() -- a slot on a 0ms-interval QTimer,
            # i.e. it runs on the Qt *main* thread. An unbounded wait()
            # here blocks that thread indefinitely once the board goes
            # quiet (e.g. a calibration run converging or reaching
            # calib_max_iters -- see get_data_no_write()/
            # get_data_and_write()), freezing the entire application (no
            # repaints, no button clicks, OS "Not Responding") until data
            # resumes -- a more severe freeze than the reader thread's own
            # shutdown delay, which those methods already handle
            # separately. Bounded once at least one real sample has been
            # yielded, so FigureQtPG.update() can keep assuming the very
            # first value this generator ever yields is real data, never
            # the "nothing new yet" sentinel below.
            timeout = 0.2 if got_first_sample else None
            if not self._new_data_event.wait(timeout=timeout):
                yield None
                continue
            self._new_data_event.clear()  # block until the next data
            if self.ser_data != ser_data0:
                ser_data0 = self.ser_data
                self.data[0] = self.data[1]
                self.data[1] = self.convert(ser_data0)
                got_first_sample = True
                yield self.data
