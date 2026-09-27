"""Generates a real, data-grounded "current interaction model vs. SupplyWatch"
comparison chart for the conference paper -- NOT a fabricated behavioral
result. It re-renders the exact same real backtest scores (already computed
by run_historical_backtest.py) under two delivery policies:

  - "Alert-only (current)": the score the user actually sees only updates
    when it crosses a risk-band boundary (low/moderate/elevated) -- the
    same threshold-triggered model the paper's Section II describes as the
    status quo. Between crossings, the user's last-known value is stale.
  - "Daily brief (SupplyWatch)": the real, continuous score, visible every
    day regardless of whether a threshold was crossed.

Both series come from the same real disruption_score() output already in
backtest_output/backtest_results.csv -- this shows an information-
availability difference (a property of the architecture), not a claimed
behavioral or engagement outcome, which RQ3 has not tested.

Usage:
    python scripts/make_before_after_chart.py
"""

from __future__ import annotations

import csv
from datetime import datetime
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.dates as mdates
import matplotlib.pyplot as plt

OUT_DIR = Path(__file__).resolve().parents[1] / "backtest_output"
MATERIAL = "Dysprosium"


def band(score: int) -> str:
    if score >= 70:
        return "elevated"
    if score >= 40:
        return "moderate"
    return "low"


def main() -> None:
    rows = [
        r for r in csv.DictReader(open(OUT_DIR / "backtest_results.csv"))
        if r["material"] == MATERIAL
    ]
    rows.sort(key=lambda r: r["date"])
    dates = [datetime.strptime(r["date"], "%Y-%m-%d") for r in rows]
    scores = [int(r["score"]) for r in rows]

    alert_only = []
    last_band = None
    last_value = scores[0]
    for s in scores:
        b = band(s)
        if b != last_band:
            last_value = s
            last_band = b
        alert_only.append(last_value)

    fig, ax = plt.subplots(figsize=(6.5, 3.6), dpi=200)
    ax.step(dates, alert_only, where="post", color="#9aa5b3", linewidth=1.6,
             linestyle="--", label="Alert-only (current): updates only on a band crossing")
    ax.plot(dates, scores, color="#2563eb", linewidth=2.0,
            label="Daily brief (SupplyWatch): continuous, real score every day")

    for boundary in (40, 70):
        ax.axhline(boundary, color="#d1d5db", linewidth=0.8, linestyle=":")

    ax.set_ylim(0, 100)
    ax.set_ylabel("Disruption score")
    ax.set_title(f"{MATERIAL}: information a user actually sees, same real scoring data")
    ax.xaxis.set_major_locator(mdates.MonthLocator(interval=3))
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%b %Y"))
    ax.grid(True, color="#f0f0f0", linewidth=0.6)
    ax.legend(loc="upper left", fontsize=8, frameon=False)
    fig.tight_layout()

    out_path = OUT_DIR / "interaction_model_comparison.png"
    fig.savefig(out_path, facecolor="white")
    print(f"Wrote {out_path}")


if __name__ == "__main__":
    main()
