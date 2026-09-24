#!/usr/bin/env python3
"""Unattended per-unit absolute-time calibration: launches get.py, records
for a long duration with no supervision needed, marks a checkpoint near
the end, stops, computes that board's clock ppm_offset from the
recording's own header, and writes it into calibration.json.

Why this works without any extra hardware: get.py already records the
PC's wall-clock time both when a recording starts (Header.time
['start_time']) and at every mArk/checkpoint press (Header.time
['check_points'], alongside the board's own device-reported elapsed
time at that same instant) -- see mylib/communicate.py's
check_points(). This script just drives that existing mechanism by
remote control (mylib/sync.py's run/mark/stop/quit, the same channel
sync_trigger.py uses) instead of a human sitting at the keyboard, and
uses the pair furthest from start_time (the mark near the end) to
compute the board's clock offset. See calibration.json's "_readme" for
the ppm_offset sign convention this writes.

CORRECTED FOR A SUBTLE BIAS: check_points()'s device-side value is the
timestamp of the most recently *arrived sensor sample* at mark time, not
"the device's time right now" -- it only updates once per sample, so it
can lag the true mark instant by up to one full sampling interval
(1/ODR), while the paired wall-clock value is accurate. Left uncorrected
this is a one-sided bias (always makes the device side look slower than
it is), not just noise. This script measures the recording's own mean
sampling interval (the same way scripts/measure_timing_precision.py
does) and adds half of it to the device-side elapsed time -- the
expected value of that staleness under a uniform arrival-time
assumption -- leaving only a much smaller residual random uncertainty.

The real-world wait itself cannot be shortened -- detecting a ppm-level
clock offset requires the accumulated drift (duration x ppm_offset) to
exceed measurement noise, so a longer recording gives a more trustworthy
number -- but you don't have to watch it: start this and walk away.
Driving the mark by script (rather than a human clicking a button) also
removes human reaction-time noise (~0.1-0.5s) from the measurement,
replacing it with this script's own scheduling latency (milliseconds),
which is one more reason this can be trusted at shorter durations than
a manually-marked session would need.

CAUTION: mylib/sync.py's run/mark/stop/quit commands broadcast to every
currently sync-enabled window, not just the one this script launches --
this script refuses to run if any other sync-enabled window is already
registered, rather than risk sending commands into someone else's
session.

Also logs the board's on-chip temperature (RP2040/RP2350's built-in
sensor -- die temperature, not the crystal oscillator's own temperature,
but a useful proxy) immediately before 'run', and again right after the
end-of-run 'mark' but still before 'stop' (NOT after -- confirmed on
real hardware that get.py's Stop handler writes the recording's .cpt
header file and nothing rewrites it afterward, so anything logged
post-stop never makes it into the saved file). The second query does
land a moment before streaming actually stops (a ~1ms ADC settle/read
that would otherwise show up as a one-off irregular sampling interval
if sent mid-stream), but only after the mark the ppm_offset calculation
actually uses, so it can't affect that result. Stored per-run in
calibration.json so a temperature
correlation across repeated runs can be checked directly.

Usage:
    python3 scripts/calibrate_timing.py LIS3DH --duration 1800
    python3 scripts/calibrate_timing.py LIS3DH --duration 1800 --dry-run
"""
import argparse
import datetime
import glob
import json
import os
import re
import subprocess
import sys
import threading
import time

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO_ROOT)
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import numpy as np  # noqa: E402

import mylib.calibration as calib  # noqa: E402
import mylib.fileIO as FIO  # noqa: E402
import mylib.utils as utils  # noqa: E402
from mylib.sync import list_listeners, send_trigger  # noqa: E402

STARTUP_TIMEOUT_S = 30
POST_MARK_SETTLE_S = 2
POST_STOP_SETTLE_S = 2
POST_TEMP_SETTLE_S = 1
MIN_RECOMMENDED_DURATION_S = 300


def wait_for_listener(timeout):
    """Wait for any sync listener to appear. Confirmed on real hardware
    (2026-09-24) that get.py's own launcher process (subprocess.Popen's
    pid) is never the one that registers -- get.py's main() spawns a
    child via multiprocessing (see get.py's Process(...) call) for each
    connected board, and it's that child's window that creates the
    SyncListener, under a different pid entirely. Matching against the
    launcher's pid therefore never succeeded and this always timed out,
    even though a listener reliably showed up within ~2s in practice.
    Safe to accept *any* listener here rather than matching a specific
    pid, since main() already refuses to run if any listener existed
    before this launch (see the pre_existing check)."""
    t0 = time.monotonic()
    while time.monotonic() - t0 < timeout:
        if list_listeners():
            return True
        time.sleep(0.2)
    return False


_TEMP_LINE_RE = re.compile(r"query_temperature\(\) -> temp_c=(None|[-\d.]+)")


def read_subprocess_output(proc, temp_readings):
    """Continuously drain proc.stdout (get.py's own console output,
    merged stderr) for the whole life of the subprocess: echoes each
    line prefixed "[get.py] ", and appends any temperature reading
    (float, or None on failure) found in a
    "[INFO] query_temperature() -> temp_c=..." line, in the order they
    appear, to temp_readings.

    Why read temperature this way instead of from the saved recording's
    header (which mylib/communicate.py's query_temperature() *does* also
    log into): get.py's Stop handler writes the .cpt header file once,
    and nothing rewrites it afterward, so a temperature queried after
    'stop' (the only time it's safe to query at all -- see the 'temp'
    comment in main()) never reaches the saved file. Reading it directly
    off get.py's own stdout sidesteps that entirely.

    Must run in its own thread for the whole subprocess lifetime, not
    just read after the fact: with stdout=PIPE, an unread pipe fills up
    and blocks the child's next write once full, which would silently
    stall a long unattended recording if nothing were draining it
    throughout."""
    for line in proc.stdout:
        line = line.rstrip('\n')
        print(f'[get.py] {line}')
        m = _TEMP_LINE_RE.search(line)
        if m:
            temp_readings.append(None if m.group(1) == 'None' else float(m.group(1)))


def find_new_dat_file(dir_name, since):
    candidates = [f for f in glob.glob(os.path.join(dir_name, '*.dat'))
                  if os.path.getmtime(f) >= since]
    if not candidates:
        return None
    return max(candidates, key=os.path.getmtime)


def mean_sample_interval(dat_file):
    """Mean device-reported sampling interval (seconds) for dat_file,
    decoded the same way scripts/measure_timing_precision.py does. Used
    to correct check_points()'s mark-timing bias -- see the module
    docstring."""
    import plot as plotmod
    from mylib.plot_utils.reading import ReadData

    sys.argv = ['plot.py', '-f', dat_file]
    args = plotmod.parse_args()
    rd = ReadData(args)
    return float(np.diff(rd.data_t[0]).mean())


def main():
    parser = argparse.ArgumentParser(description=__doc__,
                                      formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('ini_name', help='board config to calibrate, e.g. LIS3DH '
                                          '(matches <ini_name>.ini)')
    parser.add_argument('--duration', type=float, default=1800,
                         help='seconds to record before marking and stopping '
                              '(default: 1800 = 30 min; longer gives a more '
                              'trustworthy ppm_offset)')
    parser.add_argument('--dry-run', action='store_true',
                         help="compute and print the result but don't write calibration.json")
    args = parser.parse_args()

    if args.duration < MIN_RECOMMENDED_DURATION_S:
        print(f"[WARN] --duration {args.duration}s is quite short; the resulting "
              f"ppm_offset may be noisy. {MIN_RECOMMENDED_DURATION_S}s+ is recommended.")

    ini_path = os.path.join(REPO_ROOT, f'{args.ini_name}.ini')
    if not os.path.isfile(ini_path):
        sys.exit(f"{ini_path} not found.")
    env_set, _code = utils.read_setting_ini(ini_path)
    dir_name = os.path.join(REPO_ROOT, env_set.get('dir_name', 'data'))

    pre_existing = list_listeners()
    if pre_existing:
        sys.exit("Another sync-enabled window is already running "
                 f"({len(pre_existing)} listener(s) registered). This script's "
                 "run/mark/stop/quit commands would be broadcast to it too -- "
                 "close it first (or quit it via sync_trigger.py) and re-run.")

    launch_time = datetime.datetime.now()
    print(f"Launching: python3 get.py -i {ini_path} -sync")
    # stdout/stderr piped (not inherited) so this script can read
    # get.py's own "[INFO] query_temperature() -> temp_c=..." lines
    # directly -- see read_subprocess_output()'s docstring for why
    # temperature can't just be read back from the saved recording.
    # PYTHONUNBUFFERED=1 so those lines arrive promptly instead of
    # sitting in a block-buffered pipe until the process exits.
    child_env = dict(os.environ, PYTHONUNBUFFERED='1')
    proc = subprocess.Popen([sys.executable, 'get.py', '-i', ini_path, '-sync'],
                            cwd=REPO_ROOT, env=child_env, stdout=subprocess.PIPE,
                            stderr=subprocess.STDOUT, text=True, bufsize=1)
    temp_readings = []
    reader_thread = threading.Thread(target=read_subprocess_output,
                                     args=(proc, temp_readings), daemon=True)
    reader_thread.start()

    try:
        if not wait_for_listener(STARTUP_TIMEOUT_S):
            sys.exit(f"get.py did not register as a sync listener within "
                     f"{STARTUP_TIMEOUT_S}s (board not connected, or the window "
                     "failed to open). Check the get.py output above.")

        # Queried while genuinely idle (before 'run' even starts).
        print("Querying on-chip temperature before starting ('temp') ...")
        send_trigger('temp')
        time.sleep(POST_TEMP_SETTLE_S)

        print("Board connected. Starting recording ('run') ...")
        send_trigger('run')

        print(f"Recording for {args.duration:.0f}s -- safe to leave this running "
              f"unattended.")
        time.sleep(args.duration)

        print("Marking checkpoint ('mark') ...")
        send_trigger('mark')
        time.sleep(POST_MARK_SETTLE_S)

        print("Stopping ('stop') ...")
        send_trigger('stop')
        time.sleep(POST_STOP_SETTLE_S)

        # Deliberately AFTER 'stop' has fully settled, not before or
        # during: sending 'T' while the board is actively streaming
        # samples was tested on real hardware and found to corrupt the
        # recording outright (confirmed via a wildly wrong
        # mean_sample_interval and ppm_offset) -- the firmware's 'T'
        # reply is plain text interleaved into what the PC side's reader
        # thread strictly expects to be fixed-size binary sample frames,
        # desyncing frame alignment for the rest of the stream. This is
        # a real protocol-level hazard, not just a ~1ms timing nuisance
        # as originally assumed -- 'temp' must never be sent while a
        # board is recording. Also can't just move back before 'stop'
        # and rely on the saved .cpt for it, the way the pre-'run'
        # reading is recoverable from the header: get.py's Stop handler
        # writes the recording's .cpt header file and nothing rewrites
        # it afterward, so anything queried post-stop never reaches the
        # saved file -- hence reading it directly off get.py's own
        # stdout instead (see read_subprocess_output()).
        print("Querying on-chip temperature after stopping ('temp') ...")
        send_trigger('temp')
        time.sleep(POST_TEMP_SETTLE_S)

        print("Closing window ('quit') ...")
        send_trigger('quit')
        try:
            proc.wait(timeout=15)
        except subprocess.TimeoutExpired:
            print("[WARN] get.py did not exit after 'quit'; leaving it running "
                  "(check on it manually).")
    except BaseException:
        # Best-effort cleanup so an interrupted run (Ctrl+C, an exception
        # above) doesn't leave a board silently recording forever.
        send_trigger('stop')
        send_trigger('quit')
        raise

    dat_file = find_new_dat_file(dir_name, launch_time.timestamp())
    if dat_file is None:
        sys.exit(f"No new .dat file appeared under {dir_name}/ -- recording may "
                 "not have started (check get.py's output above).")
    print(f"Recording: {dat_file}")

    header = FIO.FileIO().read_open(dat_file)
    sample_interval = mean_sample_interval(dat_file)
    print(f"mean_sample_interval={sample_interval * 1000:.4f}ms "
          f"(mark-timing bias correction: +{0.5 * sample_interval * 1000:.4f}ms)")
    result = compute_ppm_offset(header, sample_interval)
    print(f"chip_id={result['chip_id']}")
    print(f"wall_elapsed={result['wall_elapsed']:.3f}s  "
          f"device_elapsed={result['device_elapsed']:.3f}s")
    print(f"ppm_offset={result['ppm_offset']:+.2f}")

    # Best-effort: None for either/both if the board's firmware doesn't
    # support 'T' (see Board.query_temperature()) -- never blocks writing
    # the calibration result itself. Read from temp_readings (captured
    # off get.py's own stdout by read_subprocess_output() as it ran),
    # not from the saved recording's header -- see that function's
    # docstring for why the header can't be used for the second reading.
    temp_start = temp_readings[0] if len(temp_readings) > 0 else None
    temp_end = temp_readings[1] if len(temp_readings) > 1 else None
    if temp_start is not None:
        print(f"on-chip temperature: start={temp_start:.2f}C"
              + (f" end={temp_end:.2f}C" if temp_end is not None else " (no end reading)"))
    else:
        print("on-chip temperature: not available (older firmware without 'T'?)")

    if args.dry_run:
        print("(--dry-run: calibration.json not modified)")
        return

    entry = write_calibration_entry(result, dat_file, temp_start, temp_end)
    all_offsets = [r['ppm_offset'] for r in entry['runs']]
    print(f"Wrote calibration.json: {result['chip_id']} -> "
          f"ppm_offset={entry['ppm_offset']:+.2f} "
          f"(mean of {entry['n_runs']} run(s); this run: {result['ppm_offset']:+.2f}; "
          f"range so far: {min(all_offsets):+.2f} to {max(all_offsets):+.2f})")


DEFAULT_CALIBRATION_README = (
    'Optional per-unit absolute-time calibration. Each key under '
    "'boards' is one physical board's factory-burned unique ID, "
    "exactly as reported in this project's serial handshake "
    "(visible in the console as '[INFO] board_program=... "
    "chip_id=...' when a board connects, or in a .dat file's "
    "header). 'ppm_offset' is how many parts-per-million the "
    "device's reported elapsed time exceeds true elapsed time, as "
    "measured by comparing the device's own reported duration "
    'against an independent time reference (e.g. an '
    'NTP-synchronized PC clock, over a long recording -- see '
    'README.md, or run scripts/calibrate_timing.py). Positive '
    "means the device's clock runs fast. plot.py applies "
    'corrected_time = raw_time / (1 + ppm_offset / 1e6) to any '
    'recording from a board listed here; boards with no entry are '
    'left uncorrected (this is the default -- calibration is '
    'opt-in, per unit, and this file starts empty). This is a '
    'per-unit measurement, not a general claim about the board '
    "type -- see README.md's timing-precision discussion for why. "
    "A single run's ppm_offset is noisy (see calibrate_timing.py's "
    "module docstring), so scripts/calibrate_timing.py accumulates "
    "repeated runs against the same board in 'runs' rather than "
    "overwriting; the top-level 'ppm_offset' it writes is the mean "
    "across 'runs' ('n_runs' of them), which is what plot.py actually "
    "reads -- run it several times (ideally at different times/room "
    "temperatures) rather than relying on a single run. Each run entry "
    "also records 'temp_c_start'/'temp_c_end' -- the board's own "
    "on-chip die temperature (Celsius) immediately before/after that "
    "run, queried only while idle so it never perturbs the recording's "
    "sampling cadence (null if unavailable, e.g. older firmware) -- so "
    "ppm_offset can be checked for a temperature correlation across "
    "runs directly, instead of only inferring it from varying the time "
    "of day.")


def compute_ppm_offset(header, sample_interval=None):
    """header: a communicate.Header (or anything with the same .time/
    .board shape) from a completed calibration recording. sample_interval:
    the recording's mean device-reported sampling interval (seconds), if
    known -- see mean_sample_interval(). Used to correct check_points()'s
    mark-timing bias (see module docstring); pass None to skip the
    correction (e.g. in tests with synthetic data that has no such bias).
    Returns {'chip_id', 'wall_elapsed', 'device_elapsed', 'ppm_offset'},
    or exits with a clear message if the recording is unusable for
    calibration."""
    start_time = header.time.get('start_time')
    check_points = header.time.get('check_points', [])
    chip_id = header.board.get('chip_id')

    if start_time is None or not check_points:
        sys.exit("Recording has no start_time/check_points -- the mark may not "
                 "have registered. Nothing written; try again.")
    if chip_id is None:
        sys.exit("This board's firmware doesn't report a chip_id (older "
                 "firmware?) -- can't key a calibration.json entry. Reflash "
                 "with scripts/build_firmware.py's current firmware first.")

    lap_time_device, wall_clock_at_mark = check_points[-1]
    wall_elapsed = (wall_clock_at_mark - start_time).total_seconds()
    device_elapsed = float(lap_time_device)
    if sample_interval is not None:
        # check_points()'s device-side value is the last-arrived sample's
        # timestamp, not "device time right now" -- it can lag the true
        # mark instant by up to one full sample interval. Add the
        # expected (mean) staleness under a uniform arrival-time
        # assumption to turn that one-sided bias into a smaller,
        # zero-mean residual uncertainty.
        device_elapsed += 0.5 * sample_interval
    ppm_offset = (device_elapsed - wall_elapsed) / wall_elapsed * 1e6
    return {'chip_id': chip_id, 'wall_elapsed': wall_elapsed,
            'device_elapsed': device_elapsed, 'ppm_offset': ppm_offset}


def write_calibration_entry(result, dat_file, temp_start=None, temp_end=None):
    """Append this run to result['chip_id']'s run history in
    calibration.json (creating it if this is the first run for that
    board) and recompute its reported ppm_offset as the mean across all
    runs so far -- repeated runs against the same physical board
    (same chip_id) accumulate rather than overwrite each other, since a
    single run's ppm_offset is noisy enough that averaging several is
    recommended (see README.md). Preserves every other board's existing
    entry. temp_start/temp_end (on-chip die temperature, Celsius, from
    Board.query_temperature() before/after this run -- None if
    unavailable) are stored alongside the run so ppm_offset can later be
    inspected for a temperature correlation across runs, rather than
    only varying by time-of-day as a weak proxy. Returns the (possibly
    newly created) entry for this chip_id."""
    if os.path.isfile(calib.CALIBRATION_PATH):
        with open(calib.CALIBRATION_PATH, encoding='utf-8') as f:
            calibration_data = json.load(f)
        calibration_data.setdefault('boards', {})
    else:
        calibration_data = {'_readme': DEFAULT_CALIBRATION_README, 'boards': {}}

    boards = calibration_data['boards']
    entry = boards.setdefault(result['chip_id'], {'runs': []})
    entry['runs'].append({
        'ppm_offset': result['ppm_offset'],
        'measured_from': os.path.relpath(dat_file, REPO_ROOT),
        'measured_at': datetime.datetime.now().isoformat(timespec='seconds'),
        'wall_clock_elapsed_s': result['wall_elapsed'],
        'temp_c_start': temp_start,
        'temp_c_end': temp_end,
    })
    entry['n_runs'] = len(entry['runs'])
    entry['ppm_offset'] = sum(r['ppm_offset'] for r in entry['runs']) / entry['n_runs']

    with open(calib.CALIBRATION_PATH, 'w', encoding='utf-8') as f:
        json.dump(calibration_data, f, indent=2, ensure_ascii=False)
        f.write('\n')
    return entry


if __name__ == '__main__':
    main()
