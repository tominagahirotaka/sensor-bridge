# sensor-bridge

A Python/PyQt5 research instrumentation framework for acquiring, visualizing,
and analyzing sensor data streamed from a Raspberry Pi Pico / Pico W over
USB serial. It pairs a lightweight Arduino firmware layer (one sketch per
supported sensor board) with two desktop applications: `get.py` for live
acquisition and `plot.py` for post-hoc visualization and signal processing.

## Why sensor-bridge

Most hobbyist Arduino-to-PC serial examples send data as ASCII text
(`Serial.println(...)`), which is simple to read but too slow for
high-rate, timing-sensitive measurements. sensor-bridge instead:

- times each sample **on the Pico itself**, in microseconds, at the moment
  of acquisition -- not on the host when the packet happens to arrive, so
  sampling intervals are not distorted by PC-side OS scheduling or GUI
  redraw jitter;
- streams samples as **fixed-width binary frames** (`struct`-packed, one
  `struct.Struct` compiled once per connection) rather than delimited text,
  avoiding both the parsing overhead and the ambiguity of text framing;
- keeps live acquisition (`get.py`) and post-hoc analysis (`plot.py`) as
  separate applications sharing the same underlying data model, so a
  recording can be re-opened, re-filtered, and re-exported at any time
  without re-running the experiment.

Measured on real recorded hardware data (LIS3DH accelerometer, several
output-data-rate settings), sampling-interval jitter stayed under 1%
coefficient of variation. This measurement has not yet been written up as
a repeatable script/notebook in this repository; doing so is a TODO
before citing the number in the paper.

## Supported hardware

Each row below is a `<name>.ini` / `<name>_jp.ini` pair (English / Japanese
UI) plus a matching sketch under `firmware/Arduino/`.

| Board config | Sensor / purpose |
|---|---|
| `LIS3DH` | LIS3DH 3-axis accelerometer (SPI) |
| `SHT35` | Sensirion SHT35 temperature & humidity (I2C) |
| `Analog` | Generic analog input (e.g. a custom photoplethysmography front-end read via the Pico's ADC) |
| `DPG_X95840W` | X95840W digital-potentiometer-based device, with live peak (heart-rate-style) detection |
| `DPG_X95840W_LIS3DHx2` | DPG_X95840W combined with two LIS3DH accelerometers |
| `default` | Fallback generic analog config |

New boards are added by pairing a new `<name>.ini` with a new Arduino
sketch; see [Adding a new sensor board](#adding-a-new-sensor-board) below.

## Requirements

- Python 3.13 (the version this repository has been developed and tested
  against; earlier Python 3 versions have not been verified)
- A Raspberry Pi Pico or Pico W running one of the firmware sketches under
  `firmware/Arduino/` -- named for the *framework* the firmware is written in
  (Arduino-style `.ino` sketches via the community
  [earlephilhower/arduino-pico](https://github.com/earlephilhower/arduino-pico)
  core), not Arduino-brand hardware; see
  [`firmware/Arduino/README.md`](firmware/Arduino/README.md).
  Build with the Arduino IDE or `arduino-cli` and flash the resulting
  `.uf2`, or use one of the prebuilt `*.rpipico.uf2` files under
  `firmware/`.
- Python dependencies, installed via:

  ```bash
  pip install -r requirements.txt
  ```

## Quick start

### Live acquisition (`get.py`)

Connect a Pico running compatible firmware over USB, then:

```bash
python get.py
```

`get.py` scans for connected boards, identifies each one from its own
firmware self-report, and opens one window per board using the matching
`<name>.ini`. Useful options:

```bash
python get.py -i <name>             # load an additional/override .ini on top of the auto-detected one
python get.py -lang ja             # Japanese UI
python get.py -d                   # verbose --Debug diagnostics
python get.py --help
```

### Post-hoc analysis (`plot.py`)

```bash
python plot.py -f path/to/recording.dat
```

Opens the recorded `.dat`/`.cpt` pair in the analysis GUI: time-series,
power spectrum, wavelet scalogram, peak/derivative overlays, signal
smoothing (trim/downsample/moving-average/lowpass/bandpass/bandnotch), and
Excel/CSV export. Run `python plot.py --help` for the full option list
(graph type, wavelet parameters, moving-average window, overlay toggles,
etc.).

## Testing

The suite under `tests/` covers the pure-logic and PyQt5/pyqtgraph-backed
modules that don't require actual hardware (protocol parsing, signal
filters, the live peak-detection pipeline, histogram binning, i18n
catalog completeness, and a few GUI helper/data-model functions), run
headless via `QT_QPA_PLATFORM=offscreen`:

```bash
pip install -r requirements-dev.txt
pytest
```

Code paths that require a physically connected Pico (the serial
handshake against real firmware, sensor register-level correctness) are
not covered by this suite and still need manual hardware testing.

## File format

A recording is saved as a `.dat` (binary samples, pickled header) plus a
`.cpt` (checkpoint marks) file, both written by `get.py` under the
directory named by the board's `dir_name` setting. `plot.py` reads this
pair back into the same in-memory data model used for live plotting.

## Design notes

Two choices in this codebase are deliberate, not accidental, and are
documented here since they can look unusual out of context:

**Board `.ini` files execute Python (`[code]` section).** Per-board GUI
layout (menus, panels, LCD readouts, dialogs) is defined as literal Python
snippets, `exec()`/`eval()`'d against the application's own namespace at
load time, rather than a static declarative format. This mirrors an
established Python idiom for trusted, developer-authored configuration
(e.g. Sphinx's `conf.py`, Django's `settings.py`, `setup.py`) -- config
files here are written by the same developer adding a board, not
untrusted end-user input, and per-board layouts genuinely need dynamic
content (e.g. one row per detected port) that a static schema would need
to reinvent a scripting language to express. New board configs have been
generated from this repository's existing files by AI coding assistants
with reasonable success as a first draft; as with any hardware-facing
code, the result still needs verification against real hardware before
being trusted (register maps, timing, and sensor-specific quirks are not
things a template alone can validate).

**Live acquisition and analysis are separate applications.** `get.py`
focuses on low-latency real-time acquisition; `plot.py` focuses on
richer, slower analysis (wavelet transforms, filtering, export) against
already-recorded data. Splitting them keeps the acquisition loop simple
and avoids coupling acquisition timing to analysis-side processing cost.

## Adding a new sensor board

See [`docs/adding-a-board.md`](docs/adding-a-board.md) for the `.ini`
section reference, the `self.board` attribute surface (captured from real
hardware handshakes), the firmware-side handshake, and a verification
checklist where every item corresponds to a real bug caught while adding
a board to this repository.

## License

MIT License -- see [`LICENSE`](LICENSE).

## Citation

A citation entry will be added once this software has an associated
publication and archived release (DOI).
