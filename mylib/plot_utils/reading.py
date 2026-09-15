"""Data model and file-loading layer: PlotData/PlotImageData (the plot.py
in-memory series containers, incl. to_excel export) and ReadData (loads a
.dat/.cpt recording, or a processed-binary payload, into a PlotData)."""

import datetime
import os
import re
import sys
import time

import numpy as np
import pandas as pd

from processed_binary import ProcessedBinaryError, decode_processed_payload
import mylib.communicate as comm
import mylib.fileIO as FIO
import mylib.utils as utils
from mylib.debug_utils import debug_print
from mylib.i18n import t as tr


class PlotData:
    def __init__(self, data=None, labels=None):
        """
        data: list of (x, y) tuples or lists
        labels: optional list of labels
        """
        self.data = [(np.array(x), np.array(y)) for x, y in data] if data else []
        self.labels = labels if labels else [None] * len(self.data)
        self.xlabel = None
        self.title = None
        self.subtitle = None

    def __getitem__(self, idx):
        return self.data[idx]

    def __len__(self):
        return len(self.data)

    def __iter__(self):
        return iter(self.data)

    def add_series(self, x, y, label=None):
        self.data.append((np.array(x), np.array(y)))
        self.labels.append(label)
        self.num_data = len(self.data)

    def __repr__(self):
        return f"PlotData({len(self.data)} series)"

    def to_excel(self, filename, filter=None, mark_points=None, note_df=None):
        basename = os.path.splitext(filename)[0]  # 'ABC_G02'
        start = time.perf_counter()
        time_shift1 = float(mark_points[0][0]) if len(mark_points) > 0 else 0
        filter_df = pd.DataFrame(filter)
        title_df = pd.Series({'title': self.title, 'subtitle': self.subtitle}).T
#        with pd.ExcelWriter(filename, engine='openpyxl') as writer:
        with pd.ExcelWriter(filename, engine='xlsxwriter') as writer:
            sheet_count = 0
            for i, ((x, y), label) in enumerate(zip(self.data, self.labels)):
                if len(x) == 0 or len(y) == 0:
                    continue  # 空データはスキップ
                x_lab = f"{self.xlabel['bottom'][0]}({self.xlabel['bottom'][1]})" if self.xlabel else 'time'
                y_lab = f"{label['left'][0]}({label['left'][1]})" if label else f"Series{i + 1}"
                if time_shift1 > 0:
                    ts1 = x - time_shift1
                    df = pd.DataFrame({x_lab: x, x_lab + 'ts1': ts1, y_lab: y})
                else:
                    df = pd.DataFrame({x_lab: x, y_lab: y})
                sheet_name = y_lab
                print(f'{sheet_name=}')
                # シート名が31文字超えないようにし、不正文字も除去
                safe_name = sheet_name[:31].replace('/', '_')
                df.to_excel(writer, sheet_name=safe_name, index=False)
# clean_name = re.sub(r'[()]', '', safe_name)
                clean_name = re.sub(r'\([^)]*\)', '', safe_name)
                df.to_csv(f"{basename}_{clean_name}.csv", index=False)
                sheet_count += 1

            filter_df.to_excel(writer, sheet_name='Filter', index=False)
            title_df.to_excel(writer, sheet_name='Title', index=True, header=False)
            if mark_points is not None:
                mark_df = pd.DataFrame(
                    mark_points, columns=[
                        'real time', 'time'], index=range(
                        1, len(mark_points) + 1))
                mark_df.to_excel(writer, sheet_name='mark points', index=True, header=True)
            if note_df is not None:
                note_df.to_excel(writer, sheet_name='Note', index=True, header=False)

            if sheet_count == 0:
                raise ValueError(
                    "No valid data series to write. At least one non-empty sheet is required.")

        print(tr('pu.save_plotdata_excel', sec=time.perf_counter() - start))
        print(f"{filename=}")


class PlotImageData:
    def __init__(self, data=None, labels=None):
        """
        data: list of (x, y, value) tuples or lists
        labels: optional list of labels
        """
        self.data = [(np.array(x), np.array(y), np.array(z)) for x, y, z in data] if data else []
        self.labels = labels if labels else [None] * len(self.data)
        self.xlabel = None
        self.title = None
        self.subtitle = None

    def __getitem__(self, idx):
        return self.data[idx]

    def __len__(self):
        return len(self.data)

    def __iter__(self):
        return iter(self.data)

    def add_series(self, x, y, val, label=None):
        self.data.append((np.array(x), np.array(y), np.array(val)))
        self.labels.append(label)

    def __repr__(self):
        return f"PlotData({len(self.data)} series)"

    def to_excel(self, filename, filter=None, mark_points=None, note_df=None):
        basename = os.path.splitext(filename)[0]  # 'ABC_G02'
        start = time.perf_counter()
        time_shift1 = float(mark_points[0][0]) if len(mark_points) > 0 else 0
        filter_df = pd.DataFrame(filter)
        title_df = pd.Series({'title': self.title, 'subtitle': self.subtitle}).T
#        with pd.ExcelWriter(filename, engine='openpyxl') as writer:
        with pd.ExcelWriter(filename, engine='xlsxwriter') as writer:
            sheet_count = 0
            csv_files = []
            for i, ((x, y, val), label) in enumerate(zip(self.data, self.labels)):
                if len(x) == 0 or len(y) == 0 or len(val) == 0:
                    continue  # 空データはスキップ

                print(type(x), getattr(x, 'shape', None))
                print(type(y), getattr(y, 'shape', None))
                print(type(val), getattr(val, 'shape', None))

#                df = pd.DataFrame({'x': x, 'y': y, 'z':val})
                print(f'{self.xlabel=}, {label=}')
                df = pd.DataFrame(val.T, index=x, columns=y)
                x_lab = f"{self.xlabel['bottom'][0]}({self.xlabel['bottom'][1]})" if self.xlabel else 'time'
                sheet_name = f"{label['left'][0]}({label['left'][1]})" if label else f"Series{i + 1}"
                df.index.name = f"{x_lab}\\freq.({label['left'][1]})"
                # シート名が31文字超えないようにし、不正文字も除去
                safe_name = sheet_name[:31].replace('/', '_')
# clean_name = re.sub(r'[()]', '', safe_name)
                clean_name = re.sub(r'\([^)]*\)', '', safe_name)
                # Scalogramの時間×周波数行列は数十万〜数百万セル規模になり、xlsxwriterへの
                # セル単位書き込みはCSV書き込みの5〜6倍以上遅い(実測: 5分の記録で約30秒 vs
                # 4秒)。Excelで閲覧するにも大きすぎる行数になるため、Excelシートへは書き込まず
                # CSVのみに残し、どのCSVに対応するかを後で'Data'シートに一覧で示す。
                csv_path = f"{basename}_{clean_name}.csv"
                df.to_csv(csv_path, index=True)
                csv_files.append((safe_name, os.path.basename(csv_path)))
                sheet_count += 1

            filter_df.to_excel(writer, sheet_name='Filter', index=False)
            title_df.to_excel(writer, sheet_name='Title', index=True, header=False)
            if csv_files:
                csv_index_df = pd.DataFrame(csv_files, columns=['channel', 'data file (CSV)'])
                csv_index_df.to_excel(writer, sheet_name='Data', index=False)
            if mark_points is not None:
                mark_df = pd.DataFrame(
                    mark_points, columns=[
                        'real time', 'time'], index=range(
                        1, len(mark_points) + 1))
                mark_df.to_excel(writer, sheet_name='mark points', index=True, header=True)
            if note_df is not None:
                note_df.to_excel(writer, sheet_name='Note', index=True, header=False)

            if sheet_count == 0:
                raise ValueError(
                    "No valid data series to write. At least one non-empty sheet is required.")

        print(tr('pu.save_imagedata_excel', sec=time.perf_counter() - start))
        print(f"{filename=}")


class ReadData():
    def __init__(self, args):
        self.args = args
        file = FIO.FileIO()                                                      # Instance of FileIO class
        self.header = file.read_open(self.args.filename)  # header読込み
        if self.header:                                                            # 全データ一括読込み
            debug_print(self.args, f' With header ... Using file.fread.read()')
            all_bin_data = file.fread.read()
        else:
            debug_print(self.args, f' No header ... Using np.loadtxt()')
            data_ = np.loadtxt(sys.argv[1], dtype='int', comments='#', unpack=True)

        for key, val in self.header.__dict__.items():
            debug_print(self.args, f' {key:<10}={val}')  # header確認

        if hasattr(self.header, 'processed_data'):
            self._load_processed_payload(all_bin_data)
            self._load_external_excel()
            self.makeTitle()
            return

        self.board = comm.Board(self.header, self.args, False)     # Instance of Board class

        # For Old version (旧versionに入っていない項目追加)
        if 'struct' not in self.board.p.env_set:
            self.ForOldVersion()
            print(tr('pu.use_python38'))

        self.board.set_self_vars()               # set variables
        self.board._build_struct()
        # self.board.prepare_plotting()
        debug_print(self.args, f' self variables={vars(self.board)}')       # print self vars list
        debug_print(self.args, f'[INFO] one_data_size={self.board.one_data_size}')
        self.num_data = int(len(all_bin_data) / self.board.one_data_size)

        self.data = np.zeros((self.num_data, 2 * len(self.board.structure)))  # data配列確保
        for i in range(self.num_data):                # data変換(binary data -> numerical data)
            self.data[i] = self.board.convert(
                all_bin_data[i * self.board.one_data_size:(i + 1) * self.board.one_data_size])
        # data配列の行と列を入替え
        self.data_t = self.data.T
        # PlotData 作成
        self.data0 = PlotData()
        self.data0.title = 'Timeseries'
        for k, lst in enumerate(self.board.structure[1:]):
            ax_label = {'left': (f'{lst[0][0]}{lst[0][1]}',
                                 f'{self.board.func_unit[lst[2]]}')}   # axis label 'port\d(V)'
            self.data0.add_series(self.data_t[0], self.data_t[k + 1], label=ax_label)

        # Axis label bottom -->  'time(sec)'
        self.ax_time = {'bottom': (
            self.board.structure[0][0][0], self.board.func_unit[self.board.structure[0][2]])}
        self.data0.xlabel = {'bottom': (
            self.board.structure[0][0][0], self.board.func_unit[self.board.structure[0][2]])}

        self._load_checkpoint_list()
        self._load_external_excel()

        self.makeTitle()                         # setting Title

    def _load_processed_payload(self, payload):
        metadata = self.header.processed_data
        try:
            series = decode_processed_payload(payload, metadata)
        except ProcessedBinaryError as exc:
            raise ValueError(str(exc)) from exc

        self.board = None
        self.num_data = len(series[0][0]) if series else 0
        self.data0 = PlotData()
        self.data0.title = 'Timeseries'

        time_meta = metadata.get('time_axis', {})
        time_name = str(time_meta.get('name', 'time'))
        time_unit = str(time_meta.get('unit', ''))
        self.ax_time = {'bottom': (time_name, time_unit)}
        self.data0.xlabel = {'bottom': (time_name, time_unit)}

        data_rows = []
        first_time = None
        for index, (x, y) in enumerate(series):
            if first_time is None:
                first_time = x
            label_meta = metadata.get('series', [])[index]
            ax_label = {
                'left': (
                    label_meta.get(
                        'name', f'series_{index}'), label_meta.get(
                        'unit', ''))}
            self.data0.add_series(x, y, label=ax_label)
            data_rows.append(y)

        if first_time is None:
            self.data_t = np.array([[]])
        else:
            self.data_t = np.vstack([first_time, *data_rows])
        self._load_checkpoint_list()

    def _load_checkpoint_list(self):
        self.cpt_list = np.array([time[1] if type(time[0]) is datetime.datetime else time[0]
                                 for time in self.header.time['check_points']])
        debug_print(self.args, f' ================ {self.cpt_list=}')

    def _load_external_excel(self):
        # 外部excelファイルに縦線を描画したい位置とその文字列を指定(ex. 'LT' \n 300, 'PRE11'\n 250)
        self.external_excel = os.path.splitext(self.args.filename)[0] + ".xlsx"
        if os.path.exists(self.external_excel):
            external_df = pd.read_excel(self.external_excel)
            self.external_dict = external_df.to_dict(orient="index")[0]
            debug_print(self.args, f'{self.external_excel=}, {self.external_dict=}')
            self.LT_dict = {k: v for k, v in self.external_dict.items() if 'LT' in k}
            self.PRE_dict = {k: v for k, v in self.external_dict.items() if 'PRE' in k}
        else:
            self.external_dict = None
            self.LT_dict = None
            self.PRE_dict = None

    # For Old version
    # 旧versionに入っていない項目の追加
    # platformの仕様変更の為，読み込めない場合はpython3.8以下を使用
    def ForOldVersion(self):
        # 現行Firmwareの対象はRaspberry Pi Pico/Pico Wのみ。ここは、それ以前に
        # 実際にArduino Unoで記録した過去のData(.dat)を読むためだけの後方互換Codeで、
        # 現行のHardware対応状況とは無関係(Raw Data保持のため削除しないこと)。
        port_str = ','.join(str(item) for item in self.board.p.env_set['port_num'])
        time_unit = self.board.p.env_set['time_unit']
        time_byte = self.board.p.env_set['time_byte']
        data_byte = self.board.p.env_set['data_byte']
        ADCres = self.board.p.env_set['ADCres'] = '10'       # 記録当時のArduino Unoの仕様(10bit ADC)
        volt = self.board.p.env_set['volt'] = '5'          # 記録当時のArduino Unoの仕様(5V)
        self.board.p.env_set['struct'] = f'time(u{time_byte}:func0), [({port_str})]port(u{data_byte}:func1)'
        time_bits = 8 * time_byte
        volt_coeff = float(volt) / float(2**12)
        self.board.p.env_set['func'] = (
            f"[(lambda tm:tm/{float(10**time_unit)}, {time_bits}, 'sec'), "
            f" (lambda x:x*{volt_coeff}, {ADCres}, 'V')]"
        )
        self.board.p.env_set['endian'] = 'big'
        # debug_print(self.args, f"{self.board.p.env_set['func']=}")

    def makeTitle(self):                         # title設定
        subject = self.header.subject
        if 'birth' in subject:
            # 被験者情報系Template(name/height/weight/birth/gender/...)。GenderのComboBoxや
            # 生年月日のDateEditは未操作でも既定値(Male/2000-01-01等)を持つため、Nameが空なら
            # Subjectダイアログは実質未入力とみなす(例: 何も設定していないのに
            # 「Male(26)」のような偽のTitleが出るのを防ぐ)。
            if not str(subject.get('name', '')).strip():
                self.title = ''
                return
            if 'age' not in subject:
                age = utils.calc_age(subject['birth'], self.header.time['start_time'])
            else:
                age = subject['age']
            self.title = f"{subject['name']} {subject['gender']}({age})"
        elif subject and any(str(val).strip() for val in subject.values()):
            # birthを持たないTemplate(LIS3DHの実験Title/実験設定/MEMO等)。全FieldがQLineEdit
            # 相当で「未操作でも値を持つ」Widgetが無いため、何か1つでも入力されていれば表示する。
            self.title = ';'.join(f'{key}:{val} ' for key, val in subject.items())
        else:
            self.title = ''  # 'Plot program'

    def output_excel_file(self, excelfile):
        col1 = [la + '_' + s for la, s in zip(self.board.lab, self.board.lab_sub)]
        columns = col1 + [lab + '(raw)' for lab in col1]
        print(f'num of data={self.num_data}, column names={columns}')
        if self.num_data < 2**20:
            with pd.ExcelWriter(excelfile) as writer:
                pd.DataFrame(
                    self.data,
                    columns=columns).to_excel(
                    writer,
                    sheet_name='data',
                    index=False,
                    header=True)
        else:
            print(tr('pu.excel_row_limit'))
