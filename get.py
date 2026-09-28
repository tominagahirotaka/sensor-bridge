#!/usr/bin/env python3
"""
sensor-bridge: data acquisition module
Acquires binary data from a Raspberry Pi Pico / Pico W.
"""

import argparse
import multiprocessing
import os
import sys

from timed_import import timed_import

# Fixed position/total for every heavy import this file times -- see
# plot.py's own _TOTAL/timed_import usage for why (antivirus real-time
# scanning of a compiled extension, or a slow network-mounted profile
# dir, can make one of these take a very long time on some Windows lab
# machines; these numbered, timestamped lines make it possible to tell
# which one, instead of the terminal just silently sitting there).
_TOTAL = 4

with timed_import('PyQt5', 1, _TOTAL):
    from PyQt5.QtGui import QIcon
    from PyQt5.QtWidgets import QApplication
# mylib/__init__.py itself imports matplotlib (for font setup), so this
# first mylib.* import is the one that pays for that -- timing it here
# rather than leaving it silently bundled into whatever imported mylib
# first.
with timed_import('mylib.communicate (+ matplotlib font setup)', 2, _TOTAL):
    import mylib.communicate as comm
with timed_import('mylib.i18n', 3, _TOTAL):
    import mylib.i18n as i18n
    from mylib.i18n import t
with timed_import('mylib.window', 4, _TOTAL):
    import mylib.window as win

from version import __version__


def make_window(argv, args, board, win_index=0, num_boards=1):
    i18n.set_language(args.lang)                  # re-apply in this spawned process
    rcv = comm.Receive(args, board, num_boards)   # data receive object
    # argv[0] becomes the X11 WM_CLASS (verified via xprop); Qt's
    # setDesktopFileName() only affects the Wayland app-id, so both are
    # needed to match sensor-bridge-get.desktop's StartupWMClass on either
    # session type and get the dock/taskbar icon to show.
    app = QApplication(['sensor-bridge-get'] + list(argv[1:]))
    app.setDesktopFileName('sensor-bridge-get')
    app.setWindowIcon(QIcon('icon.png'))
    # win_index staggers this window's position when multiple boards are
    # connected at once (each board runs in its own process, so they can't
    # share a running counter); a single board still centers exactly as before.
    window = win.ApplicationWindow(rcv, args, win_index)  # kept alive by this ref; PyQt closes GC'd windows
    sys.exit(app.exec_())                        # ApplicationWindow excution


def main():
    # 'spawn' gives each board its own fresh interpreter instead of a forked
    # copy of this one. On Linux (where 'fork' is the historical default),
    # opening a board's serial port in a forked child was observed on real
    # hardware to leave DTR/termios handling broken for that port -- a fresh
    # board_program handshake (see Board.open_serial()) would hang or return
    # garbage even though the exact same code worked every time unforked.
    # macOS/Windows already default to 'spawn', so this only changes Linux.
    multiprocessing.set_start_method('spawn')

    # --lang must be resolved before the parser is built so --help itself is localized.
    i18n.set_language(i18n.resolve_lang_from_argv(sys.argv)
                      or os.environ.get('SENSOR_BRIDGE_LANG'))

    parser = argparse.ArgumentParser(description=t('get.description'))
    parser.add_argument(
        '-v',
        '--version',
        action="version",
        version=f"%(prog)s {__version__}",
        help=t('help.version'))
    parser.add_argument('-i', '--init', help=t('help.init'))
    parser.add_argument('-s', '--style', help=t('help.style'))
    parser.add_argument('-f', '--fullscreen', action='store_true', help=t('help.fullscreen'))
    parser.add_argument('-d', '--Debug', action='store_true', help=t('help.debug'))
    parser.add_argument('-lang',
                        '--lang',
                        choices=i18n.SUPPORTED_LANGS,
                        default=i18n.get_language(),
                        help=t('help.lang',
                               langs='/'.join(i18n.SUPPORTED_LANGS)))
    parser.add_argument('-sync', '--sync', action='store_true', help=t('help.sync'))
    args = parser.parse_args()
    i18n.set_language(args.lang)

    boards = comm.search_connected_boards()     # List the connected boards
    print(t('get.connected_boards', boards=boards))
    for win_index, board in enumerate(boards):  # multi processing
        multiprocessing.Process(
            target=make_window, args=(sys.argv, args, board, win_index, len(boards))).start()


if __name__ == '__main__':
    main()
