#!/usr/bin/env python3
"""Batch-flash one firmware onto many boards: plug a Pico in BOOTSEL mode
(hold BOOTSEL while connecting USB), it gets flashed automatically, unplug
it, plug the next one in -- repeat until Ctrl+C. Intended for flashing a
whole class set of boards with the same firmware.

Requires firmware/<Sketch>.ino.<board>.uf2 to already exist -- run
scripts/build_firmware.py first if it doesn't.

IMPORTANT LIMITATION: a board in BOOTSEL mode can only be identified as
RP2040-family (Pico/Pico W) or RP2350-family (Pico 2/Pico 2 W) -- that
information comes from the chip's own boot ROM. Whether a board is the
plain or the wireless (W) variant is NOT something the boot ROM knows
(the wireless chip is a separate part on the board, invisible to it), so
it cannot be auto-detected. You must say which exact variant you are
flashing via --board; this script only auto-detects the chip generation,
as a safety check against the wrong .uf2 family (e.g. catches trying to
flash an rpipico2 image onto a plain RP2040 Pico), not the W/plain split.

Usage:
    python3 scripts/flash_firmware.py LIS3DH --board rpipico
    python3 scripts/flash_firmware.py DPG_X95840W_LIS3DHx2 --board rpipico2w
"""
import argparse
import glob
import os
import shutil
import sys
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
FIRMWARE_DIR = REPO_ROOT / 'firmware'

# .ini basename (as passed on the command line) -> firmware/Arduino sketch name
INI_TO_SKETCH = {
    'Analog': 'PICO_Analog',
    'DPG_X95840W': 'PICO_DPG_X95840W',
    'DPG_X95840W_LIS3DHx2': 'PICO_DPG_X95840W_LIS3DHx2',
    'LIS3DH': 'PICO_LIS3DH_SPI',
    'SHT35': 'PICO_i2cSHT35',
}

BOARD_CHIP_FAMILY = {
    'rpipico': 'RP2040',
    'rpipicow': 'RP2040',
    'rpipico2': 'RP2350',
    'rpipico2w': 'RP2350',
}

POLL_INTERVAL_S = 1.0


def candidate_bootsel_roots():
    """Directories worth scanning for a mounted BOOTSEL drive, per
    platform. Returns whatever exists; nonexistent roots are skipped."""
    if sys.platform == 'darwin':
        return glob.glob('/Volumes/*')
    if sys.platform.startswith('win'):
        return [f'{chr(letter)}:\\' for letter in range(ord('A'), ord('Z') + 1)]
    # Linux and friends
    user = os.environ.get('USER') or os.environ.get('LOGNAME') or ''
    roots = []
    for pattern in (f'/media/{user}/*', f'/run/media/{user}/*', '/media/*/*', '/mnt/*'):
        roots.extend(glob.glob(pattern))
    return roots


def find_bootsel_drives():
    """Return {mount_path: chip_family} for every currently-mounted
    RP2040/RP2350 BOOTSEL drive, identified by the INFO_UF2.TXT file the
    boot ROM always exposes."""
    found = {}
    for root in candidate_bootsel_roots():
        info = os.path.join(root, 'INFO_UF2.TXT')
        if not os.path.isfile(info):
            continue
        try:
            with open(info, encoding='utf-8', errors='replace') as f:
                text = f.read()
        except OSError:
            continue
        # Confirmed on real hardware: RP2040's INFO_UF2.TXT says
        # "Model: Raspberry Pi RP2" (NOT "RP2040") -- an earlier version
        # of this check assumed the full "RP2040" string, which never
        # matched and misclassified every real RP2040 board as
        # 'unknown'. RP2350's exact wording hasn't been confirmed on
        # real hardware yet, so 'RP2350' is checked first (on the
        # assumption it says the full "RP2350"); the generic 'RP2'
        # fallback below only catches RP2040, since anything saying
        # "RP2350" already matched above.
        if 'RP2350' in text:
            found[root] = 'RP2350'
        elif 'RP2' in text:
            found[root] = 'RP2040'
        else:
            found[root] = 'unknown'
    return found


def main():
    parser = argparse.ArgumentParser(description=__doc__,
                                      formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('ini_name', help='which board config to flash, e.g. LIS3DH '
                                          '(matches the .ini name, without .ini)')
    parser.add_argument('--board', required=True, choices=sorted(BOARD_CHIP_FAMILY),
                         help='exact board variant to flash (cannot be auto-detected; see '
                              'the module docstring for why)')
    args = parser.parse_args()

    sketch = INI_TO_SKETCH.get(args.ini_name)
    if sketch is None:
        sys.exit(f"Unknown ini name {args.ini_name!r}. Known: {', '.join(INI_TO_SKETCH)}")

    uf2_path = FIRMWARE_DIR / f'{sketch}.ino.{args.board}.uf2'
    if not uf2_path.is_file():
        sys.exit(f"{uf2_path} does not exist. Run scripts/build_firmware.py first.")

    expected_family = BOARD_CHIP_FAMILY[args.board]

    print(f"Flashing {uf2_path.relative_to(REPO_ROOT)} ({args.ini_name} / {args.board}).")
    print("Plug boards into BOOTSEL mode one at a time (hold BOOTSEL while "
          "connecting USB). Ctrl+C to stop.\n")

    seen = set()
    flashed_count = 0
    try:
        while True:
            current = find_bootsel_drives()
            for mount, family in current.items():
                if mount in seen:
                    continue
                seen.add(mount)
                if family != expected_family:
                    print(f"  SKIPPED {mount}: detected {family}-family chip, "
                          f"but --board {args.board} expects {expected_family}-family. "
                          f"Wrong board/uf2 -- not flashing.")
                    continue
                try:
                    shutil.copyfile(uf2_path, os.path.join(mount, uf2_path.name))
                    flashed_count += 1
                    print(f"  [{flashed_count}] flashed {mount}")
                except OSError as e:
                    print(f"  ERROR flashing {mount}: {e}")
            # drives that disappeared (board rebooted after flashing, or was
            # unplugged) are forgotten so re-inserting the same board flashes it again
            seen &= set(current)
            time.sleep(POLL_INTERVAL_S)
    except KeyboardInterrupt:
        print(f"\nStopped. {flashed_count} board(s) flashed.")


if __name__ == '__main__':
    main()
