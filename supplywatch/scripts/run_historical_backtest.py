"""Runs the real historical backtest (snapshot/backtest.py) and produces:
  - backtest_output/backtest_results.csv  (every material/date/score/factors row)
  - backtest_output/backtest_chart.png    (score trend vs. the real event timeline)

Usage:
    python scripts/run_historical_backtest.py
"""

from __future__ import annotations

import csv
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import matplotlib

matplotlib.use("Agg")
import matplotlib.dates as mdates
import matplotlib.pyplot as plt

from snapshot.backtest import EVENTS, run_backtest

MATERIALS = ["Gallium", "Germanium", "Cobalt", "Lithium", "Yttrium", "Dysprosium", "Indium", "Graphite"]
OUT_DIR = Path(__file__).resolve().parents[1] / "backtest_output"

REE_FOCUS = ["Dysprosium", "Yttrium", "Indium"]  # the materials this specific event sequence targets
BAND_COLORS = {"low": "#34d399", "moderate": "#fbbf24", "elevated": "#f87171"}


def band_color(score: int) -> str:
    if score >= 70:
        return BAND_COLORS["elevated"]
    if score >= 40:
        return BAND_COLORS["moderate"]
    return BAND_COLORS["low"]


def main() -> None:
    OUT_DIR.mkdir(exist_ok=True)
    results = run_backtest(MATERIALS)

    csv_path = OUT_DIR / "backtest_results.csv"
    with open(csv_path, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=["date", "material", "score", "price", "export", "trade"])
        writer.writeheader()
        for r in results:
            writer.writerow(
                {
                    "date": r["date"].isoformat(),
                    "material": r["material"],
                    "score": r["score"],
                    "price": r["factors"]["price"],
                    "export": r["factors"]["export"],
                    "trade": r["factors"]["trade"],
                }
            )
    print(f"Wrote {len(results)} rows to {csv_path}")

    by_material: dict[str, list] = {}
    for r in results:
        by_material.setdefault(r["material"], []).append(r)

    fig, ax = plt.subplots(figsize=(11, 5.5), dpi=150)
    fig.patch.set_facecolor("#0b0e14")
    ax.set_facecolor("#12161f")

    for material in REE_FOCUS:
        rows = sorted(by_material[material], key=lambda r: r["date"])
        dates = [r["date"] for r in rows]
        scores = [r["score"] for r in rows]
        ax.plot(dates, scores, marker="o", markersize=3, linewidth=2, label=material)

    for i, ev in enumerate(EVENTS):
        ax.axvline(ev.date, color="#8b96a5", linestyle="--", linewidth=1, alpha=0.6)
        ax.annotate(
            f"{i + 1}",
            xy=(ev.date, 1.0),
            xycoords=("data", "axes fraction"),
            ha="center",
            va="bottom",
            fontsize=9,
            color="#dfe4eb",
            fontweight="bold",
        )

    ax.set_ylim(0, 100)
    ax.set_ylabel("Disruption score", color="#dfe4eb", fontsize=11)
    ax.set_title(
        "disruption_score() vs. the real China rare-earth export-control escalation\n"
        "(real historical prices + real static concentration + documented event dates; see caption)",
        color="#f2f4f7",
        fontsize=12,
        pad=14,
    )
    ax.xaxis.set_major_locator(mdates.MonthLocator(interval=2))
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%b %Y"))
    ax.tick_params(colors="#9aa5b3")
    for spine in ax.spines.values():
        spine.set_color("#2a3543")
    ax.grid(True, color="#1f2733", linewidth=0.6)
    legend = ax.legend(loc="upper left", facecolor="#12161f", edgecolor="#2a3543", fontsize=9)
    for text in legend.get_texts():
        text.set_color("#dfe4eb")

    caption = "  ".join(f"{i + 1}. {ev.label} ({ev.date.strftime('%b %Y')})" for i, ev in enumerate(EVENTS))
    fig.text(0.02, 0.01, caption, color="#6f7c8e", fontsize=7, wrap=True)

    fig.tight_layout(rect=(0, 0.05, 1, 1))
    chart_path = OUT_DIR / "backtest_chart.png"
    fig.savefig(chart_path, facecolor=fig.get_facecolor())
    print(f"Wrote chart to {chart_path}")


if __name__ == "__main__":
    main()
