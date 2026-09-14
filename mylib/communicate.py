#!/usr/bin/env python3
"""USB-serial link to the Pico/Pico W board: board discovery, the
handshake protocol (parameters + binary 'struct' description), and the
background thread that streams decoded samples for get.py's GUI."""

import datetime
import json
import os
import platform
import struct
import threading
import time

import numpy as np
import serial.tools.list_ports

import mylib.fileIO as FIO
import mylib.i18n as i18n
import mylib.utils as utils
from mylib.debug_utils import debug_print
from mylib.i18n import t


class Header:
    def __init__(self):
        self.board = {}
        self.subject = {}
        self.time = {}
        self.machine = platform.uname()._asdict()                 # PC情報取得


class ReceiveCommon:
    def __init__(self, args, board):
        self.p = Header()                 # Instance of Header class (保存ファイルの先頭に情報を書き込む為のObject)
        self.init_flag, self.write_flag = False, False        # set flags
        self.p.board['device'] = board
        self.board = Board(self.p, args, True)        # Instance of Board class
        self.board.loop_th = True         # Thread loop
        board_program = self.board.open_serial()      # open serial & get board_program name
        ini_path = i18n.resolve_localized_path(
            board_program + '.ini')  # `_jp.ini` sibling when --lang ja
        if os.path.isfile(ini_path):                  # 測定環境情報取得
            self.p.env_set, self.code = utils.read_setting_ini(ini_path)
        else:
            print(t('comm.ini_missing_use_default', ini=board_program + '.ini'))
            self.p.env_set, self.code = utils.read_setting_ini(
                i18n.resolve_localized_path('default.ini'))
        if args.init is not None:
            print(t('comm.additional_init', init=args.init))
            env_set, code = utils.read_setting_ini(args.init)
            self.p.env_set.update(env_set)
            self.code.update(code)
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

    # USB読み込み専用thread開始
    def start_read_thread(self):
        if self.write_flag:
            self.file = FIO.FileIO()            # instance of fileIO class
            self.file.write_open(self.p)        # dataファイルopen(書き出し)
            self.th = threading.Thread(
                target=self.board.get_data_and_write, args=(
                    self.file.fwrite,))  # Thread設定
        else:
            print(t('comm.not_writing'))
            self.th = threading.Thread(target=self.board.get_data_no_write)  # Thread設定
        # Thread開始
        self.th.setDaemon(True)
        self.th.start()
        # Thread開始時点での時刻を取得
        self.p.time['th_start_time'] = datetime.datetime.now()
        # data stream(update関数が,この関数内yield文により順にデータを取得する)
        self.stream = self.board.data_stream()

    def check_points(self):
        now = datetime.datetime.now()
        lap_time = self.board.data[-1][0]
        self.p.time['check_points'].append([lap_time, now])
        self.check_point_txt = f"CP.{len(self.p.time['check_points']):03d}  {lap_time:.2f}(sec)"
        print(f'[INFO] {self.check_point_txt=}, {now=}')


class Receive(ReceiveCommon):
    def __init__(self, args, board):
        super().__init__(args, board)

    # 測定開始(Qt)
    def start_running(self, marker):
        # USB 接続, Command送出し、戻ってきたParameterを設定
        # b"s"... start or test, b"c"... calibration
        self.board.connect_serial(marker)
        self.board.ser.read_until(b'OK\r\n')                 # Flush until OK\r\n
        self.p.time['start_time'] = datetime.datetime.now()  # 測定開始時間取得
        self.start_read_thread()                             # Start thread

    # Send b'r' (Stop) to Board
    def stop_running(self):
        self.board.connect_serial(b'r')                      # USB 接続, Command b'r' (Stop)

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
    return [list(usb) for usb in list(dict.fromkeys(boards))]   # ダブりを削除


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
            self.ser_data = None          # 明示的にNoneで初期化
            self._data_ready = threading.Event()
            self._new_data_event = threading.Event()

            print(f'[INFO] {self.ser.port=}')

    def _build_struct(self):
        """structureからstruct.Structを事前コンパイル"""
        # self.endianの実際の値を確認
        # 'little' → '<', 'big' → '>'
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
            self._func_list.append(self.func[st[2]][0])  # 関数を直接リストに

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
        for s in [key + '=' + str(val) for key, val in self.p.env_set.items()]:
            if 'struct' in s:
                continue
            try:
                exec('self.' + s, locals(), globals())
            except NameError:
                if ',' in s:
                    cmd_txt = 'self.' + s.replace('=', '=("').replace(',', '","') + '")'
                    if s[-1] == ',':
                        cmd_txt = cmd_txt[:-3] + ')'
                    debug_print(self.args, f'{cmd_txt=}')
                    exec(cmd_txt)
                else:
                    exec('self.' + s.replace('=', '=\"') + '\"', locals(), globals())
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

    def _waiting(self, ch):
        while not self.ser.inWaiting() > 0:
            time.sleep(0.001)  # 1ms 待ってCPU解放

        u_atmark = self.ser.read_until(b'@@')              # Flush buffer until @@
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

    def connect_serial(self, marker):
        self.ser.write(marker)  # b"s"... start or test, b"c"... calibration
        self.ser.reset_output_buffer()
        self.ser.reset_input_buffer()
        if marker == b'r':
            return
        # boardからの応答を待つ
        board_params = self._waiting('setparams')
        self.p.env_set.update(dict([k.split('=') for k in board_params.split(';')]))
        # boardから受け取った変数を self. 変数に加工
        self.set_self_vars()
        self._build_struct()

    def open_serial(self):
        print(t('comm.open_serial'))
        # serial port OPEN
        self.ser.open()
        # boardからの応答を待つ Obtain 'board_program' Name
        flag = self._waiting('board_program')
        self.ser.reset_output_buffer()
        self.ser.reset_input_buffer()
        board_program = flag.decode().split(':')[1]
        print(f'[INFO] {board_program=}')
        return board_program

    def init_serial(self, marker):
        # Write parameters PC ===> board
        exclusion_list = [
            'title',
            'dir_name',
            'num_points',
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
        # boardからの応答を待つ 'setparams'
        board_params = self._waiting('setparams')
        print(f'[INFO] {board_params=}')
        self.p.env_set.update(dict([k.split('=') for k in board_params.split(';')]))
        # boardから受け取った変数を self. 変数に加工
        self.set_self_vars()
        self._build_struct()

    def get_data_no_write(self):
        print(t('comm.thread_no_write_start'))
        while self.loop_th:
            self.ser_data = self.ser.read(self.one_data_size)
            self._data_ready.set()      # 初回待機解除用
            self._new_data_event.set()  # 新データ到着を通知
        self.ser.reset_output_buffer()
        self.ser.reset_input_buffer()
        print(t('comm.thread_no_write_stopped'))
        try:
            self.ser.write(b"r")
        except serial.SerialException:
            pass

    def get_data_and_write(self, f):
        while self.loop_th:
            self.ser_data = self.ser.read(self.one_data_size)
            self._data_ready.set()
            self._new_data_event.set()  # 新データ到着を通知
            f.write(self.ser_data)
        self.ser.reset_output_buffer()
        self.ser.reset_input_buffer()
        print(t('comm.thread_write_stopped'))
        try:
            self.ser.write(b"r")
        except serial.SerialException:
            pass

    def convert(self, s):
        # struct.unpack_fromで一括デコード（Cレベル、高速）
        raw = self._struct.unpack_from(s)

        # 変換関数を事前リストから直接呼ぶ
        fun = [f(v) for f, v in zip(self._func_list, raw)]
        out = np.empty(len(fun) + len(raw), dtype=np.float64)
        out[:len(fun)] = fun
        out[len(fun):] = raw
        return out.reshape(1, -1)

    def data_stream(self):
        self._data_ready.wait()
        ser_data0 = self.ser_data
        init_val = self.convert(ser_data0)
        init_val[0][0] = init_val[0][len(self.structure)] = 0
        self.data = np.full((2, len(self.structure) * 2), init_val)
        while True:
            # ポーリングの代わりにEventで待機
            self._new_data_event.wait()
            self._new_data_event.clear()  # 次のデータまでブロック
            if self.ser_data != ser_data0:
                ser_data0 = self.ser_data
                self.data[0] = self.data[1]
                self.data[1] = self.convert(ser_data0)
                yield self.data
