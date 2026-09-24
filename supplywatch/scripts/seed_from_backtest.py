"""Reseed daily_snapshots / guest_demo_snapshots from the real historical
backtest (snapshot/backtest.py) instead of scripts/backfill_snapshots.py.

Why this exists: backfill_snapshots.py calls the LIVE ingestors once per
"day" it backfills, stamping today's real-time price/news signal with a
past snapshot_date -- it never simulates a different day's real value (no
free API supports that). Combined with the in-process TTL cache, repeated
runs within one process return byte-identical signals, so every backfilled
day ends up with the same score: flat sparklines, "Unchanged" trend
everywhere. That's an artifact of the seeding method, not the live
pipeline (which does vary day to day once it actually runs across real
calendar days).

This script instead reuses run_backtest() -- already real, already
validated, already the source of the report's Chapter 6 backtest chart --
which computes disruption_score() from genuine historical yfinance prices
and the documented policy-event timeline at weekly checkpoints. That gives
a real, honestly-varying history without fabricating anything new.

Deletes existing rows for the materials it reseeds first, so there's no
stale flat data left sitting alongside the real backtest history.

Usage:
    python scripts/seed_from_backtest.py
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import delete, select
from sqlalchemy.dialects.postgresql import insert as pg_insert

from core.database import AsyncSessionLocal, DailySnapshot, GuestDemoSnapshot, Material
from snapshot.backtest import run_backtest
from snapshot.delta import compute_trend
from snapshot.guest import GUEST_DEMO_MATERIALS
from snapshot.jobs import summarize


async def main() -> None:
    async with AsyncSessionLocal() as db:
        materials = (await db.execute(select(Material))).scalars().all()
        name_to_id = {m.name: m.id for m in materials}
        material_names = list(name_to_id)

        print(f"Running real backtest for {len(material_names)} materials...")
        results = run_backtest(material_names, checkpoint_days=7)
        print(f"Got {len(results)} real weekly checkpoints.")

        await db.execute(delete(DailySnapshot).where(DailySnapshot.material_id.in_(name_to_id.values())))
        await db.execute(delete(GuestDemoSnapshot).where(GuestDemoSnapshot.material_name.in_(GUEST_DEMO_MATERIALS)))
        await db.commit()

        guest_history: dict[str, list[int]] = {name: [] for name in GUEST_DEMO_MATERIALS}

        for row in results:
            material, snap_date, score, factors = row["material"], row["date"], row["score"], row["factors"]
            summary = summarize(material, score, factors)

            stmt = pg_insert(DailySnapshot).values(
                material_id=name_to_id[material], snapshot_date=snap_date,
                score=score, factors=factors, summary=summary,
            )
            stmt = stmt.on_conflict_do_update(
                constraint="uq_daily_snapshot_material_date",
                set_={"score": stmt.excluded.score, "factors": stmt.excluded.factors, "summary": stmt.excluded.summary},
            )
            await db.execute(stmt)

            if material in guest_history:
                guest_history[material].append(score)
                trend = compute_trend(guest_history[material])
                g_stmt = pg_insert(GuestDemoSnapshot).values(
                    material_name=material, snapshot_date=snap_date,
                    score=score, trend=trend, summary=summary,
                )
                g_stmt = g_stmt.on_conflict_do_update(
                    constraint="uq_guest_snapshot_material_date",
                    set_={"score": g_stmt.excluded.score, "trend": g_stmt.excluded.trend, "summary": g_stmt.excluded.summary},
                )
                await db.execute(g_stmt)

        await db.commit()
        print("Reseeded daily_snapshots and guest_demo_snapshots from the real backtest.")


if __name__ == "__main__":
    asyncio.run(main())
