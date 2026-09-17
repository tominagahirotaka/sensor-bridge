#!/usr/bin/env python3
"""Launch get.py and get_camera.py together, both with -sync, so that
sync_trigger.py can start/stop/quit them together afterward. See
README.md's "Starting several windows together" section.

    python launch_synced.py
"""

import subprocess
import sys


def main():
    get_proc = subprocess.Popen([sys.executable, 'get.py', '-sync'])
    camera_proc = subprocess.Popen([sys.executable, 'get_camera.py', '-sync'])
    print(f'Launched get.py (pid={get_proc.pid}) and get_camera.py (pid={camera_proc.pid}), both with -sync.')
    print("Note: get.py itself spawns one further process per connected "
          "board (see get.py's main()), so these two PIDs are the "
          "launchers, not necessarily the sync-registered windows themselves.")
    print("Once the windows are open, run 'python sync_trigger.py --list' "
          "to confirm they registered, then 'python sync_trigger.py start' "
          "/ 'stop' / 'quit' to control them all together.")


if __name__ == '__main__':
    main()
