from dataclasses import dataclass, field


@dataclass
class MaterialSignal:
    material: str
    source: str
    price_delta: float = 0.0
    export_mentions: int = 0
    trade_hhi: float = 0.0
    metadata: dict = field(default_factory=dict)


# One record per source is needed for a complete reading. disruption_score()
# averages each factor over the records it receives, so a missing record
# changes the denominators and inflates the other factors, and a failed fetch
# recorded as 0 would read as "no risk". Callers therefore skip a material
# for that run when any source is missing, instead of scoring a partial set.
EXPECTED_SOURCES = ("usgs", "comtrade", "sanctions")


def missing_sources(signals: list[MaterialSignal]) -> list[str]:
    got = {s.source for s in signals}
    return [src for src in EXPECTED_SOURCES if src not in got]
