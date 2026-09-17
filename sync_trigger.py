#!/usr/bin/env python3
"""Send a "start", "stop", or "quit" command to every currently-running
get.py board window and get_camera.py window that was launched with
-sync.

Meant to be bound to a single OS-level global keyboard shortcut (in your
OS's own settings -- Python cannot reliably grab a system-wide shortcut
across platforms), so that one keypress starts (or stops, or closes)
every currently-open, sync-enabled window at once. See mylib/sync.py and
README.md's "Starting several windows together" section.

    python sync_trigger.py start
    python sync_trigger.py stop
    python sync_trigger.py quit        # cleanly close every sync-enabled window
    python sync_trigger.py --list      # show what's currently listening
"""

import argparse
import sys

from mylib.sync import list_listeners, send_trigger


def main():
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('command', nargs='?', choices=['start', 'stop', 'quit'],
                        help='command to send to every sync-enabled window')
    parser.add_argument('--list', action='store_true',
                        help='list currently registered sync listeners and exit')
    args = parser.parse_args()

    if args.list:
        listeners = list_listeners()
        if not listeners:
            print('No sync-enabled windows are currently running.')
        for entry in listeners:
            print(f"pid={entry['pid']}  port={entry['port']}  {entry['label']}")
        return

    if not args.command:
        parser.error('a command (start/stop/quit) or --list is required')

    n = send_trigger(args.command)
    print(f"Sent '{args.command}' to {n} window(s).")
    if n == 0:
        print('(No windows were listening. Launch them with -sync to opt in.)')


if __name__ == '__main__':
    sys.exit(main())
