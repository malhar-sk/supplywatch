"""A failed fetch must never be recorded as a reading of zero.

Before this fix the price ingestor fell back to 0.0 and the news ingestor to
0 mentions, so an outage looked like "flat price" / "no news" (and was cached
for six hours). Now a failed fetch raises SourceUnavailable, the source is
dropped, and any material with a source missing is skipped for that run:
no snapshot row, no score, no alert, and an existing row is left untouched.

Everything here is offline and database-free: the jobs run against a fake
session that records which statements they execute.
"""

import asyncio
from datetime import date
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest
from sqlalchemy.dialects import postgresql

from core import cache
from core.database import DisruptionScore, RawSignal
from ingest.base import SourceUnavailable
from ingest.comtrade import ComtradeIngestor
from ingest.sanctions import SanctionsIngestor
from ingest.usgs import USGSIngestor
from signals.models import EXPECTED_SOURCES, MaterialSignal, missing_sources
from snapshot.guest import GUEST_DEMO_MATERIALS, run_guest_snapshot
from snapshot.jobs import run_daily_snapshot

FAILING = "Cobalt"  # the material whose news source "fails" in the job-level tests


def _signals(material: str, sources=EXPECTED_SOURCES) -> list[MaterialSignal]:
    by_source = {
        "usgs": MaterialSignal(material=material, source="usgs", price_delta=10.0),
        "sanctions": MaterialSignal(material=material, source="sanctions", export_mentions=2),
        "comtrade": MaterialSignal(material=material, source="comtrade", trade_hhi=5000.0),
    }
    return [by_source[s] for s in sources]


async def _collect_with_one_source_down(name: str) -> list[MaterialSignal]:
    return _signals(name, ("usgs", "comtrade") if name == FAILING else EXPECTED_SOURCES)


# --- helper -----------------------------------------------------------------

def test_expected_sources_match_the_real_ingestors():
    assert set(EXPECTED_SOURCES) == {c.source_name for c in (USGSIngestor, ComtradeIngestor, SanctionsIngestor)}


def test_missing_sources_reports_exactly_what_is_absent():
    assert missing_sources(_signals("Cobalt")) == []
    assert missing_sources(_signals("Cobalt", ("usgs", "comtrade"))) == ["sanctions"]
    assert missing_sources([]) == list(EXPECTED_SOURCES)


# --- ingestors --------------------------------------------------------------

def test_price_fetch_raises_instead_of_returning_zero():
    cache.clear()
    with patch("ingest.usgs._fetch_price_delta_yfinance", return_value=None), \
         patch("ingest.usgs._fetch_price_delta_twelvedata", return_value=None), \
         patch("ingest.usgs._fetch_price_delta_finnhub", return_value=None):
        with pytest.raises(SourceUnavailable):
            asyncio.run(USGSIngestor("Indium").fetch())


def test_a_failed_price_fetch_is_not_cached():
    cache.clear()
    with patch("ingest.usgs._fetch_price_delta_yfinance", return_value=None), \
         patch("ingest.usgs._fetch_price_delta_twelvedata", return_value=None), \
         patch("ingest.usgs._fetch_price_delta_finnhub", return_value=None):
        with pytest.raises(SourceUnavailable):
            asyncio.run(USGSIngestor("Indium").fetch())
    # The provider recovers: the next call must get the real value, not a cached failure.
    with patch("ingest.usgs._fetch_price_delta_yfinance", return_value=2.5):
        assert asyncio.run(USGSIngestor("Indium").fetch()) == {"price_delta": 2.5}
    cache.clear()


def test_a_genuine_zero_price_change_is_still_a_valid_reading():
    cache.clear()
    with patch("ingest.usgs._fetch_price_delta_yfinance", return_value=0.0):
        assert asyncio.run(USGSIngestor("Cobalt").fetch()) == {"price_delta": 0.0}
    cache.clear()


def test_news_fetch_raises_when_the_feed_is_unreachable():
    cache.clear()
    with patch("ingest.sanctions.requests.get", side_effect=ConnectionError("offline")):
        with pytest.raises(SourceUnavailable):
            asyncio.run(SanctionsIngestor("Cobalt").fetch())
    cache.clear()


def test_a_feed_with_no_recent_items_is_a_real_count_of_zero():
    cache.clear()
    response = MagicMock()
    response.content = b"<rss><channel></channel></rss>"
    with patch("ingest.sanctions.requests.get", return_value=response):
        assert asyncio.run(SanctionsIngestor("Cobalt").fetch()) == {"mentions": 0}
    cache.clear()


# --- jobs, against a fake session -------------------------------------------

class _Rows:
    def __init__(self, items):
        self._items = items

    def scalars(self):
        return self

    def all(self):
        return self._items

    def scalar_one_or_none(self):
        return self._items[0] if self._items else None


class _FakeDB:
    """Records which statements a job runs. Material and prior-score lookups
    return the given rows; everything else (existing-row lookup) finds nothing."""

    def __init__(self, materials=()):
        self._materials = list(materials)
        self.added = []  # ORM objects passed to add() (legacy pipeline)
        self.selects = []  # statements that read a snapshot table
        self.inserts = []  # parameters of each insert/upsert
        self.committed = False
        self._first = True

    async def execute(self, stmt):
        compiled = stmt.compile(dialect=postgresql.dialect())
        sql = str(compiled)
        if sql.lstrip().upper().startswith("INSERT"):
            self.inserts.append(compiled.params)
            return _Rows([])
        if self._first and self._materials:
            self._first = False
            return _Rows(self._materials)
        self.selects.append(sql)
        return _Rows([])

    def add(self, obj):
        self.added.append(obj)

    async def commit(self):
        self.committed = True


def test_snapshot_job_skips_a_material_with_a_failed_source():
    db = _FakeDB([SimpleNamespace(id=1, name="Cobalt"), SimpleNamespace(id=2, name="Lithium")])
    with patch("snapshot.jobs._collect_signals", new=_collect_with_one_source_down):
        results = asyncio.run(run_daily_snapshot(db, snapshot_date=date(2098, 3, 1)))

    by_name = {r["material"]: r for r in results}
    assert by_name["Cobalt"]["skipped"] is True
    assert by_name["Cobalt"]["missing_sources"] == ["sanctions"]
    assert by_name["Cobalt"]["score"] is None
    assert by_name["Lithium"].get("skipped") is None and by_name["Lithium"]["score"] > 0

    # Cobalt: no lookup and no write at all, so an existing row cannot be overwritten
    # with a zero-scored one. Lithium: exactly one upsert.
    assert [p["material_id"] for p in db.inserts] == [2]
    assert len(db.selects) == 1
    assert db.committed


def test_guest_job_skips_a_material_with_a_failed_source():
    db = _FakeDB()
    with patch("snapshot.guest._collect_signals", new=_collect_with_one_source_down):
        results = asyncio.run(run_guest_snapshot(db, snapshot_date=date(2098, 3, 3)))

    assert [r["material"] for r in results if r.get("skipped")] == [FAILING]
    written = sorted(p["material_name"] for p in db.inserts)
    assert written == sorted(set(GUEST_DEMO_MATERIALS) - {FAILING})


def test_pipeline_skips_score_and_alerts_for_a_material_with_a_failed_source():
    from scheduler import jobs

    async def fake_fetch(name):
        sources = ("usgs", "comtrade") if name == "Cobalt" else EXPECTED_SOURCES
        return [(s, {}, sig) for s, sig in zip(sources, _signals(name, sources))]

    db = _FakeDB([SimpleNamespace(id=1, name="Cobalt"), SimpleNamespace(id=2, name="Lithium")])
    with patch.object(jobs, "_fetch_material_raw", new=fake_fetch), patch.object(jobs, "AlertDispatcher"):
        asyncio.run(jobs.run_pipeline(db))

    scored = [o.material_id for o in db.added if isinstance(o, DisruptionScore)]
    raw = [o.material_id for o in db.added if isinstance(o, RawSignal)]
    assert scored == [2], "only Lithium (all sources up) may get a score"
    assert sorted(raw) == [1, 1, 2, 2, 2], "raw rows that did arrive are still kept"
