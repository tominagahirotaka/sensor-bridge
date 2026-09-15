# Adding a new sensor board

A "board" in sensor-bridge is a pair of files: `<name>.ini` (and its
`<name>_jp.ini` sibling for the Japanese UI) plus a matching Arduino sketch
under `Arduino/`. This guide documents the pieces you need to touch, using
attributes and values captured from real hardware handshakes rather than
guesses, and closes with the checklist that has caught every real bug found
while adding boards to this repository so far.

**Read this once, but don't write a new board's files from scratch.**
Start by copying the `.ini`/`_jp.ini` pair and sketch of the existing board
closest to your sensor's interface (SPI, I2C, or plain analog) and adapt it
-- see [Copy-and-adapt, including with AI assistance](#copy-and-adapt-including-with-ai-assistance)
below.

## How a board loads

1. `get.py` scans for connected Picos and asks each one, over serial, what
   firmware it's running (`board_program`, a plain-text self-report).
2. It loads `<board_program>.ini` (or the `_jp` sibling if `--lang ja`).
3. `[main]`/`[notsave]`/`[board]` sections are merged into one `env_set`
   dict. The `[code]` section is kept separate and its values are executed
   as Python at UI build time (see below).
4. The PC and board then exchange parameters over serial (`init_serial()`
   in `mylib/communicate.py`), and the board reports back its `struct`
   (binary frame layout) and `func` (per-field raw-to-physical-unit
   conversion) definitions, which get merged into `env_set` too.

`-i/--init <name>` loads an *additional* `.ini` on top of the auto-detected
one (`self.p.env_set.update(...)`, `self.code.update(...)`) -- this is how
`DPG_X95840Wpeak.ini` layers peak-detection UI on top of the base
`DPG_X95840W.ini` without duplicating everything.

## `.ini` sections

```ini
[main]
title       = Accelerometer(LIS3DH)     # window title / recording title

[notsave]
dir_name      = data_LIS3DH             # recordings go under ./<dir_name>/
time_width    = 20                      # live-plot rolling window, seconds
min_peak_dist = 0.400                   # live peak detection: min seconds between beats

[board]
# Anything here is sent to the device during init_serial() (minus a fixed
# exclusion list: title/dir_name/min_peak_dist/time_width/func/struct/
# one_data_byte/serial_time_interval/real_time_interval/endian -- those
# are either PC-only or things the *board* sends back, not the PC).
spi_cs_pin   = 17
odr          = 5
fs           = 0

[code]
# Python source text, one key per name below. exec()'d/eval()'d against
# mylib/window.py's module globals() at UI-build time.
figs = ...
```

`[board]` values round-trip as plain strings unless your firmware's
parameter negotiation sends back a value that `eval()`s cleanly as Python
(int/float/tuple/etc.) -- see `mylib/communicate.py`'s `_coerce_env_value()`
docstring for the exact rules, and `tests/test_communicate.py` for worked
examples straight from real handshakes.

## `[code]` keys

All of these are looked up via `self.code['<key>']` in `mylib/window.py`.
`figs`/`panel1`/`lcd`/`subject_template`/`param_setting_template` are
`eval()`'d (they must be a single expression); the rest are `exec()`'d
(free-form statements). Everything runs with access to `self` (the live
`ApplicationWindow`), `self.board` (see [attribute reference](#selfboard-attribute-reference)
below), and any name importable from `mylib/window.py` (`Qtu` for
`mylib/Qtutils.py`'s widget factories, `QLabel`/`QLineEdit`/etc. from
PyQt5, `utils` for `mylib/utils.py`).

| Key | exec/eval | Required | Purpose |
|---|---|---|---|
| `window_setting` | exec | yes | Stylesheet strings (`title_style`, `text_box_style`), optional window icon |
| `menubar` | exec | yes | Builds `self.menuBar()`; wire each action's shortcut label to a callback like `self.on_start_button` |
| `figs` | eval | yes | List of plot-row dicts (labels, y-limits, marker style, which raw fields each row plots) -- see below |
| `panel1` | eval | yes | Dict of `{label: [callback_or_QLabel, WidgetKind]}` for the button/status column |
| `lcd` | eval | yes | List of dicts of `QLCDNumber`/`QLabel` pairs for the live readout row(s) |
| `layout` | eval | **currently unused/vestigial** -- every board config still defines it, but nothing in this repository reads `self.code['layout']`; the actual layout is built directly in `window.py`. Safe to copy verbatim from an existing board and ignore |
| `lcd_update` | exec | yes | Runs every plot-update tick; pushes `first_last_data`/`peak_interval` into the `lcd` widgets |
| `subject_template` | eval | yes | Dict describing the "measurement info" dialog's fields |
| `before_subject_window` / `after_subject_window` | exec | no | Optional pre/post hooks around the subject dialog (e.g. building the summary label shown on the panel) |
| `param_setting_template` | eval | yes | Dict describing the "Parameter" dialog's fields (what gets sent on Start/Again) |
| `before_param_setting_window` / `after_param_setting_window` | exec | no | Optional pre/post hooks around the parameter dialog |

### `figs`

One dict per plotted row:

```python
{'label' : (self.board.lab[0]+'('+self.board.func_unit[0]+')',
            self.board.lab[1]+'('+self.board.func_unit[1]+')'),
 'limit' : (None, (-2, 2)),                 # (x-limit, y-limit); None = autoscale
 'data'  : ((0, 1, {'peak': False, 'raw': (False, False)}),),
 'grid'  : True,
 'pargs' : {'ls': '', 'marker': 'o', 'ms': 1, 'color': 'red'},   # peak-marker style
 'fargs' : {'ls': '-', 'lw': 1, 'marker': 'o', 'ms': 0},          # line style
 'legend': False}
```

`'data'` entries are `(x_field_index, y_field_index, {'peak': bool, 'raw': (bool, bool)})`.
Field indices are positions in the device's `struct` (index 0 is always
the timestamp). Set `'peak': True` to run live peak/heart-rate-style
detection on that channel -- see
[the peak-detection tuning notes](#peak-detection-if-your-sensor-needs-it)
below before relying on it. Board configs commonly build `figs` with a
`(lambda self: [... for k, p_no in enumerate(self.board.port_num)])(self)`
pattern to emit one row per detected port/channel rather than a fixed
number of rows.

## `self.board` attribute reference

After the handshake, `self.board` carries every `[board]` key (coerced per
the rules above) plus these, captured verbatim from a real LIS3DH/
DPG_X95840W session (`--Debug` output):

| Attribute | Example value | Meaning |
|---|---|---|
| `structure` | `[[('time', ''), (0, 4), 0], [('port', '0'), (4, 6), 1], ...]` | `[(label, suffix), (byte_start, byte_end), func_index]` per field, decoded from the device's `struct` string |
| `lab` | `['time', 'port', 'port', 'port']` | Field base names, in `structure` order |
| `lab_sub` | `['', '0', '1', '2']` | Field suffixes (e.g. per-port index) |
| `func_unit` | `['sec', 'V', 'kOhm']` | Physical unit per `func` entry |
| `func` | list of `(callable, bits, unit)` | Raw-to-physical-unit conversion, decoded from the device's `func` string (see `_coerce_env_value()`) |
| `one_data_size` | `10` | Bytes per sample frame |
| `lim_auto_raw` / `lim_auto_func` | `(0, 4095)` / `(0.0, 4.999...)` | Auto-scale limits in raw counts / converted units, derived from each field's bit width |

`struct`'s mini-language (`"time(u4:func0), [(0,1,2)]port(u2:func1)"`) is
parsed by `mylib/utils.py`'s `repeat_interpret()`/`content_process()`/
`make_struct_list()` -- see `tests/test_utils.py` for more worked examples,
including the repeat-group syntax (`[(0,1,2)]field(...)` -> one `field`
entry per listed index; `[N]field(...)` -> `N` sequential entries).

## Firmware side

Each sketch under `Arduino/<name>/` implements the PC-facing half of the
same handshake:

- `initialSetupParam(ch, input)` -- parses the PC's `env_set` string,
  configures the sensor (register writes, I2C/SPI setup), and reports back
  `struct`/`func`/`endian`/anything else the PC needs via
  `serial_print_separate(join_dict(params_to, ";", "="))`.
- `changeParam(ch)` -- called on Start/Again/caliBrate; computes
  `serial_time_interval`/`real_time_interval` (how fast the device can
  actually stream given the baud rate and your ODR) and reports them back.
- `loop()`'s single-character command dispatch (`'i'`/`'a'`/`'s'`/`'r'`/`'q'`/`'c'`)
  followed by a fixed `delay(100)` after each. **Do not remove these
  delays without testing on real hardware first** -- one of them is
  commented "VERY IMPORTANT" for a documented reason (serial-buffer
  settling), and removing what looked like a redundant *second* delay(100)
  on LIS3DH/SHT35 broke their handshake in practice (bytes dropped mid-
  transmission) even though sibling boards apparently worked fine without
  it. If you want to investigate this for a new board, do it as its own
  change, verified against real hardware, not bundled with adding the
  board.

## Copy-and-adapt, including with AI assistance

The nine existing board configs are deliberately consistent in structure
specifically so a new one can be produced by adapting the closest existing
example -- by a human, or, as demonstrated while developing LIS3DH support
in this repository, by an AI coding assistant given the existing files as
context. That worked well as a way to get a plausible first draft quickly.
It did **not**, on its own, produce hardware-correct code: real issues only
surfaced once the result was tested against a physical board (see the
checklist below -- every item on it corresponds to something that actually
went wrong this way). Treat AI-assisted (or human-assisted) generation from
samples as a fast way to a first draft, not a substitute for the checklist.

## Verification checklist

Work through these, in order, before trusting any data from a new board.
Each one corresponds to a real failure encountered while adding a board to
this repository:

1. **Identity check first.** If your sensor has a device-ID register
   (`who_am_i` or equivalent), read it back and print it before writing any
   other registers. Confirms wiring, bus mode, and chip-select handling
   before you waste time debugging something else.
2. **Watch the raw handshake with `-d`/`--Debug`.** Confirm `struct`/`func`
   decode into the field list you expect (`self.structure` -- see above)
   before assuming the acquired data is meaningful.
3. **Values containing `=` will break naive parsing.** If your `func`
   lambda's body contains a comparison (`>=`, `<=`), it must survive
   `key=value;key=value` parsing. This repository's protocol code already
   handles it correctly (`split('=', 1)`, not `split('=')`) -- but if you
   add *new* string-parsing code anywhere in the pipeline, remember this.
4. **Check sampling-interval jitter, not just that data arrives.** Record a
   short sample and look at the Header Viewer's time-interval histogram in
   `plot.py` (or replicate `tests/test_peak_detection.py`'s approach) for
   your target sample rate. A wrong `real_time_interval` calculation can
   produce data that *looks* fine on screen but has bad timing underneath.
5. **If you set `'peak': True` on a channel**, see the tuning notes below
   before trusting the derived rate -- the default settings assume a
   heartbeat-like waveform shape and amplitude range.
6. **Never remove firmware timing delays without a hardware test on that
   exact board.** See [Firmware side](#firmware-side) above.

## Peak detection, if your sensor needs it

Live peak/heart-rate-style detection (`FigureQtPG._detect_and_record_peak`
in `mylib/Qtutils.py`) assumes a roughly heartbeat-shaped pulsatile signal.
Things worth knowing if you enable `'peak': True` on a new channel:

- The amplitude threshold (`self.average`) is a slow exponential moving
  average (`AVERAGE_TIME_CONSTANT_SEC = 3.0`), not the channel's absolute
  scale -- it should adapt to most signal ranges, but verify against real
  data rather than assuming it.
- `min_peak_dist` (a `[notsave]` key, seconds) rejects candidate peaks
  closer together than that. Too small and a secondary feature in your
  waveform (e.g. a dicrotic notch on a pressure/PPG-like signal) can get
  detected as an extra beat; too large and you'll miss genuinely fast
  rates. This is a real tuning tradeoff specific to your sensor and
  application, not something with a universally correct default.
- The displayed rate is a median over the last several detected peaks
  (`PEAK_TIME_BUFFER_SIZE = 7`), which absorbs an occasional bad detection
  but won't fix a *systematic* one (e.g. a secondary feature present on
  every single beat). If you see the displayed rate consistently locked
  onto roughly double or half the true rate, suspect `min_peak_dist`
  first.
- See `tests/test_peak_detection.py` for worked examples of all of the
  above, including how to reproduce and check for each failure mode with
  synthetic data before you have hardware in hand.
