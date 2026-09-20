"""Historical backtest against the real China rare-earth export-control
escalation (Feb 2025 - Jul 2026).

Uses the same, unmodified disruption_score() as the live pipeline. Two of
its three input signals are genuinely real historical data:

  - price_delta: real historical close prices via yfinance (the same proxy
    tickers as the live USGSIngestor), trailing-2-week % change computed
    at each historical checkpoint date.
  - trade_hhi: the same static, real USGS-sourced concentration table used
    live (concentration doesn't move week to week, so a constant value is
    the honest choice for both live and historical use).

The third signal, export/news-control intensity, cannot be sourced live:
Google News RSS has no historical date-range query, and GDELT (the
free alternative) was unreachable from this environment. Rather than
fabricate headline counts for past dates, this uses an event-study
approach: a documented, dated, cited sequence of real MOFCOM policy
actions (see EVENTS below) drives an explicit intensity step-function per
material. This is a real, verifiable, and transparently-declared
methodology substitution — not synthetic data standing in for a metric it
doesn't actually represent.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta

import yfinance as yf

from ingest.comtrade import TRADE_HHI
from ingest.usgs import PRICE_TICKERS
from signals.models import MaterialSignal
from signals.scorer import disruption_score


@dataclass(frozen=True)
class Event:
    date: date
    label: str
    description: str
    source: str


# Verified against IEA policy database, CSET/Georgetown MOFCOM notice
# translations, CSIS, European Parliament Research Service, S&P Global,
# and SCMP (cross-checked Sept 2026). See report Chapter 2/6 references.
EVENTS: list[Event] = [
    Event(
        date(2025, 2, 4),
        "Indium licensing controls",
        "MOFCOM/GACC export-license requirement covering tungsten, tellurium, "
        "bismuth, molybdenum, and indium-related items (41 items).",
        "IEA policy database; China Briefing",
    ),
    Event(
        date(2025, 4, 4),
        "Heavy rare-earth export controls",
        "MOFCOM adds 7 medium/heavy rare earths (incl. dysprosium, yttrium) "
        "and related magnet materials to the export control list, "
        "requiring licenses for export to all countries.",
        "CSIS; China Briefing",
    ),
    Event(
        date(2025, 10, 9),
        "Second-wave controls announced",
        "MOFCOM Notice 2025 No. 61 adds 5 more rare earths, extends controls "
        "to processing/extraction technology, and introduces a 0.1% "
        "Chinese-content extraterritorial rule.",
        "CSET/Georgetown MOFCOM Notice 2025 No. 61 translation",
    ),
    Event(
        date(2025, 11, 7),
        "Second-wave controls suspended",
        "Suspended ahead of its Nov 8 effective date, following the "
        "Trump-Xi Busan summit (Oct 30, 2025) and a broader trade truce, "
        "through Nov 10, 2026.",
        "European Parliament Research Service; Clark Hill",
    ),
    Event(
        date(2026, 6, 15),
        "US entity export ban",
        "10 US firms added to China's Export Control Watchlist, restricting "
        "Chinese exporters from supplying them dual-use items including "
        "rare earths and magnets.",
        "S&P Global",
    ),
    Event(
        date(2026, 7, 24),
        "EU entity export ban",
        "14 named EU entities (incl. Rheinmetall, IHC Merwede) added to the "
        "same watchlist -- a distinct, entity-specific action, not an "
        "extension of the suspended Oct 2025 content-based rule.",
        "S&P Global; SCMP; Table.Briefings",
    ),
]

BACKTEST_START = date(2025, 1, 6)
BACKTEST_END = date(2026, 9, 14)

# Materials named directly in the real event sequence above.
HEAVY_REE_MATERIALS = {"Dysprosium", "Yttrium"}
INDIUM_MATERIAL = "Indium"
# Controlled since Aug 2023 / Dec 2024, i.e. before this backtest window
# starts -- held at a constant elevated level throughout, which is the
# accurate representation rather than an artificial spike mid-window.
PRE_CONTROLLED_MATERIALS = {"Gallium", "Germanium"}


def export_intensity(material: str, as_of: date) -> int:
    """Documented-event-driven proxy for export/news-control intensity.

    Returns an integer on the same 0-5 scale the live SanctionsIngestor's
    real headline count would occupy after scorer.py's `* 20` scaling
    (i.e. this is deliberately NOT a headline count -- it is what the
    live signal is scaled to represent, min(100, mentions * 20)).
    """
    if material in PRE_CONTROLLED_MATERIALS:
        return 3  # constant: real controls predate this backtest window

    if material == INDIUM_MATERIAL:
        return 3 if as_of >= EVENTS[0].date else 0

    if material in HEAVY_REE_MATERIALS:
        level = 0
        if as_of >= EVENTS[1].date:  # heavy REE controls
            level = 3
        if EVENTS[2].date <= as_of < EVENTS[3].date:  # second wave, pre-suspension
            level = 5
        if as_of >= EVENTS[3].date:  # suspended, back to the Apr 2025 baseline
            level = 3
        if as_of >= EVENTS[5].date:  # renewed entity-list tension (EU)
            level = 4
        elif as_of >= EVENTS[4].date:  # renewed entity-list tension (US)
            level = 4
        return level

    # Materials outside this specific Chinese rare-earth control regime
    # (Cobalt, Lithium, Graphite): their own real risk drivers (DRC supply,
    # Australia/Chile concentration, etc.) are out of scope for this
    # particular backtest, which is anchored specifically to the China
    # rare-earth escalation -- held at a low, constant baseline here.
    return 1


def _price_history(ticker: str):
    return yf.Ticker(ticker).history(start="2024-12-01", end="2026-09-20", auto_adjust=True)


def historical_price_delta(material: str, as_of: date, price_data: dict) -> float:
    """Real trailing-2-week % price change ending at `as_of`, averaged
    across the material's proxy tickers, computed from already-fetched
    real yfinance history (no re-querying per date)."""
    deltas: list[float] = []
    window_start = as_of - timedelta(days=14)
    for ticker in PRICE_TICKERS.get(material, []):
        hist = price_data.get(ticker)
        if hist is None or hist.empty:
            continue
        window = hist.loc[str(window_start):str(as_of)]
        if len(window) < 2:
            continue
        prev = float(window["Close"].iloc[0])
        cur = float(window["Close"].iloc[-1])
        if prev:
            deltas.append((cur - prev) / prev * 100)
    return round(sum(deltas) / len(deltas), 2) if deltas else 0.0


def run_backtest(materials: list[str], checkpoint_days: int = 7) -> list[dict]:
    """Compute the real, existing disruption_score() at weekly checkpoints
    across the backtest window, using real historical prices + real static
    HHI + the documented-event export-intensity proxy. Returns a flat list
    of {material, date, score, factors} rows -- callers persist or plot."""
    all_tickers = sorted({t for m in materials for t in PRICE_TICKERS.get(m, [])})
    price_data = {t: _price_history(t) for t in all_tickers}

    results = []
    d = BACKTEST_START
    while d <= BACKTEST_END:
        for material in materials:
            signal = MaterialSignal(
                material=material,
                source="backtest",
                price_delta=historical_price_delta(material, d, price_data),
                export_mentions=export_intensity(material, d),
                trade_hhi=TRADE_HHI.get(material, 3000),
            )
            score, factors = disruption_score([signal])
            results.append({"material": material, "date": d, "score": score, "factors": factors})
        d += timedelta(days=checkpoint_days)
    return results
