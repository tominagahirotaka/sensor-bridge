"""Message catalog for console and GUI text (English default, Japanese optional).

Switch language with the ``--lang {en,ja}`` CLI option (get.py / plot.py) or
the ``SENSOR_BRIDGE_LANG`` environment variable (the CLI option wins). Falls
back to English for any language or message key this catalog does not know.
"""

import os
from typing import Optional, Sequence

DEFAULT_LANG = "en"
SUPPORTED_LANGS = ("en", "ja")

_current_lang = os.environ.get("SENSOR_BRIDGE_LANG", DEFAULT_LANG)
if _current_lang not in SUPPORTED_LANGS:
    _current_lang = DEFAULT_LANG

MESSAGES = {
    # --- get.py ---
    "get.description": {
        "en": "Get data from a Raspberry Pi Pico / Pico W.",
        "ja": "Raspberry Pi Pico / Pico WからDataを取得する。",
    },
    "help.version": {
        "en": "show version",
        "ja": "Versionを表示する",
    },
    "help.init": {
        "en": "additional setting file",
        "ja": "追加の設定ファイル",
    },
    "help.style": {
        "en": "style file (.css)",
        "ja": "Style file（.css）",
    },
    "help.fullscreen": {
        "en": "fullscreen",
        "ja": "全画面表示",
    },
    "help.debug": {
        "en": "enable debug print",
        "ja": "Debug出力を有効にする",
    },
    "help.lang": {
        "en": "UI language ({langs})",
        "ja": "表示言語（{langs}）",
    },
    "help.sync": {
        "en": "listen for start/stop/quit triggers from sync_trigger.py "
              "(to start/stop/quit this window together with other "
              "sync-enabled get.py/get_camera.py windows)",
        "ja": "sync_trigger.pyからの開始/停止/終了トリガーを待ち受ける"
              "（他のsync有効なget.py/get_camera.pyウィンドウと"
              "同時に開始/停止/終了するため）",
    },
    "get.connected_boards": {
        "en": "[INFO] Connected boards: {boards}",
        "ja": "[INFO] 接続中のBoard: {boards}",
    },

    # --- mylib/window.py ---
    "window.subject_dialog_title": {
        "en": "Setting (measurement conditions, etc.)",
        "ja": "Setting(測定条件等)",
    },
    "window.param_dialog_title": {
        "en": "Parameter Setting (change from defaults)",
        "ja": "Parameter Setting(default値から変更)",
    },
    "window.reset_stop_thread": {
        "en": "[INFO] (reset) Stop Thread",
        "ja": "[INFO] (reset) Threadを停止しました",
    },
    "window.exec_write_close_cpt": {
        "en": "[INFO] Execute file.write_close_cpt()",
        "ja": "[INFO] file.write_close_cpt()を実行",
    },
    "window.check_time": {
        "en": "[INFO] Check time No.{no}, {val}",
        "ja": "[INFO] Checkpoint No.{no}, {val}",
    },
    "window.status_test": {
        "en": "Test (not recording)",
        "ja": "Test（記録なし）",
    },
    "window.status_run": {
        "en": "Run (recording)",
        "ja": "Run（記録中）",
    },
    "window.status_calib": {
        "en": "Calibration (not recording)",
        "ja": "Calibration（記録なし）",
    },
    "window.status_calib_done": {
        "en": "Calibration finished -- press Stop, then Test/Run",
        "ja": "Calibration終了 -- Stopを押してからTest/Runへ",
    },
    "window.status_stopped": {
        "en": "Stopped",
        "ja": "停止",
    },
    "window.status_push_after_running": {
        "en": "Push after Running button",
        "ja": "Runボタンを押した後に実行してください",
    },
    "window.temp_query_received": {
        "en": "[INFO] Received 'temp' sync command",
        "ja": "[INFO] 'temp' syncコマンドを受信",
    },
    "window.quit_pressed": {
        "en": "Quit button pressed",
        "ja": "Quitボタンが押されました",
    },
    "window.close_pressed": {
        "en": "Window Close button pressed",
        "ja": "Windowの閉じるボタンが押されました",
    },
    "window.quit_log": {
        "en": "[INFO] {msg}",
        "ja": "[INFO] {msg}",
    },

    # --- mylib/communicate.py ---
    "comm.ini_missing_use_default": {
        "en": "[INFO] [{ini}] does not exist, using [default.ini] instead",
        "ja": "[INFO] [{ini}] が存在しないため、[default.ini] を使用します",
    },
    "comm.additional_init": {
        "en": "[INFO] additional initial setting {init!r}",
        "ja": "[INFO] 追加の初期設定 {init!r}",
    },
    "comm.additional_init_not_found": {
        "en": "[ERROR] -i/--init file {init!r} not found (also tried {tried!r}); "
              "it had NO EFFECT -- check the filename (a bare board name needs a "
              "matching '<name>.ini' file, e.g. -i MyBoard needs "
              "MyBoard.ini in the current directory)",
        "ja": "[ERROR] -i/--init のファイル{init!r}が見つかりません（{tried!r}も試しました）。"
              "設定は何も反映されていません。ファイル名を確認してください"
              "（例: -i MyBoard を使うには、カレントディレクトリに"
              "MyBoard.ini が必要です）",
    },
    "comm.not_writing": {
        "en": "[INFO] Not writing",
        "ja": "[INFO] 記録なし（書き込みを行いません）",
    },
    "comm.board_not_connected": {
        "en": "Raspberry Pi Pico is not connected (no USB connection).",
        "ja": "Raspberry Pi PICOが未接続(USB未接続)です。",
    },
    "comm.prompt_connect_usb": {
        "en": "Connect the USB cable and press ENTER. To cancel, type any character first.",
        "ja": "USB接続して，ENTERキーを押してください。中止したい場合は任意の文字を入れてください。",
    },
    "comm.open_serial": {
        "en": "[INFO] open_serial & get board_program name",
        "ja": "[INFO] open_serial & board_program名を取得",
    },
    "comm.board_program_retry": {
        "en": "[WARN] board_program handshake attempt {attempt} got unparsable "
              "data ({raw!r}), retrying...",
        "ja": "[WARN] board_programハンドシェイクの{attempt}回目の試行で解析不能な"
              "データを受信({raw!r})。再試行します...",
    },
    "comm.board_program_failed": {
        "en": "[ERROR] Could not complete the board_program handshake on {port} "
              "after several attempts; the board may be stuck. Try unplugging "
              "and reconnecting it.",
        "ja": "[ERROR] {port}でboard_programハンドシェイクが数回試行しても完了しません"
              "でした。Boardが固まっている可能性があります。一度抜き差ししてください。",
    },
    "comm.setparams_retry": {
        "en": "[WARN] setparams response attempt {attempt} was malformed "
              "({raw!r}), retrying...",
        "ja": "[WARN] setparams応答の{attempt}回目の試行が不正な形式でした"
              "（{raw!r}）。再試行します...",
    },
    "comm.setparams_failed": {
        "en": "[ERROR] Could not get a well-formed setparams response from "
              "{port} after several attempts; the board may be stuck. Try "
              "unplugging and reconnecting it.",
        "ja": "[ERROR] {port}から正しい形式のsetparams応答が数回試行しても得られません"
              "でした。Boardが固まっている可能性があります。一度抜き差ししてください。",
    },
    "comm.write_failed": {
        "en": "[ERROR] Could not send the command to {port} ({err}); the "
              "board may have disconnected. Try unplugging and reconnecting "
              "it, then press Test/Run again.",
        "ja": "[ERROR] {port}へのコマンド送信に失敗しました（{err}）。Boardが切断"
              "された可能性があります。一度抜き差ししてから、Test/Runを再度押して"
              "ください。",
    },
    "comm.thread_no_write_start": {
        "en": "[INFO] Thread: [get_data_no_write] Start",
        "ja": "[INFO] Thread: [get_data_no_write] 開始",
    },
    "comm.thread_no_write_stopped": {
        "en": "[INFO] Thread: [get_data_no_write] Stopped",
        "ja": "[INFO] Thread: [get_data_no_write] 停止",
    },
    "comm.thread_write_stopped": {
        "en": "[INFO] Thread: [get_data_and_write] Stopped",
        "ja": "[INFO] Thread: [get_data_and_write] 停止",
    },
    "comm.thread_serial_error": {
        "en": "[ERROR] Serial read failed ({err}); the board may have disconnected. "
              "Stopping acquisition -- press Test/Run to reconnect.",
        "ja": "[ERROR] Serial読み込みに失敗しました({err})。Boardが切断された可能性があります。"
              "取得を停止します -- 再接続するにはTest/Runを押してください。",
    },
    "comm.thread_short_read": {
        "en": "[INFO] Board stopped sending data (got {got}/{expected} bytes after "
              "the read timeout) -- it may have finished a one-shot operation "
              "(e.g. calibration converging or reaching calib_max_iters). "
              "Waiting; press Stop when done.",
        "ja": "[INFO] Boardからのデータ送信が止まりました（タイムアウト後に{got}/"
              "{expected}バイトしか届きませんでした）。Calibrationの収束や"
              "calib_max_iters到達など、一度きりの処理が終わった可能性があります。"
              "待機します。終了する場合はStopを押してください。",
    },

    # --- plot.py: argparse description & --config ---
    "plot.description": {
        "en": "Plotting tool with config support",
        "ja": "設定ファイル対応のPlot表示Tool",
    },
    "plot.help.config": {
        "en": "path to the config file (JSON format)",
        "ja": "設定ファイルのPath（JSON形式）",
    },

    # --- plot.py: DEFAULTS / CLI help ---
    "plot.help.dirname": {
        "en": "default folder",
        "ja": "既定のFolder",
    },
    "plot.help.filename": {
        "en": "data file name",
        "ja": "データファイル名",
    },
    "plot.help.graph": {
        "en": "Graph type ({types})",
        "ja": "Graph種類（{types}）",
    },
    "plot.help.smoothing": {
        "en": "Apply signal smoothing beforehand (filter file: {file}, filter: {filt})",
        "ja": "前もってSignal smoothingをする（Filterファイル: {file}、Filter: {filt}）",
    },
    "plot.help.mvaverage": {
        "en": "moving average window (seconds)",
        "ja": "移動平均の秒数",
    },
    "plot.help.timeshift1": {
        "en": "time-shift so Mark 1 starts at t=0",
        "ja": "初めからMark 1にTimeshiftされる",
    },
    "plot.help.vline": {
        "en": "Mark line & LT & PRE line visible",
        "ja": "Mark・LT・PRE線を表示",
    },
    "plot.help.LT": {
        "en": "LT line visible",
        "ja": "LT線を表示",
    },
    "plot.help.PRE": {
        "en": "PRE lines visible",
        "ja": "PRE線を表示",
    },
    "plot.help.mvaslider": {
        "en": "moving average slider visible",
        "ja": "移動平均のSliderを表示",
    },
    "plot.help.wpconfig": {
        "en": "path to wavelet parameter config JSON",
        "ja": "Wavelet Parameter設定JSONのPath",
    },
    "plot.help.wlrange": {
        "en": "frequency range: start stop step",
        "ja": "周波数範囲: start stop step",
    },
    "plot.help.wlomega0": {
        "en": "Morlet wavelet omega0",
        "ja": "Morlet WaveletのOmega0",
    },
    "plot.help.pdffile": {
        "en": "write to PDF file",
        "ja": "PDFファイルに出力",
    },
    "plot.help.background": {
        "en": "run in background & quit after 100 msec",
        "ja": "Backgroundで実行し100msec後に終了",
    },
    "plot.help.automation": {
        "en": "automatically process every file in this folder",
        "ja": "このFolder内を自動処理",
    },
    "plot.help.fullscreen": {
        "en": "fullscreen",
        "ja": "全画面表示",
    },
    "plot.help.excel": {
        "en": "Excel output",
        "ja": "Excel出力",
    },
    "plot.help.header": {
        "en": "write header info to {filename}_header.xlsx on startup",
        "ja": "起動時にHeader情報を{filename}_header.xlsxへ書き出す",
    },
    "plot.help.peaks": {
        "en": "Peaks & Valleys visible",
        "ja": "Peak・Valleyを表示",
    },

    # --- plot.py: console messages ---
    "plot.no_dat_in_dir": {
        "en": "[INFO] No .dat files found in {dirname}. Exiting.",
        "ja": "[INFO] {dirname} に.datファイルが見つかりません。処理を終了します。",
    },
    "plot.no_dat_in_data_folder": {
        "en": "No data found in the data folder.",
        "ja": "dataフォルダにdataがありません",
    },
    "plot.config_load_error": {
        "en": "Failed to load config file: {err}",
        "ja": "設定ファイル読み込みエラー: {err}",
    },
    "plot.selected_file": {
        "en": "[INFO] Selected file: {path}",
        "ja": "[INFO] 選択したFile: {path}",
    },
    "plot.gui.save_graph_dialog_title": {
        "en": "Save Graph Data",
        "ja": "グラフDataの保存先",
    },
    "plot.gui.save_image_dialog_title": {
        "en": "Save Graph Image",
        "ja": "グラフ画像の保存先",
    },
    "plot.gui.save_region_select_checkbox": {
        "en": "Include Region Select row",
        "ja": "Region Select行も保存する",
    },
    "plot.gui.save_region_select_checkbox_tip": {
        "en": "Include the bottom Region Select (full-range overview) row in the saved image",
        "ja": "保存する画像に、最下段のRegion Select（全体表示）行も含めます",
    },
    "plot.save_image_eps_needs_pdftops": {
        "en": "Saving as EPS requires the 'pdftops' command-line tool (from "
              "poppler-utils), which was not found on this system. Try PDF, "
              "SVG, or PNG instead, or install poppler-utils.",
        "ja": "EPS形式での保存には'pdftops'コマンド（poppler-utils付属）が必要ですが、"
              "見つかりませんでした。代わりにPDF、SVG、PNGをお試しいただくか、"
              "poppler-utilsをインストールしてください。",
    },
    "plot.gui.save_csv_checkbox": {
        "en": "Also save CSV files",
        "ja": "CSVファイルも保存する",
    },
    "plot.gui.save_csv_checkbox_tip": {
        "en": "Also write each series to a separate .csv file next to the Excel file",
        "ja": "各シリーズを、Excelファイルと同じ場所に別途.csvとしても保存します",
    },
    "plot.gui.save_csv_checkbox_forced_tip": {
        "en": "Scalogram's data matrix is not written into the Excel sheet (too slow "
              "for large data), so CSV is the only place it's saved -- always on",
        "ja": "Scalogramのデータ行列はExcelシートに書き込まない(大きいと非常に遅いため)"
              "ため、CSVが唯一の保存先です。常にONになります",
    },
    "plot.selected_graph": {
        "en": "[INFO] Selected graph: {graph}",
        "ja": "[INFO] 選択したGraph: {graph}",
    },
    "plot.exec_received_data": {
        "en": "[INFO] Data received from Exec button:",
        "ja": "Execボタンで受け取ったデータ:",
    },
    "plot.current_shift_value": {
        "en": "Current shift value: {shift}",
        "ja": "現在のシフト値: {shift}",
    },

    # --- plot.py: GUI (buttons, tooltips, checkboxes) ---
    "plot.gui.open_file": {"en": "Open File", "ja": "ファイルを開く"},
    "plot.gui.open_file_tip": {"en": "Open a file (Ctrl+O)", "ja": "ファイルを開く(Ctrl+O)"},
    "plot.gui.save_graph": {"en": "Save Graph", "ja": "グラフを保存"},
    "plot.gui.save_graph_tip": {
        "en": "Save the displayed graph as an image (PDF or PNG)",
        "ja": "表示されているグラフを画像として保存する(PDFまたはPNG)",
    },
    "plot.gui.save_data": {"en": "Save Data", "ja": "データを保存"},
    "plot.gui.save_data_tip": {
        "en": "Save the displayed graph's data to Excel (Ctrl+S)",
        "ja": "表示されているグラフのDataをexcel保存する(Ctrl+S)",
    },
    "plot.gui.smoothing": {"en": "Smoothing", "ja": "平滑化"},
    "plot.gui.smoothing_tip": {
        "en": "Smooth the signal by applying various filters (Ctrl+F)",
        "ja": "各種Filterをかけてsignalを平滑化する(Ctrl+F)",
    },
    "plot.gui.wavelet_params": {"en": "Wavelet Params", "ja": "Waveletパラメータ"},
    "plot.gui.wavelet_params_tip": {
        "en": "Edit the wavelet transform's frequency range/omega0 and "
              "recompute the scalogram, without relaunching plot.py",
        "ja": "Wavelet変換の周波数範囲/omega0を編集し、plot.pyを再起動せずにScalogramを再計算する",
    },
    "plot.gui.select_graph": {"en": "Select Graph", "ja": "Graphを選択"},
    "plot.gui.select_graph_tip": {"en": "Choose which graph to draw (Ctrl+G)", "ja": "描画する図の選択(Ctrl+G)"},
    "plot.gui.info": {"en": "INFO", "ja": "情報"},
    "plot.gui.info_tip": {"en": "Show information contained in the data (Ctrl+I)", "ja": "dataに含まれる情報を表示します(Ctrl+I)"},
    "plot.gui.full_range": {"en": "Full Range", "ja": "全範囲"},
    "plot.gui.full_range_tip": {
        "en": "Toggle the bottom overview's selected range between full and the "
              "range you had selected",
        "ja": "最下段の選択範囲を、全範囲と直前に選択していた範囲とで切り替えます",
    },
    "plot.gui.quit": {"en": "Quit", "ja": "終了"},
    "plot.gui.quit_tip": {"en": "Quit (Ctrl+Q)", "ja": "終了します(Ctrl+Q)"},
    "plot.gui.select_port": {"en": "Select port", "ja": "ポート選択"},
    "plot.gui.peak_tip": {"en": "Show peak and valley positions", "ja": "peakとvalleyの位置を表示"},
    "plot.gui.mark_check": {"en": "Mark", "ja": "マーク"},
    "plot.gui.mark_tip": {"en": "Show marked (checkpoint) positions", "ja": "Mark(CheckPoint)した位置を表示"},
    "plot.gui.select_mark": {"en": "Select Mark", "ja": "Mark選択"},
    "plot.gui.time_shift_tip": {
        "en": "Move the time axis origin to the marked (checkpoint) position",
        "ja": "Mark(CheckPoint)した位置に時間軸の始点を移動",
    },
    "plot.gui.derivatives": {"en": "Derivatives", "ja": "微分"},
    "plot.gui.derivatives_tip": {"en": "Derivative", "ja": "微分"},
    "plot.gui.lt_tip": {"en": "Show the LT (Lactate Threshold) position", "ja": "LT(Lactate Threashold)の位置を表示"},
    "plot.gui.pre_tip": {"en": "Show PRE 11-13", "ja": "PRE11-13を表示"},
    "plot.gui.label2_tip": {"en": "Seconds since the selected Mark=1", "ja": "Select Mark=1 からの秒数"},
    "plot.gui.mv_window_size": {"en": "moving average window size", "ja": "移動平均のWindowサイズ"},

    # --- mylib/plot_utils.py: Signal Smoothing window ---
    "pu.smoothing_window_title": {"en": "Signal Smoothing", "ja": "信号平滑化"},
    "pu.btn_exec": {"en": "Exec", "ja": "実行"},
    "pu.btn_load": {"en": "Load", "ja": "読込"},
    "pu.btn_save": {"en": "Save", "ja": "保存"},
    "pu.btn_undo": {"en": "Undo", "ja": "元に戻す"},
    "pu.btn_apply": {"en": "Apply", "ja": "適用"},

    # --- mylib/plot_utils.py: Wavelet Parameters window ---
    "pu.wavelet_param_window_title": {"en": "Wavelet Parameters", "ja": "Waveletパラメータ"},
    "pu.wavelet_range_group": {"en": "Frequency range", "ja": "周波数範囲"},
    "pu.wavelet_range_min": {"en": "min", "ja": "最小"},
    "pu.wavelet_range_max": {"en": "max", "ja": "最大"},
    "pu.wavelet_range_step": {"en": "step", "ja": "刻み幅"},
    "pu.wavelet_omega0_group": {"en": "omega0", "ja": "omega0"},

    "pu.reset_tmin_to_zero": {"en": "Reset t_min to t=0", "ja": "t_min を t=0 にリセット"},
    "pu.history_prefix": {"en": "History: ", "ja": "履歴:"},
    "pu.save_plotdata_excel": {
        "en": "Saved PlotData to Excel in {sec:.4f} sec",
        "ja": "PlotDataをExcelへ保存 {sec:.4f} 秒",
    },
    "pu.save_imagedata_excel": {
        "en": "Saved ImageData to Excel in {sec:.4f} sec",
        "ja": "ImageDataをExcelへ保存 {sec:.4f} 秒",
    },
    "pu.use_python38": {
        "en": "This looks like header data recorded before this release (missing 'struct' field). Try reading it with Python 3.8 or earlier.",
        "ja": "このリリースより前に記録されたHeaderData（'struct'欄が無い形式）のようです。python3.8以前で読み込みを試してください。",
    },
    "pu.excel_row_limit": {
        "en": "[Alert] == num of data>1,048,576 -> Excel limit over(No data)",
        "ja": "[Alert] == num of data>1,048,576 -> Excelの上限を超えています(未出力)",
    },
    "pu.decimate_points": {
        "en": "[INFO] Points: {before:,} -> {after:,}",
        "ja": "[INFO] 点数: {before:,} → {after:,}",
    },
    "pu.warn_cpt_lst_empty": {
        "en": "Warning: cpt_lst is empty, using 0.0 instead.",
        "ja": "Warning: cpt_lst が空のため、0.0に置き換えます。",
    },
    "pu.warn_index_out_of_range": {
        "en": "Warning: index {idx} is out of range. Using the last value instead.",
        "ja": "Warning: インデックス {idx} が範囲外。最後の値を使用します。",
    },
    "pu.warn_unsupported_filter_type": {
        "en": "Warning: unsupported default_filter type {filter_type}. Continuing without a filter.",
        "ja": "Warning: 未対応のdefault_filter型 {filter_type}。フィルタなしで続行します。",
    },
    "pu.error_at_pair": {
        "en": "Error at pair {i}: {err}",
        "ja": "Pair {i} でError: {err}",
    },
    "pu.auto_saving_header": {
        "en": "Auto Saving Header to '{excelfile}' in {sec:.4f} sec",
        "ja": "Headerを '{excelfile}' へ自動保存 {sec:.4f} 秒",
    },
    "pu.unsupported_region_type": {
        "en": "Unsupported data type for region setting.",
        "ja": "Region設定に未対応のDataTypeです。",
    },
    "pu.unsupported_method": {
        "en": "Unsupported method: {method}",
        "ja": "未対応のmethod: {method}",
    },
    "pu.prominence_10pct": {
        "en": "Prominence = 10% of y-range",
        "ja": "Prominence=y変動の10%",
    },
    "pu.mavg_title": {
        "en": "{title} moving-average window {sec}sec",
        "ja": "{title} 移動平均時間 {sec}sec",
    },
    "pu.time_interval_histogram_title": {
        "en": "Sampling Time Interval Histogram",
        "ja": "サンプリング時間間隔のヒストグラム",
    },
    "pu.shift_placeholder": {
        "en": "Enter seconds",
        "ja": "秒数入力",
    },
    "pu.shift_tooltip": {
        "en": "Also shifts the time axis origin by the specified number of seconds",
        "ja": "更に,指定された秒数だけ時間軸の始点を移動",
    },
    "pu.cutoff_range_error": {
        "en": "Cutoff frequency cutoff={cutoff}Hz must be within the Nyquist frequency {nyq:.2f}Hz.",
        "ja": "カットオフ周波数 cutoff={cutoff}Hz はナイキスト周波数 {nyq:.2f}Hz の範囲内にしてください。",
    },

    # --- mylib/fileIO.py ---
    "fio.py38_incompat_1": {
        "en": "Cause: uname_result_base.__new__() takes 6 arguments but 7 were given.",
        "ja": "対処法: uname_result_base.__new__()は6つの引数を受け取りますが、7つが与えられました。",
    },
    "fio.py38_incompat_2": {
        "en": "Please try this under Python 3.8 or earlier.\nconda activate py38     (to return to the original environment: conda activate base)",
        "ja": "python 3.8以下の環境でお試しください。\nconda activate py38     (元の環境に戻るには，conda activate base)",
    },
    "fio.py38_incompat_3": {
        "en": "Create a Python 3.8 environment beforehand with:\nconda create -n py38 python=3.8",
        "ja": "python 3.8の環境は前もって\nconda create -n py38 python=3.8\nで作成しておいてください。",
    },
    "fio.py38_incompat_4": {
        "en": "Also, you will need to pip-install the required packages in the newly created environment.",
        "ja": "なお，新たに作成した環境で必要なpackageをpipでInstallする必要があります。",
    },
    "fio.py38_incompat_5": {
        "en": "Install the required packages there with: pip install -r requirements.txt",
        "ja": "その環境で pip install -r requirements.txt を実行し、必要なpackageをInstallしてください。",
    },
    "fio.write_to": {
        "en": "[INFO] Write to: {path}",
        "ja": "[INFO] 書き込み先: {path}",
    },
    "fio.read_from": {
        "en": "[INFO] Read from: {path}",
        "ja": "[INFO] 読み込み元: {path}",
    },
    "fio.no_header": {
        "en": "[INFO] No Header",
        "ja": "[INFO] Headerなし",
    },
    "fio.not_checkpoints_file": {
        "en": "[INFO] {path} is not a Check Points file",
        "ja": "[INFO] {path} はCheck Pointsファイルではありません",
    },
    # --- plot.py: graph_type tooltips (graph-selection menu) ---
    "plot.tt.timeseries": {"en": "Show the time-series waveform", "ja": "時系列波形を表示"},
    "plot.tt.powerspectra": {"en": "Show the power spectrum", "ja": "パワースペクトルを表示"},
    "plot.tt.scalogram": {
        "en": "Show the scalogram (time-frequency distribution, via Wavelet transform)",
        "ja": "(Wavelet変換による)スカログラム（時間-周波数分布）を表示",
    },
    "plot.tt.energy": {"en": "Show the energy (via Wavelet transform)", "ja": "(Wavelet変換による)エネルギーを表示"},
    "plot.tt.energy_cumsum": {
        "en": "Show the cumulative sum of energy (via Wavelet transform)",
        "ja": "(Wavelet変換による)エネルギーの累積和を表示",
    },
    "plot.tt.energy_mavg": {
        "en": "Show the moving average of energy (via Wavelet transform)",
        "ja": "(Wavelet変換による)エネルギーの移動平均を表示",
    },
    "plot.tt.power": {"en": "Show the power (via Wavelet transform)", "ja": "(Wavelet変換による)パワーを表示"},
    "plot.tt.power_mavg": {
        "en": "Show the moving average of power (via Wavelet transform)",
        "ja": "(Wavelet変換による)パワーの移動平均を表示",
    },
    "plot.tt.max_power_freq": {"en": "Show the frequency of maximum power", "ja": "最大パワー周波数を表示"},
    "plot.tt.max_power_bpm": {"en": "Show the BPM of maximum power", "ja": "最大パワーのBPMを表示"},
    "plot.tt.pv_freq": {"en": "Show the peak-to-valley frequency", "ja": "ピーク谷間の周波数を表示"},
    "plot.tt.pv_amp": {"en": "Show the peak-to-valley amplitude", "ja": "ピーク谷間の振幅を表示"},
    "plot.tt.pv_energy": {"en": "Show the peak-to-valley energy", "ja": "ピーク谷間のエネルギーを表示"},
    "plot.tt.pv_power": {"en": "Show the peak-to-valley power", "ja": "ピーク谷間のパワーを表示"},
    "plot.tt.pv_freq_mavg": {
        "en": "Show the moving average of peak-to-valley frequency",
        "ja": "ピーク谷間の周波数の移動平均を表示",
    },
    "plot.tt.pv_amp_mavg": {
        "en": "Show the moving average of peak-to-valley amplitude",
        "ja": "ピーク谷間の振幅の移動平均を表示",
    },
    "plot.tt.pv_energy_mavg": {
        "en": "Show the moving average of peak-to-valley energy",
        "ja": "ピーク谷間のエネルギーの移動平均を表示",
    },
    "plot.tt.pv_power_mavg": {
        "en": "Show the moving average of peak-to-valley power",
        "ja": "ピーク谷間のパワーの移動平均を表示",
    },

    "plot.gui.filters_tip": {
        "en": "Filters: DS=DownSampling, LP=Lowpass filter, BP=Bandpass filter, BN=Bandnotch filter, MA=Moving Average",
        "ja": "Filters:DS=DownSampling, LP=Lowpass filter, BP=Bandpass filter, BN=Bandnotch filter, MA=Moving Average",
    },
}


def set_language(lang: Optional[str]) -> None:
    """Set the active language. Ignored if lang is falsy or unsupported."""
    global _current_lang
    if lang and lang in SUPPORTED_LANGS:
        _current_lang = lang


def get_language() -> str:
    """Return the currently active language code (e.g. 'en' or 'ja')."""
    return _current_lang


def resolve_lang_from_argv(argv: Sequence[str], flags: Sequence[str] = ("--lang", "-lang")) -> Optional[str]:
    """Pull a --lang/-lang value out of argv without a full argparse pass.

    argparse can't localize its own --help text until args are parsed, but
    the language needs to be known *before* the parser (and its help
    strings) are built. Scanning argv directly breaks that chicken-and-egg
    problem, so `--lang ja --help` shows Japanese help in the same run.
    """
    for i, arg in enumerate(argv):
        for flag in flags:
            if arg == flag and i + 1 < len(argv):
                return argv[i + 1]
            if arg.startswith(flag + "="):
                return arg.split("=", 1)[1]
    return None


def resolve_localized_path(base_path: str) -> str:
    """Prefer a `<stem>_jp<suffix>` sibling of `base_path` when Japanese is active.

    Board .ini files (Analog.ini, SHT35.ini, DPG_*.ini, default.ini, ...) are
    exec()'d Python snippets rather than runtime-translatable strings, so
    they ship as a pair of files per board (see translate_ini.py) instead of
    going through `t()`. Falls back to `base_path` unchanged for English, or
    for Japanese when no `_jp` variant has been created for this file yet.
    """
    if _current_lang != "ja":
        return base_path
    root, ext = os.path.splitext(base_path)
    jp_path = f"{root}_jp{ext}"
    return jp_path if os.path.isfile(jp_path) else base_path


def t(key: str, **kwargs) -> str:
    """Translate message `key` into the active language.

    Unknown keys are returned as-is (with kwargs interpolated if possible),
    so a missing catalog entry degrades to a readable placeholder instead of
    crashing.
    """
    entry = MESSAGES.get(key)
    if entry is None:
        template = key
    else:
        template = entry.get(_current_lang) or entry.get(DEFAULT_LANG) or key
    try:
        return template.format(**kwargs) if kwargs else template
    except (KeyError, IndexError):
        return template
