#!/usr/bin/env python3
"""
sensor-bridge: データ取得モジュール
Raspberry Pi Pico / Pico W からバイナリデータを取得する
"""

import argparse
import multiprocessing
import os
import sys

from PyQt5.QtGui import QIcon
from PyQt5.QtWidgets import QApplication

import mylib.communicate as comm
import mylib.i18n as i18n
import mylib.window as win
from mylib.i18n import t
from version import __version__


def make_window(argv, args, board):
    i18n.set_language(args.lang)                  # re-apply in this (possibly spawned) process
    rcv = comm.Receive(args, board)              # data receive object
    app = QApplication(argv)                     # ApplicationWindow object
    app.setWindowIcon(QIcon('icon.png'))
    window = win.ApplicationWindow(rcv, args)  # kept alive by this ref; PyQt closes GC'd windows
    sys.exit(app.exec_())                        # ApplicationWindow excution


def main():
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
    args = parser.parse_args()
    i18n.set_language(args.lang)

    boards = comm.search_connected_boards()     # List the connected boards
    print(t('get.connected_boards', boards=boards))
    for board in boards:                        # multi processing
        multiprocessing.Process(target=make_window, args=(sys.argv, args, board)).start()


if __name__ == '__main__':
    main()
