"""Daily snapshot job.

Additive module: calls the existing, unmodified disruption_score() via the
existing, unmodified BaseIngestor subclasses, and stores one row per
material per day. Does not modify ingestion, scoring, or the existing
threshold-alert / weekly-digest pipeline in scheduler/jobs.py.

Idempotency: the write is an upsert keyed on (material_id, snapshot_date).
Re-running this job for a date that already has a row updates that row in
place rather than inserting a duplicate. If a rerun computes a materially
different score for the same date, that is logged explicitly rather than
silently overwritten, since a same-day score change on retry is a signal
worth seeing, not noise to suppress.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import date

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from core.database import AsyncSessionLocal, DailySnapshot, Material
from ingest.comtrade import ComtradeIngestor
from ingest.sanctions import SanctionsIngestor
from ingest.usgs import USGSIngestor
from signals.models import MaterialSignal
from signals.scorer import DisruptionScorer

log = logging.getLogger(__name__)

SCORE_CHANGE_LOG_THRESHOLD = 0  # log any change; kept as a constant so a future
                                 # increment can widen the threshold deliberately


def summarize(material_name: str, score: int, factors: dict) -> str:
    """Pure function: turn a score + factor breakdown into one plain-English line."""
    dominant = max(factors, key=factors.get) if factors else None
    label = {
        "price": "price movement",
        "export": "export-restriction signals",
        "trade": "trade concentration",
    }.get(dominant, "mixed signals")
    if score >= 70:
        band = "elevated disruption risk"
    elif score >= 40:
        band = "moderate disruption risk"
    else:
        band = "low disruption risk"
    return f"{material_name}: {band} (score {score}/100), driven mainly by {label}."


async def _run_one_ingestor(cls, material_name: str) -> MaterialSignal | None:
    ingestor = cls(material_name)
    try:
        raw = await ingestor.fetch()
        return await ingestor.normalize(raw)
    except Exception as exc:  # an ingestor failing must not block the others
        log.warning("snapshot: %s failed for %s: %s", ingestor.source_name, material_name, exc)
        return None


async def _collect_signals(material_name: str) -> list[MaterialSignal]:
    """All three sources for one material, fetched concurrently (each already
    has its own try/except, so one slow/failed source can't block the others
    or this material's neighbors)."""
    results = await asyncio.gather(
        *(_run_one_ingestor(cls, material_name) for cls in (USGSIngestor, ComtradeIngestor, SanctionsIngestor))
    )
    return [signal for signal in results if signal is not None]


async def run_daily_snapshot(db: AsyncSession | None = None, snapshot_date: date | None = None) -> list[dict]:
    """Run the daily snapshot for every material and upsert the result.

    Returns a list of {material, score, rerun_score_changed} dicts so
    callers (tests, scripts) can inspect what happened without re-querying.
    """
    owns_session = db is None
    if owns_session:
        async with AsyncSessionLocal() as owned_db:
            return await run_daily_snapshot(owned_db, snapshot_date)

    snapshot_date = snapshot_date or date.today()
    materials = (await db.execute(select(Material))).scalars().all()
    results = []

    # Network-bound phase: fetch every material's signals concurrently. This
    # touches no DB state (the shared AsyncSession isn't safe for concurrent
    # queries), so it's safe to parallelize independently of the write phase
    # below. This is what turns ~24 sequential ingestor calls into one
    # concurrent batch.
    all_signals = await asyncio.gather(*(_collect_signals(m.name) for m in materials))

    for material, collected in zip(materials, all_signals):
        score, factors = DisruptionScorer.score(collected)
        summary = summarize(material.name, score, factors)

        existing = (
            await db.execute(
                select(DailySnapshot).where(
                    DailySnapshot.material_id == material.id,
                    DailySnapshot.snapshot_date == snapshot_date,
                )
            )
        ).scalar_one_or_none()

        rerun_score_changed = existing is not None and existing.score != score
        if rerun_score_changed:
            log.warning(
                "snapshot rerun for %s on %s: score changed %s -> %s on retry",
                material.name, snapshot_date, existing.score, score,
            )

        stmt = pg_insert(DailySnapshot).values(
            material_id=material.id,
            snapshot_date=snapshot_date,
            score=score,
            factors=factors,
            summary=summary,
        )
        stmt = stmt.on_conflict_do_update(
            constraint="uq_daily_snapshot_material_date",
            set_={
                "score": stmt.excluded.score,
                "factors": stmt.excluded.factors,
                "summary": stmt.excluded.summary,
                "updated_at": stmt.excluded.updated_at,
            },
        )
        await db.execute(stmt)
        results.append({"material": material.name, "score": score, "rerun_score_changed": rerun_score_changed})

    await db.commit()
    return results
