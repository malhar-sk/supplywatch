import asyncio

from ingest.base import SourceUnavailable
from ingest.comtrade import ComtradeIngestor
from ingest.sanctions import SanctionsIngestor
from ingest.usgs import USGSIngestor


def test_ingestors_return_signal():
    async def _run():
        for cls in (USGSIngestor, ComtradeIngestor, SanctionsIngestor):
            ingestor = cls('Cobalt')
            try:
                signal = await ingestor.run()
            except SourceUnavailable:
                # Offline or rate-limited: a failed fetch raises instead of
                # returning a fake zero (see tests/test_failed_fetch.py).
                continue
            assert signal.material == 'Cobalt'
            assert signal.source
    asyncio.run(_run())
