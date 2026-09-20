"""Export-restriction / disruption headline signal via the free Google News
RSS search endpoint — no API key required.

Any network failure falls back to 0 mentions rather than raising, so a
single request timeout or offline environment never breaks the pipeline
(and BaseIngestor.run() stays safe to call directly, e.g. from tests, even
without network access).

Paid/free alternatives (NewsAPI, Currents, Marketaux) were evaluated and
rejected: all are more request-limited than this free, unlimited RSS feed,
and NewsAPI's free tier explicitly bans this kind of production use. The
result is cached (core/cache.py) since the daily job only needs a fresh
count once a day.
"""

from __future__ import annotations

import asyncio
import logging
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime

import requests

from core.cache import cached_call
from ingest.base import BaseIngestor
from signals.models import MaterialSignal

log = logging.getLogger(__name__)


def _fetch_news_count_sync(material: str, days: int = 7) -> int:
    """Blocking Google News RSS call, run via asyncio.to_thread."""
    query = f"{material} export controls OR supply disruption OR sanctions OR price spike"
    url = f"https://news.google.com/rss/search?q={requests.utils.quote(query)}&hl=en-US&gl=US&ceid=US:en"
    cutoff = datetime.now(timezone.utc) - timedelta(days=days)
    count = 0
    try:
        r = requests.get(url, timeout=15, headers={"User-Agent": "SupplyWatch/1.0"})
        r.raise_for_status()
        root = ET.fromstring(r.content)
        for item in root.findall(".//item"):
            pub_raw = item.findtext("pubDate", "")
            try:
                pub_dt = parsedate_to_datetime(pub_raw)
                if pub_dt > cutoff:
                    count += 1
            except Exception:
                pass
    except Exception as exc:
        log.warning("Google News RSS error for %s: %s", material, exc)
    return count


class SanctionsIngestor(BaseIngestor):
    source_name = "sanctions"

    def __init__(self, material: str):
        self.material = material

    async def fetch(self) -> dict:
        try:
            count = await cached_call(
                f"news:{self.material}",
                lambda: asyncio.to_thread(_fetch_news_count_sync, self.material),
            )
        except Exception as exc:
            log.warning("news fetch failed for %s: %s", self.material, exc)
            count = 0
        return {"mentions": count}

    async def normalize(self, raw: dict) -> MaterialSignal:
        return MaterialSignal(material=self.material, source=self.source_name, export_mentions=int(raw.get("mentions", 0)))
