#!/usr/bin/env python3
"""Launch get.py and get_camera.py together, both with -sync, so that
sync_trigger.py can run/stop/mark/quit them together afterward. See
README.md's "Starting several windows together" section.

By default, every detected camera is opened (get_camera.py -a), not just
one -- pass -c to open a single specific camera index instead, matching
get_camera.py's own -c.

    python launch_synced.py
    python launch_synced.py -c 1
"""

import argparse
import subprocess
import sys


def main():
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('-c', '--camera', type=int, default=None,
                        help='open only this one camera index, instead of every '
                             'detected camera (get_camera.py -a)')
    args = parser.parse_args()

    camera_args = ['-sync']
    camera_args += ['-c', str(args.camera)] if args.camera is not None else ['-a']

    get_proc = subprocess.Popen([sys.executable, 'get.py', '-sync'])
    camera_proc = subprocess.Popen([sys.executable, 'get_camera.py'] + camera_args)
    print(f'Launched get.py (pid={get_proc.pid}) and get_camera.py (pid={camera_proc.pid}), both with -sync.')
    print("Note: get.py and get_camera.py -a each spawn one further "
          "process per connected board/detected camera (see their own "
          "main()s), so these two PIDs are the launchers, not necessarily "
          "the sync-registered windows themselves.")
    print("Once the windows are open, run 'python sync_trigger.py --list' "
          "to confirm they registered, then 'python sync_trigger.py run' "
          "/ 'test' / 'calibrate' / 'stop' / 'mark' / 'quit' to control "
          "them all together (or 'python sync_trigger.py' with no "
          "command for a button GUI).")


if __name__ == '__main__':
    main()
