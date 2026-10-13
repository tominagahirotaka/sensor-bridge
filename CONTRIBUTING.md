# Contributing to sensor-bridge

sensor-bridge is maintained by a single academic author alongside teaching
and research duties, so response times vary, but contributions and
questions are welcome.

## Reporting a bug or problem

Open a [GitHub issue](https://github.com/tominagahirotaka/sensor-bridge/issues).
Please include:

- what you did (command run, board/sensor involved, `.ini` used)
- what you expected to happen
- what actually happened (full error output/traceback if any)
- your OS and Python version

## Proposing a change

1. Open an issue first for anything beyond a small fix, so the approach
   can be discussed before you invest time in it.
2. Fork the repository and create a branch for your change.
3. Run the test suite (`python3 -m pytest -q`) before opening a pull
   request, and add tests for new behavior where practical.
4. If you add or change firmware (`firmware/Arduino/*.ino`), verify it
   builds with `scripts/build_firmware.py --sketch <Name>` and, if you
   have the hardware, confirm it on a real board -- note in the pull
   request whether real-hardware testing was done.
5. Open a pull request describing the change and why it's needed.

## Adding a new sensor board

See [`docs/adding-a-board.md`](docs/adding-a-board.md) for the full
procedure and verification checklist; this is the most common kind of
contribution and has a dedicated guide.

## Getting support

For questions not suited to a public issue, contact the support email
listed in the repository's Code metadata (see `README.md`).
