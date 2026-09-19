#!/usr/bin/env python3
"""Build every firmware/Arduino/*/ sketch for every board variant in one
shot, producing firmware/<Sketch>.ino.<variant>.uf2 for each combination
(the files committed under firmware/).

Self-contained: locates arduino-cli, and installs the rp2040:rp2040 core
if it isn't already present, rather than assuming a pre-configured
environment. All arduino-cli invocations pass --additional-urls directly
(instead of relying on a persistent config file), so this works
regardless of what arduino-cli config, if any, already exists.

Usage:
    python3 scripts/build_firmware.py                       # everything
    python3 scripts/build_firmware.py --sketch LIS3DH_SPI    # one sketch, all boards
    python3 scripts/build_firmware.py --board rpipico2       # all sketches, one board
    python3 scripts/build_firmware.py --sketch LIS3DH_SPI --board rpipico2
"""
import argparse
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
ARDUINO_DIR = REPO_ROOT / 'firmware' / 'Arduino'
FIRMWARE_DIR = REPO_ROOT / 'firmware'

RP2040_INDEX_URL = ('https://github.com/earlephilhower/arduino-pico/'
                     'releases/download/global/package_rp2040_index.json')

# variant name (as used in the committed .uf2 filenames) -> FQBN suffix
BOARDS = {
    'rpipico': 'rp2040:rp2040:rpipico',
    'rpipico2': 'rp2040:rp2040:rpipico2',
    'rpipicow': 'rp2040:rp2040:rpipicow',
    'rpipico2w': 'rp2040:rp2040:rpipico2w',
}


def find_arduino_cli():
    """Prefer arduino-cli on PATH; fall back to known install locations
    seen on this machine (a bundled Arduino IDE copy is more durable than
    a standalone download under /tmp, which may not survive a reboot)."""
    on_path = shutil.which('arduino-cli')
    if on_path:
        return on_path
    candidates = [
        Path.home() / 'Downloads' / 'WorkForArduino' / 'arduino-ide_2.3.2_Linux_64bit'
        / 'resources' / 'app' / 'lib' / 'backend' / 'resources' / 'arduino-cli',
        Path('/tmp/arduino-cli-bin/arduino-cli'),
    ]
    for c in candidates:
        if c.is_file():
            return str(c)
    sys.exit("arduino-cli not found on PATH or in known fallback locations. "
             "Install it (https://arduino.github.io/arduino-cli/) or add it to PATH.")


def ensure_core_installed(cli):
    result = subprocess.run(
        [cli, 'core', 'list', '--additional-urls', RP2040_INDEX_URL],
        capture_output=True, text=True)
    if 'rp2040:rp2040' in result.stdout:
        return
    print("rp2040:rp2040 core not found -- installing (one-time, may take a while)...")
    subprocess.run([cli, 'core', 'update-index', '--additional-urls', RP2040_INDEX_URL],
                    check=True)
    subprocess.run([cli, 'core', 'install', 'rp2040:rp2040',
                     '--additional-urls', RP2040_INDEX_URL], check=True)


def discover_sketches():
    """Every firmware/Arduino/<Sketch>/ directory containing a matching
    <Sketch>.ino is a buildable sketch; discovered rather than hardcoded
    so a new board added per docs/adding-a-board.md is picked up
    automatically."""
    sketches = []
    for d in sorted(ARDUINO_DIR.iterdir()):
        if d.is_dir() and (d / f'{d.name}.ino').is_file():
            sketches.append(d.name)
    return sketches


def build_one(cli, sketch, variant):
    fqbn = BOARDS[variant]
    sketch_dir = ARDUINO_DIR / sketch
    with tempfile.TemporaryDirectory() as tmp:
        result = subprocess.run(
            [cli, 'compile', '--fqbn', fqbn, '--output-dir', tmp,
             '--additional-urls', RP2040_INDEX_URL, str(sketch_dir)],
            capture_output=True, text=True)
        if result.returncode != 0:
            return False, result.stdout + result.stderr
        built = Path(tmp) / f'{sketch}.ino.uf2'
        if not built.is_file():
            return False, f"compile reported success but {built.name} was not produced"
        dest = FIRMWARE_DIR / f'{sketch}.ino.{variant}.uf2'
        shutil.copyfile(built, dest)
        return True, str(dest.relative_to(REPO_ROOT))


def main():
    parser = argparse.ArgumentParser(description=__doc__,
                                      formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--sketch', help='build only this sketch (e.g. LIS3DH_SPI, '
                                          'i.e. the firmware/Arduino/PICO_<sketch>/ directory '
                                          'name with the PICO_ prefix dropped)')
    parser.add_argument('--board', choices=sorted(BOARDS), help='build only this board variant')
    args = parser.parse_args()

    cli = find_arduino_cli()
    ensure_core_installed(cli)

    sketches = discover_sketches()
    if args.sketch:
        wanted = f'PICO_{args.sketch}'
        if wanted not in sketches:
            sys.exit(f"No such sketch {wanted!r}. Available: "
                      f"{', '.join(s.removeprefix('PICO_') for s in sketches)}")
        sketches = [wanted]
    variants = [args.board] if args.board else sorted(BOARDS)

    total = len(sketches) * len(variants)
    failures = []
    n = 0
    for sketch in sketches:
        for variant in variants:
            n += 1
            print(f"[{n}/{total}] {sketch} -> {variant} ...", end=' ', flush=True)
            ok, msg = build_one(cli, sketch, variant)
            print("OK" if ok else "FAILED")
            if ok:
                print(f"    {msg}")
            else:
                print(f"    {msg.strip()[:500]}")
                failures.append((sketch, variant))

    print(f"\n{total - len(failures)}/{total} combinations built successfully.")
    if failures:
        print("Failed:")
        for sketch, variant in failures:
            print(f"  {sketch} / {variant}")
        sys.exit(1)


if __name__ == '__main__':
    main()
