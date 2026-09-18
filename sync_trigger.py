#!/usr/bin/env python3
"""Send a "run", "test", "calibrate", "stop", "mark", or "quit" command to
every currently-running get.py board window and get_camera.py window that
was launched with -sync. Command names match each board's own button
labels (Run/Test/caliBrate/Stop/mArk, see e.g. DPG_X95840W.ini's panel1);
get_camera.py windows only understand run/stop/mark/quit and simply
ignore test/calibrate, the same as any other unrecognized command.

Meant to be bound to a single OS-level global keyboard shortcut (in your
OS's own settings -- Python cannot reliably grab a system-wide shortcut
across platforms), so that one keypress runs (or stops, marks, or closes)
every currently-open, sync-enabled window at once. See mylib/sync.py and
README.md's "Starting several windows together" section.

    python sync_trigger.py run
    python sync_trigger.py test
    python sync_trigger.py calibrate   # only meaningful for caliBrate-capable boards
    python sync_trigger.py stop
    python sync_trigger.py mark        # record a checkpoint in every running window
    python sync_trigger.py quit        # cleanly close every sync-enabled window
    python sync_trigger.py --list      # show what's currently listening
    python sync_trigger.py             # no command -> opens a small button GUI instead
"""

import argparse
import sys

from mylib.sync import list_listeners, send_trigger

COMMANDS = ['calibrate', 'test', 'run', 'mark', 'stop', 'quit']


def _send(command):
    n = send_trigger(command)
    print(f"Sent '{command}' to {n} window(s).")
    if n == 0:
        print('(No windows were listening. Launch them with -sync to opt in.)')
    return n


def run_gui():
    # Imported lazily: sync_trigger.py's CLI mode (the tool's main,
    # documented use case -- bound to an OS-level global hotkey) has no
    # need for PyQt5 to be importable, e.g. in a minimal/headless
    # environment that only ever runs it non-interactively.
    from PyQt5.QtGui import QIcon
    from PyQt5.QtWidgets import (QApplication, QHBoxLayout, QMainWindow,
                                 QPushButton, QStatusBar, QWidget)

    class TriggerWindow(QMainWindow):
        def __init__(self):
            super().__init__()
            self.setWindowTitle('sensor-bridge sync trigger')
            self.status = QStatusBar()
            self.setStatusBar(self.status)
            layout = QHBoxLayout()
            for command in COMMANDS:
                btn = QPushButton(command.capitalize())
                btn.clicked.connect(lambda checked=False, c=command: self.send(c))
                layout.addWidget(btn)
            central = QWidget()
            central.setLayout(layout)
            self.setCentralWidget(central)

        def send(self, command):
            n = _send(command)
            self.status.showMessage(f"Sent '{command}' to {n} window(s).", 3000)

    app = QApplication(['sensor-bridge-sync-trigger'])
    app.setDesktopFileName('sensor-bridge-sync-trigger')
    app.setWindowIcon(QIcon('icon.png'))
    window = TriggerWindow()
    window.show()
    sys.exit(app.exec_())


def main():
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('command', nargs='?', choices=COMMANDS,
                        help='command to send to every sync-enabled window; '
                             'omit to open a button GUI instead')
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
        run_gui()
        return

    _send(args.command)


if __name__ == '__main__':
    sys.exit(main())
