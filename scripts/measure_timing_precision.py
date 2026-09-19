#!/usr/bin/env python3
"""Measure device-reported sampling-interval precision from one or more
recorded .dat files.

This is the repeatable version of the ad hoc computation used to produce
the timing-precision table in the SoftwareX manuscript (see
Projects/Articles/sensor-bridge/docs/sensor_bridge_manuscript_draft.md,
Section 3): for each recording, it decodes the device-side timestamp
column exactly as `plot.py` would (same `ReadData` code path, so this
never drifts from what the application actually parses) and reports the
mean sampling interval, its standard deviation, and the coefficient of
variation (CV = std/mean, as a percentage) -- the metric this project uses
to characterize the consistency of successive intervals between the
Pico's own timestamps around their nominal interval. This is a measure
of precision (repeatability), not absolute accuracy against an
independent external clock reference, which this script does not
evaluate.

It does not ship any recordings itself (board `.dat`/`.cpt` files are
intentionally not versioned; see .gitignore) -- point it at your own
recordings.

Usage:
    python3 scripts/measure_timing_precision.py data/*.dat data_LIS3DH/*.dat
    python3 scripts/measure_timing_precision.py --markdown data_LIS3DH/*.dat
"""
import argparse
import os
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import plot as plotmod  # noqa: E402  (needs QT_QPA_PLATFORM set first)
from mylib.plot_utils.reading import ReadData  # noqa: E402


def measure(filename):
    """Return a dict of sampling-interval precision statistics for one
    .dat recording."""
    sys.argv = ["plot.py", "-f", filename]
    args = plotmod.parse_args()
    rd = ReadData(args)

    t = rd.data_t[0]
    dt = np.diff(t)
    mean_dt = dt.mean()
    std_dt = dt.std(ddof=0)
    return {
        "file": filename,
        "title": rd.header.env_set.get("title"),
        "odr": rd.header.env_set.get("odr"),
        "n_samples": len(t),
        "duration_s": float(t[-1] - t[0]),
        "mean_interval_ms": mean_dt * 1000.0,
        "cv_pct": 100.0 * std_dt / mean_dt,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0],
                                      formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("files", nargs="+", help="one or more recorded .dat files")
    parser.add_argument("--markdown", action="store_true",
                         help="print a markdown table (matches the manuscript's format)")
    args = parser.parse_args()

    rows = [measure(f) for f in args.files]

    if args.markdown:
        print("| Recording | Output data rate | Sampling interval | Samples | Duration | Precision (CV) |")
        print("|---|---|---|---|---|---|")
        for r in rows:
            odr = f"ODR={r['odr']}" if r["odr"] is not None else "fixed"
            print(f"| {r['title']} ({os.path.basename(r['file'])}) | {odr} | "
                  f"{r['mean_interval_ms']:.4f} ms | {r['n_samples']:,} | "
                  f"{r['duration_s']:.1f} s | {r['cv_pct']:.4f}% |")
    else:
        for r in rows:
            print(f"{r['file']}")
            print(f"  title={r['title']}  odr={r['odr']}")
            print(f"  n_samples={r['n_samples']}  duration_s={r['duration_s']:.3f}")
            print(f"  mean_interval_ms={r['mean_interval_ms']:.4f}  CV%={r['cv_pct']:.4f}")


if __name__ == "__main__":
    main()
