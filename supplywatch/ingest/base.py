from abc import ABC, abstractmethod

from signals.models import MaterialSignal


class SourceUnavailable(Exception):
    """fetch() raises this when a source returned no usable data (network
    error, every provider empty). It is not a reading of zero: a failed fetch
    must never be scored as "flat price" or "no news", so callers drop the
    source and skip the material for that run (signals.models.missing_sources)."""


class BaseIngestor(ABC):
    material: str
    source_name: str

    @abstractmethod
    async def fetch(self) -> dict:
        ...

    @abstractmethod
    async def normalize(self, raw: dict) -> MaterialSignal:
        ...

    async def run(self) -> MaterialSignal:
        raw = await self.fetch()
        return await self.normalize(raw)
