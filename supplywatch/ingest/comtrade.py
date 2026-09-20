"""Trade/production-concentration signal.

Real trade-flow data at material-level granularity isn't available as a
free, live API (UN Comtrade's material-level detail requires a paid or
rate-limited registered tier), and concentration itself doesn't move
day-to-day — USGS only republishes it annually in its Mineral Commodity
Summaries. So this is a static reference table rather than a live fetch,
which mirrors how the industry actually treats this figure.

Values researched Sept 2026 from USGS Mineral Commodity Summaries
2025/2026, cross-checked against commercial metals trackers. Germanium,
Yttrium, and Dysprosium saw new Chinese export-licensing regimes take
effect in 2025-26 that materially raised effective concentration risk
within the year — treat those three as directional estimates, not precise
figures, and revisit if USGS publishes an updated MCS edition.
"""

from __future__ import annotations

from ingest.base import BaseIngestor
from signals.models import MaterialSignal

# Trade/production concentration (HHI-style, 0-10000; higher = more
# concentrated in a single country = higher structural disruption risk).
TRADE_HHI: dict[str, float] = {
    "Gallium": 8500,  # China >85% of mine production
    "Cobalt": 4900,  # DRC ~73% of mine production
    "Lithium": 2500,  # Australia ~47% / Chile ~27% of mine production
    "Germanium": 7500,  # China ~77% of refined production
    "Yttrium": 9000,  # China ~90-99% of refining capacity
    "Dysprosium": 8500,  # China ~85-90% of mine production
    "Indium": 5500,  # China ~70% of refinery production (2025)
    "Graphite": 5000,  # China ~65-78% of natural flake graphite production
}


class ComtradeIngestor(BaseIngestor):
    source_name = "comtrade"

    def __init__(self, material: str):
        self.material = material

    async def fetch(self) -> dict:
        return {"trade_hhi": TRADE_HHI.get(self.material, 3000)}  # neutral default if unmapped

    async def normalize(self, raw: dict) -> MaterialSignal:
        return MaterialSignal(material=self.material, source=self.source_name, trade_hhi=float(raw.get("trade_hhi", 0)))
