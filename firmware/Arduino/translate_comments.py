#!/usr/bin/env python3
"""One-time EN translation of the Japanese `//` comments in the Pico .ino
firmware sources, for the public (SoftwareX) release.

Unlike translate_ini.py, this is intentionally one-directional: firmware has
no interactive language switch (no CLI, no GUI), so there's nothing to
toggle at runtime. The lab's working copies (../../sensor-bridge/Arduino/)
keep their original Japanese comments; this script only produces the
English mirror committed here.

Usage:
    python3 translate_comments.py <src.ino> <dst.ino>
"""

import sys
from pathlib import Path

# Every Japanese comment found across all 7 .ino files (verified exhaustively
# with a Unicode-range grep before writing this table) maps to exactly one
# of these phrases. Plain substring replacement is safe here because each
# phrase only ever appears inside a trailing `//` comment, never inside a
# string literal the firmware sends over serial.
PHRASES = [
    ("余裕をもって20％増した", "with a 20% margin added"),
    ("Startの印として書き出しておく", "written out as a Start marker"),
    ("4pin->GND 高価; 4pin->VDD(or OPEN) 秋月電子",
     "4pin->GND expensive; 4pin->VDD(or OPEN) Akizuki Denshi"),
    ("Deviceにモードの設定cmd送り check existence",
     "Send mode-setting cmd to device, check existence"),
    ("Wireの初期化(Pin設定)", "Initialize Wire (pin setup)"),
]


def translate(text):
    for ja, en in sorted(PHRASES, key=lambda p: len(p[0]), reverse=True):
        text = text.replace(ja, en)
    return text


def main():
    src, dst = Path(sys.argv[1]), Path(sys.argv[2])
    dst.parent.mkdir(parents=True, exist_ok=True)
    dst.write_text(translate(src.read_text(encoding="utf-8")), encoding="utf-8")
    print(f"[INFO] {src} -> {dst}")


if __name__ == "__main__":
    main()
