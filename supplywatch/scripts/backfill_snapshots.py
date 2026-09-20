"""Backfill utility: seed the last N days of daily_snapshots and
guest_demo_snapshots so the delta/trend module and dashboard have real
history to show before enough real daily-job runs have accumulated.

This calls the exact same run_daily_snapshot() / run_guest_snapshot()
functions the real scheduled job uses — it does not fabricate scores by
any separate path. It only supplies a different snapshot_date per call, so
each day's row is a genuine output of the real pipeline for that date,
not a hand-typed number.

Usage:
    python scripts/backfill_snapshots.py [--days 7]
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from datetime import date, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import select

from core.database import AsyncSessionLocal, Base, Material, engine
from snapshot.guest import run_guest_snapshot
from snapshot.jobs import run_daily_snapshot

SEED_MATERIALS = [
    ("Gallium", "Ga", "Critical Metal", ["China", "Germany"]),
    ("Germanium", "Ge", "Critical Metal", ["China", "Canada"]),
    ("Cobalt", "Co", "Battery Metal", ["DRC", "Indonesia"]),
    ("Lithium", "Li", "Battery Metal", ["Australia", "Chile"]),
    ("Yttrium", "Y", "Rare Earth", ["China", "Myanmar"]),
    ("Dysprosium", "Dy", "Rare Earth", ["China", "Australia"]),
    ("Indium", "In", "Critical Metal", ["China", "South Korea"]),
    ("Graphite", "C", "Battery Material", ["China", "Mozambique"]),
]


async def ensure_materials_seeded() -> None:
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    async with AsyncSessionLocal() as db:
        for name, symbol, category, producers in SEED_MATERIALS:
            exists = (await db.execute(select(Material).where(Material.name == name))).scalar_one_or_none()
            if not exists:
                db.add(Material(name=name, symbol=symbol, category=category, primary_producers=producers))
        await db.commit()


async def backfill(days: int) -> None:
    await ensure_materials_seeded()
    start = date.today() - timedelta(days=days - 1)
    for offset in range(days):
        snapshot_date = start + timedelta(days=offset)
        real_results = await run_daily_snapshot(snapshot_date=snapshot_date)
        guest_results = await run_guest_snapshot(snapshot_date=snapshot_date)
        print(f"{snapshot_date}: {len(real_results)} materials, {len(guest_results)} guest materials")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--days", type=int, default=7)
    args = parser.parse_args()
    asyncio.run(backfill(args.days))
