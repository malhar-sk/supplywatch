"""Guest-mode module (Chapter 4.1 / 5.1): a free, unauthenticated daily
brief for a fixed demo material set.

Isolation is structural, not just a convention:
  - GuestDemoSnapshot is keyed by material_name (a plain string), not a
    Material foreign key, so there is no column-level join path from this
    table into the authenticated-user schema.
  - This module never imports api.auth, ApiKey, AlertSubscription, or any
    per-user table, and never touches DisruptionScore or the live
    materials table.
  - run_guest_snapshot() and get_guest_brief() are the only two entry
    points; neither writes to nor reads from any per-user table.
"""

from __future__ import annotations

import asyncio
from datetime import date, timedelta

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from core.database import AsyncSessionLocal, GuestDemoSnapshot
from signals.scorer import DisruptionScorer
from snapshot.delta import compute_trend
from snapshot.jobs import _collect_signals, summarize

# Fixed demo set: guest traffic only ever sees these materials, never a
# real user's tracked list.
GUEST_DEMO_MATERIALS = ["Cobalt", "Lithium", "Gallium"]


async def run_guest_snapshot(db: AsyncSession | None = None, snapshot_date: date | None = None) -> list[dict]:
    owns_session = db is None
    if owns_session:
        async with AsyncSessionLocal() as owned_db:
            return await run_guest_snapshot(owned_db, snapshot_date)

    snapshot_date = snapshot_date or date.today()
    results = []

    # Same concurrent-fetch, sequential-write split as snapshot/jobs.py:
    # network I/O for all demo materials runs at once, DB writes stay
    # sequential on the shared AsyncSession. Reusing _collect_signals also
    # gives guest mode the same per-source failure isolation as the
    # authenticated pipeline (a single source failing no longer aborts the
    # whole guest snapshot).
    all_signals = await asyncio.gather(*(_collect_signals(name) for name in GUEST_DEMO_MATERIALS))

    for material_name, collected in zip(GUEST_DEMO_MATERIALS, all_signals):
        score, factors = DisruptionScorer.score(collected)
        summary = summarize(material_name, score, factors)

        cutoff = snapshot_date - timedelta(days=7)
        prior_scores = (
            await db.execute(
                select(GuestDemoSnapshot.score)
                .where(
                    GuestDemoSnapshot.material_name == material_name,
                    GuestDemoSnapshot.snapshot_date >= cutoff,
                    GuestDemoSnapshot.snapshot_date < snapshot_date,
                )
                .order_by(GuestDemoSnapshot.snapshot_date.asc())
            )
        ).scalars().all()
        trend = compute_trend([*prior_scores, score])

        stmt = pg_insert(GuestDemoSnapshot).values(
            material_name=material_name,
            snapshot_date=snapshot_date,
            score=score,
            trend=trend,
            summary=summary,
        )
        stmt = stmt.on_conflict_do_update(
            constraint="uq_guest_snapshot_material_date",
            set_={"score": stmt.excluded.score, "trend": stmt.excluded.trend, "summary": stmt.excluded.summary},
        )
        await db.execute(stmt)
        results.append({"material": material_name, "score": score, "trend": trend})

    await db.commit()
    return results


async def get_guest_brief(db: AsyncSession, days: int = 7) -> list[dict]:
    """Read-only guest brief. Reads GuestDemoSnapshot only."""
    cutoff = date.today() - timedelta(days=days)
    brief = []
    for material_name in GUEST_DEMO_MATERIALS:
        rows = (
            await db.execute(
                select(GuestDemoSnapshot)
                .where(GuestDemoSnapshot.material_name == material_name, GuestDemoSnapshot.snapshot_date >= cutoff)
                .order_by(GuestDemoSnapshot.snapshot_date.asc())
            )
        ).scalars().all()
        if not rows:
            continue
        latest = rows[-1]
        brief.append(
            {
                "material": material_name,
                "score": latest.score,
                "trend": latest.trend,
                "summary": latest.summary,
                "history": [r.score for r in rows],
                "dates": [r.snapshot_date.isoformat() for r in rows],
            }
        )
    return brief
