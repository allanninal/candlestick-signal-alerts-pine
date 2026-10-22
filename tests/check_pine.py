# SPDX-License-Identifier: LicenseRef-PolyForm-Noncommercial-1.0.0 (see LICENSE)
"""Check pine/CandlestickSignalAlerts.pine against tests/reference.py, bar by bar, with PineTS (a local Pine v6 runtime).

    cd tests/runner && npm install && cd ../..
    python3 tests/check_pine.py <bars dir>
<bars dir> holds <SYMBOL>_<TF>.csv files with the columns time (unix ms), open, high, low, close[, volume], oldest first.

Parity: the bullish and bearish pattern masks the script plots (data window) equal the reference's on every bar, for
each configuration below. Repaint: the script is re-run on the series cut at three points; every bar before a cut must
read the same as in the full run (a closed bar never changes when later bars arrive)."""
import argparse
import os
import subprocess
import sys
import tempfile
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from reference import ALL, NP, run  # noqa: E402

PINE = HERE.parent / "pine" / "CandlestickSignalAlerts.pine"
RUNNER = HERE / "runner" / "run_pine.mjs"
PLOTS = ["Bullish patterns (bit mask)", "Bearish patterns (bit mask)"]
NODOJI = tuple(i != 6 for i in range(NP))
# tag: (PineTS input overrides keyed by input title, reference pattern switches)
CONFIGS = {
    "default": ({}, ALL),
    "no_doji": ({"Doji": False}, NODOJI),
}


def pine_run(bars_csv, inputs):
    with tempfile.NamedTemporaryFile(suffix=".csv", delete=False) as t:
        out = t.name
    cmd = ["node", str(RUNNER), str(PINE), str(bars_csv), out]
    for k, v in inputs.items():
        cmd += ["--input", f"{k}={str(v).lower() if isinstance(v, bool) else v}"]
    subprocess.run(cmd + PLOTS, check=True, capture_output=True, text=True)
    d = pd.read_csv(out)
    os.unlink(out)
    return [d[p].fillna(-1).astype(int).to_numpy() for p in PLOTS]


def expected(b, use):
    rows = run(*(b[k].to_numpy(float) for k in ("open", "high", "low", "close")), use=use)
    bull = np.array([sum(1 << p for p, d in r["ev"] if d > 0) for r in rows])
    bear = np.array([sum(1 << p for p, d in r["ev"] if d < 0) for r in rows])
    return bull, bear


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("bars")
    a = ap.parse_args()
    series = sorted(Path(a.bars).glob("*.csv"))
    ok = True
    for tag, (inputs, use) in CONFIGS.items():
        events = bad = 0
        for f in series:
            b = pd.read_csv(f)
            got = pine_run(f, inputs)
            exp = expected(b, use)
            for g, e in zip(got, exp):
                events += int((e > 0).sum())
                miss = np.where(g != e)[0]
                bad += len(miss)
                for i in miss[:3]:
                    print(f"  {tag} {f.stem} bar {i}: pine {g[i]} reference {e[i]}")
        print(f"parity {tag}: {len(series)} series, {events} pattern bars, {bad} mismatches")
        ok &= bad == 0
    # repaint: cut each series at three points and compare with the full run (default inputs)
    changed = checked = 0
    for f in series:
        b = pd.read_csv(f)
        full = pine_run(f, {})
        n = len(b)
        for cut in (n // 2, n - 300, n - 1):
            with tempfile.NamedTemporaryFile(suffix=".csv", delete=False, mode="w") as t:
                b.iloc[:cut].to_csv(t, index=False)
            part = pine_run(t.name, {})
            os.unlink(t.name)
            for g, fu in zip(part, full):
                checked += cut
                changed += int((g[:cut] != fu[:cut]).sum())
    print(f"repaint: {checked} bar values re-read after cuts, {changed} changed")
    ok &= changed == 0
    print("ALL PASS" if ok else "FAIL")
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
