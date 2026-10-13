---
title: 'sensor-bridge: device-timestamped binary acquisition and signal-processing analysis for microcontroller-based research sensors'
tags:
  - Python
  - research instrumentation
  - Raspberry Pi Pico
  - serial acquisition
  - real-time visualization
  - signal processing
authors:
  - name: Hirotaka Tominaga
    orcid: 0000-0002-7234-5708
    affiliation: 1
affiliations:
  - index: 1
    name: Division of Mathematical Analysis, Education and Research Center for Community Medicine, Faculty of Medicine, Saga University, Japan
date: 13 October 2026
bibliography: paper.bib
---

# Summary

Low-cost microcontroller boards such as the Raspberry Pi Pico are
increasingly used to build custom data-acquisition front ends for
research instruments -- reading a microphone, an accelerometer, a
temperature sensor, or a biomedical signal such as an electrocardiogram.
`sensor-bridge` is a Python/PyQt5 framework that turns this into a
reusable system rather than a one-off script. It separates the problem
into three layers: a small firmware sketch that timestamps every sample
on the microcontroller itself, in microseconds, and sends it as a
compact binary frame; a live-acquisition application (`get.py`) that
automatically detects connected boards and plots incoming data in real
time; and a post-hoc analysis application (`plot.py`) that reopens a
recording for spectral, wavelet, and peak-detection analysis with
Excel/CSV export. A new sensor is supported by writing a firmware
sketch and a declarative `.ini` configuration file, without touching
the shared application code.

# Statement of need

Researchers building their own low-cost measurement instruments around
Arduino-, ESP32-, or Pico-class boards typically write the acquisition
software for each project from scratch: a text-based serial protocol
(`Serial.println(...)`) read and timestamped on the host PC. This is
adequate for slow, exploratory measurements, but it introduces two
problems once timing matters. First, parsing and re-serializing ASCII
text costs CPU time that a fixed-width binary read avoids. Second, and
more importantly, timestamping a sample only when it arrives at the
host conflates the true sampling interval with PC-side operating-system
scheduling and GUI-redraw jitter, silently corrupting the very timing
information many measurements depend on. `sensor-bridge` targets
researchers and instructors who need both of these problems solved
without building bespoke acquisition software for every new sensor:
every sample is timestamped on the microcontroller itself, at the
moment of acquisition, and transmitted as a binary frame rather than
delimited text, while live acquisition and post-hoc analysis remain
separate applications sharing one reproducible on-disk recording
format.

# State of the field

Comparable acquisition software exists and is acknowledged rather than
claimed superseded. Octopus Sensing [@octopus_sensing] targets
synchronized multi-device acquisition (EEG/GSR/PPG/camera); CRAPPY
[@crappy] is a broader laboratory control/acquisition framework;
WicdPico [@wicdpico] is a CircuitPython-based Raspberry Pi Pico 2 W
platform with a web GUI, closest to `sensor-bridge` in target hardware;
DUGseis [@dugseis] handles real-time seismo-acoustic waveform
acquisition. Beyond these, pyPhotometry [@pyphotometry] and pyControl
[@pycontrol] pair device firmware with a Python host application for
fiber-photometry and behavioural-neuroscience experiments respectively,
and Open Ephys [@openephys] is a widely used open-source platform for
multichannel electrophysiology. The Pico itself has separately been
used for single-purpose instruments, e.g. a gamma-ray spectrometer
[@picogamma], and an ESP32-based system exists for photoplethysmography
(PPG) acquisition [@esp32ppg]. None of the above combine device-side
timestamping, binary framing, multi-board parallel operation, and an
integrated time-series/spectrum/wavelet/peak-detection suite for
Pico/Arduino-class hardware in one package -- `sensor-bridge`'s
contribution is this combination, not any single technique in
isolation. The closest conceptual analog is the Harp protocol
[@harp] -- device-side hardware timestamping plus clock synchronization
across devices -- but it targets custom neuroscience hardware rather
than low-cost Pico/Arduino-class boards and delegates analysis to an
external tool. Where multi-device clock synchronization is itself the
goal, dedicated infrastructure such as Lab Streaming Layer [@lsl]
performs clock-offset correction across independently clocked devices;
`sensor-bridge` does not attempt this, since its target use case is one
or a few boards needing both live monitoring and later signal-processing
analysis, not large synchronized sensor networks.

# Software design

The firmware layer (one `.ino` sketch per board, built for RP2040/RP2350
via the community earlephilhower/arduino-pico core) implements a common
single-character command protocol and reports back a self-describing
handshake -- binary struct layout, unit-conversion functions, measured
timing -- so the host application never hard-codes a board's data
format. This choice trades a small amount of firmware complexity for
letting `get.py` support an open-ended set of boards through
configuration alone. `get.py` writes recordings incrementally as a
`.dat`/`.cpt` pair: `.dat`'s header, once written, is never modified
again, so a crash or disconnection mid-recording still leaves it intact
and readable; marks placed during the session are instead captured in
`.cpt`, written once at a clean stop. `plot.py` reopens either file for
FFT spectra, continuous wavelet transform, a configurable smoothing
pipeline, peak detection, and Excel/CSV export. Keeping live
acquisition and post-hoc analysis as separate applications sharing one
recording format means an experiment is never re-run merely to change
how it is filtered or displayed -- a design decision that matters most
for expensive or non-repeatable measurements, such as human-subject
exercise trials. Per-board GUI layout is declared in a `<board>.ini`
file whose `[code]` section is literal Python, evaluated at load time
-- a config-as-code approach (mirroring precedent such as Sphinx's
`conf.py`) chosen so a new sensor is added by writing a firmware sketch
and an `.ini` file, not by modifying shared application code; this
trusts the `.ini` the same way any other developer-authored script is
trusted, and is documented as such.

# Research impact statement

`sensor-bridge`'s acquisition approach has a multi-year history of real
use that predates this submission. The same generic analog-ADC front
end it still uses today was used for several years in undergraduate
physics laboratory courses taught by the author, with students
connecting microphones, electrocardiogram (ECG), and electromyography
(EMG) sensors; by 2020 the same codebase was already acquiring
photoplethysmography (PPG) data in the author's own research
[@tominaga2023nagasaki; @tominaga2024jps; @tominaga2025kumamoto]. Most
recently, students in an undergraduate medical-physics electronics
practicum at Saga University installed the software on their own
laptops -- a heterogeneous mix of 105 Windows 11 and macOS machines --
to acquire and analyze microphone, ECG, EMG, temperature/humidity
(SHT35), and custom PPG-circuit signals; it ran successfully on every
machine used. Independently of this teaching use, the PPG acquisition
and calibration support in the current codebase was developed as the
acquisition system for a manuscript in preparation for submission to
*Physiological Measurement*. Device-reported sampling-interval
precision, measured from six real LIS3DH accelerometer recordings
across its available output data rates, stayed between 0.0061% and
0.2719% coefficient of variation, reproducible from the repository via
`scripts/measure_timing_precision.py`.

# AI usage disclosure

The overall software architecture and its design decisions --
device-side microsecond timestamping, the binary self-describing wire
protocol, separating live acquisition from post-hoc analysis, and the
firmware/`.ini` extension mechanism -- were conceived by the author
prior to, and independently of, any AI assistance, as described in the
Research impact statement above. Claude (Claude Sonnet 5, Anthropic), an
AI coding and writing assistant, was applied afterward to this already
working codebase to help implement further features (including
multi-board support and additional sensor configurations), debug, test,
and document the software, and to help draft and organize this
manuscript and the accompanying repository documentation. The author
reviewed, verified, and edited all AI-assisted content and code, and
additionally verified hardware-facing firmware changes against real
Pico hardware before trusting them, as documented in the repository's
hardware-verification matrix (`README.md`). The author takes full
responsibility for the content of this paper and the software it
describes.

# Acknowledgements

This work was supported in part by JSPS KAKENHI Grant Number 19K11669
(Grant-in-Aid for Scientific Research (C)).

# References
