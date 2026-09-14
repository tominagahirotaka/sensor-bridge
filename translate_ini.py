#!/usr/bin/env python3
"""Translate the [code] section of a sensor-bridge board .ini file between
English and Japanese.

Board .ini files (Analog.ini, SHT35.ini, DPG_*.ini, ...) are authored per
sensor/circuit by whoever wires it up, and their [code] section is literal
Python source (menu labels, dialog field labels, etc.) that get exec()'d at
runtime -- so unlike get.py/plot.py, they aren't good candidates for the
--lang runtime switch in mylib/i18n.py. Instead: keep one canonical English
.ini per board, and derive a `<name>_jp.ini` counterpart (or the reverse)
with this script, so both can be maintained from the same phrase table
below.

Usage:
    ./translate_ini.py default.ini --to ja            # -> default_jp.ini
    ./translate_ini.py default_jp.ini --to en          # -> default.ini
    ./translate_ini.py Analog.ini --to ja -o out.ini   # explicit output path

Only text inside the [code] section is touched; [main]/[notsave]/[board]
(config values and their comments) are left untouched, matching how
mylib/i18n.py scopes translation to runtime-visible text rather than
developer-facing comments.
"""

import argparse
import re
import sys
from pathlib import Path

# (English, Japanese) pairs. Applied whole-file within the [code] section,
# longest phrase first, so e.g. "Test(not recording)" is replaced before the
# bare "Test" that also appears (as a panel1 dict key) -- otherwise the short
# rule would fire first and corrupt the longer phrase's own match.
PHRASE_PAIRS = [
    # --- subject_template (demographic fields) ---
    ("Name", "氏名"),
    ("Height (cm)", "身長(cm)"),
    ("Weight (kg)", "体重(kg)"),
    ("Date of birth", "生年月日"),
    ("Gender", "性別"),
    ("Male", "男"),
    ("Female", "女"),
    ("Systolic BP (mmHg)", "収縮期血圧(mmHg)"),
    ("Diastolic BP (mmHg)", "拡張期血圧(mmHg)"),
    ("Heart rate (bpm)", "心拍数(bpm)"),
    ("1st", "1回目"),
    ("2nd", "2回目"),
    ("3rd", "3回目"),
    ("Resting heart rate (average):", "平常時心拍数(average):"),
    ("Target heart rate", "目標心拍数"),

    # --- SHT35.ini subject_template / after_subject_window ---
    ("Measurement Room", "測定室"),
    ("Room: ", "測定室:"),
    ("Measurement Device", "測定装置"),
    ("Device: ", "装置:"),
    ("Operator", "測定者"),
    ("Operator: ", "測定者:"),
    ("/sec", "回/sec"),

    # --- DPG_X95840W*.ini param_setting_template ---
    # μ = Greek small letter mu (matches source .ini files, not U+00B5 micro sign)
    ("interval (μs)", "時間間隔(μs)"),
    ("0..minimum interval", "0..最小時間"),
    ("ADC read count", "ADC実行回数"),
    ("Max voltage (V)", "最大電圧(V)"),
    ("calib_wait time after value change (msec)", "calib_値変更後待機時間(msec)"),
    ("calib_amplitude detection time (msec)", "calib_振動幅検出時間(msec)"),
    (r"Max amplitude\nPort1", r"最大振幅\nPort1"),
    (r"Tuning width\nPort1", r"調整幅\nPort1"),
    ("Save folder name", "保存Folder名"),
    ("Plot points", "描画点数"),
    ("ADC resolution", "ADC精度"),

    # --- menubar / panel1 button & menu labels ---
    ("Test(not recording)", "テスト（記録なし）"),
    ("Run(recording)", "実行（記録中）"),
    ("Mark(checkpoint)", "マーク（チェックポイント）"),
    ("mArk(=Mark)", "マーク（=Mark）"),
    ("caliBration(not recording)", "キャリブレーション（記録なし）"),
    ("Information", "測定情報"),
    ("Parameter", "パラメータ設定"),
    ("Mark", "マーク"),
    ("mArk", "マーク"),
    ("Stop", "停止"),
    ("Quit", "終了"),
    ("caliBrate", "キャリブレーション"),
    ("Calibrate", "キャリブレーション"),
    ("Test", "テスト"),
    ("Run", "実行"),
]

CODE_SECTION_RE = re.compile(r"^\[code\]\s*$", re.MULTILINE)


def translate_text(text, to_lang):
    """Replace EN<->JA phrases in `text` for direction `to_lang` ('en'/'ja')."""
    if to_lang == "ja":
        pairs = [(en, ja) for en, ja in PHRASE_PAIRS]   # search EN, replace JA
    elif to_lang == "en":
        pairs = [(ja, en) for en, ja in PHRASE_PAIRS]   # search JA, replace EN
    else:
        raise ValueError(f"unsupported --to value: {to_lang!r}")

    # Longest source phrase first so a short phrase can't pre-empt (and
    # corrupt) a longer phrase that contains it.
    pairs.sort(key=lambda pair: len(pair[0]), reverse=True)
    for src, dst in pairs:
        text = text.replace(src, dst)
    return text


def translate_ini(content, to_lang):
    """Translate only the [code] section of an .ini file's raw content."""
    m = CODE_SECTION_RE.search(content)
    if not m:
        raise ValueError("no [code] section found; refusing to translate the whole file")
    head, tail = content[:m.end()], content[m.end():]
    return head + translate_text(tail, to_lang)


def default_output_path(input_path, to_lang):
    stem = input_path.stem
    if to_lang == "ja":
        if stem.endswith("_jp"):
            return input_path  # already a _jp file; overwrite in place
        return input_path.with_name(f"{stem}_jp{input_path.suffix}")
    else:
        if stem.endswith("_jp"):
            return input_path.with_name(f"{stem[:-3]}{input_path.suffix}")
        return input_path  # already the English original; overwrite in place


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("input", type=Path, help="source .ini file")
    parser.add_argument("--to", dest="to_lang", choices=("en", "ja"), required=True,
                        help="target language for the [code] section")
    parser.add_argument("-o", "--output", type=Path, default=None,
                        help="output path (default: derived from --to, e.g. X.ini -> X_jp.ini)")
    args = parser.parse_args()

    content = args.input.read_text(encoding="utf-8")
    translated = translate_ini(content, args.to_lang)

    out_path = args.output or default_output_path(args.input, args.to_lang)
    out_path.write_text(translated, encoding="utf-8")
    print(f"[INFO] {args.input} --({args.to_lang})--> {out_path}")


if __name__ == "__main__":
    main()
