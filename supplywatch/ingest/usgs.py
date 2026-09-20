"""Price-direction signal via free yfinance ETF/equity proxy tickers, with
Twelve Data and Finnhub as documented free-tier fallbacks if yfinance (an
unofficial scraper that can silently break) returns nothing usable.

Named USGSIngestor for consistency with the existing (pre-semester)
BaseIngestor pattern; there is no free live USGS API for price data, so
this fetches price direction from public-market proxies instead. The
actual USGS-sourced data (Mineral Commodity Summaries concentration
figures) lives in ComtradeIngestor.

Fallback chain (each step only runs if the previous one returned no usable
data, not just a flat 0% -- those are genuinely different outcomes):
  1. yfinance, trailing 2-week % change (free, no key, existing default)
  2. Twelve Data /time_series, same trailing-2-week methodology (free tier:
     800 requests/day -- https://twelvedata.com/pricing). Needs
     TWELVEDATA_API_KEY; silently skipped if unset.
  3. Finnhub /quote, latest-day % change only -- a narrower window than the
     other two, used only as a last resort (free tier: 60 calls/min --
     https://finnhub.io/pricing). Needs FINNHUB_API_KEY; silently skipped
     if unset.
  4. Neutral 0.0, same as before this fallback chain existed.

Alpha Vantage was evaluated and rejected: its free tier has shrunk to 25
requests/day, too low to cover 8 materials reliably.

All network calls (including the fallbacks) are blocking, so they run off
the event loop via asyncio.to_thread. yfinance's own result is cached for
DEFAULT_TTL_SECONDS (core/cache.py) since the daily job only needs a fresh
value once a day; repeated calls within a test/backfill run reuse it
instead of re-hitting the free API.
"""

from __future__ import annotations

import asyncio
import logging

import requests
import yfinance as yf

from core.cache import cached_call
from core.config import get_settings
from ingest.base import BaseIngestor
from signals.models import MaterialSignal

log = logging.getLogger(__name__)

# Free yfinance-tradable proxies per material (researched Sept 2026).
# Multiple tickers per material are averaged to reduce single-stock noise,
# same approach the project's existing live_scorer.py demo script uses.
PRICE_TICKERS: dict[str, list[str]] = {
    "Gallium": ["REMX", "MP"],  # VanEck Rare Earth ETF + MP Materials
    "Cobalt": ["GLNCY"],  # Glencore ADR (world's largest cobalt producer)
    "Lithium": ["LIT", "SQM", "ALB"],  # Global X Lithium ETF + SQM + Albemarle
    "Germanium": ["TECK", "FPLSF"],  # Teck Resources (byproduct producer) + 5N Plus ADR
    "Yttrium": ["REMX", "MP", "LYSCF"],  # + Lynas ADR (only non-China heavy-REE separator)
    "Dysprosium": ["REMX", "MP", "LYSCF"],
    "Indium": ["TECK"],  # weak proxy: Teck's stock is dominated by zinc/copper, not indium
    "Graphite": ["SYAAF", "NVNXF"],  # Syrah Resources ADR + Novonix ADR
}


def _fetch_price_delta_yfinance(material: str) -> float | None:
    """Trailing-2-week % price move, averaged across proxy tickers.
    Returns None (not 0.0) if every ticker failed, so callers can tell
    "no data" apart from "genuinely flat" and fall through to a fallback."""
    tickers = PRICE_TICKERS.get(material, [])
    deltas: list[float] = []
    for sym in tickers:
        try:
            hist = yf.Ticker(sym).history(period="2wk", auto_adjust=True)
            if hist.empty or len(hist) < 2:
                continue
            cur = float(hist["Close"].iloc[-1])
            prev = float(hist["Close"].iloc[0])
            if prev:
                deltas.append((cur - prev) / prev * 100)
        except Exception as exc:
            log.warning("yfinance %s (%s): %s", sym, material, exc)
    return round(sum(deltas) / len(deltas), 1) if deltas else None


def _fetch_price_delta_twelvedata(material: str) -> float | None:
    api_key = get_settings().twelvedata_api_key
    if not api_key:
        return None
    deltas: list[float] = []
    for sym in PRICE_TICKERS.get(material, []):
        try:
            resp = requests.get(
                "https://api.twelvedata.com/time_series",
                params={"symbol": sym, "interval": "1day", "outputsize": 10, "apikey": api_key},
                timeout=10,
            )
            data = resp.json()
            values = data.get("values")
            if not values or len(values) < 2:
                continue
            cur = float(values[0]["close"])  # most recent first
            prev = float(values[-1]["close"])
            if prev:
                deltas.append((cur - prev) / prev * 100)
        except Exception as exc:
            log.warning("Twelve Data %s (%s): %s", sym, material, exc)
    return round(sum(deltas) / len(deltas), 1) if deltas else None


def _fetch_price_delta_finnhub(material: str) -> float | None:
    """Last resort only: Finnhub's free /quote gives latest-day change, a
    narrower window than the trailing-2-week methodology used above -- an
    honest tradeoff for a final fallback, not a silent inconsistency."""
    api_key = get_settings().finnhub_api_key
    if not api_key:
        return None
    deltas: list[float] = []
    for sym in PRICE_TICKERS.get(material, []):
        try:
            resp = requests.get(
                "https://finnhub.io/api/v1/quote",
                params={"symbol": sym, "token": api_key},
                timeout=10,
            )
            data = resp.json()
            dp = data.get("dp")  # percent change, provided directly by Finnhub
            if dp is not None:
                deltas.append(float(dp))
        except Exception as exc:
            log.warning("Finnhub %s (%s): %s", sym, material, exc)
    return round(sum(deltas) / len(deltas), 1) if deltas else None


def _fetch_price_delta_sync(material: str) -> float:
    for fetch in (_fetch_price_delta_yfinance, _fetch_price_delta_twelvedata, _fetch_price_delta_finnhub):
        result = fetch(material)
        if result is not None:
            return result
    return 0.0


class USGSIngestor(BaseIngestor):
    source_name = "usgs"

    def __init__(self, material: str):
        self.material = material

    async def fetch(self) -> dict:
        try:
            delta_pct = await cached_call(
                f"price:{self.material}",
                lambda: asyncio.to_thread(_fetch_price_delta_sync, self.material),
            )
        except Exception as exc:
            log.warning("price fetch failed for %s: %s", self.material, exc)
            delta_pct = 0.0
        return {"price_delta": delta_pct}

    async def normalize(self, raw: dict) -> MaterialSignal:
        return MaterialSignal(material=self.material, source=self.source_name, price_delta=float(raw.get("price_delta", 0)))
