"""Idempotency test for the daily snapshot job (Chapter 5.3.2 / Chapter 3.2 contract):

running the job twice for the same date must not create duplicate rows.
"""

import asyncio
from datetime import date

from sqlalchemy import delete, select

from core.database import AsyncSessionLocal, Base, DailySnapshot, Material, engine
from snapshot.jobs import run_daily_snapshot

TEST_MATERIAL = ("Cobalt", "Co", "Battery Metal", ["DRC", "Indonesia"])


async def _ensure_schema_and_material() -> int:
    # Each asyncio.run() call in this process gets its own event loop, but
    # `engine` is a module-level singleton whose pooled connections are
    # bound to whichever loop created them. Disposing first forces fresh
    # connections bound to *this* loop instead of reusing stale ones from
    # a previous test file's now-closed loop.
    await engine.dispose()
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    async with AsyncSessionLocal() as db:
        name, symbol, category, producers = TEST_MATERIAL
        existing = (await db.execute(select(Material).where(Material.name == name))).scalar_one_or_none()
        if existing:
            return existing.id
        m = Material(name=name, symbol=symbol, category=category, primary_producers=producers)
        db.add(m)
        await db.commit()
        await db.refresh(m)
        return m.id


def test_snapshot_job_is_idempotent():
    async def _run():
        material_id = await _ensure_schema_and_material()
        snapshot_date = date(2099, 1, 1)  # fixed, far-future date so this test never collides with a real run

        # run_daily_snapshot() processes every material in the table, not
        # just the one this test cares about — so cleanup must target the
        # whole (fictional) test date, not just this test's material_id,
        # or it leaks stray rows for every other material into real data.
        async def _clean():
            async with AsyncSessionLocal() as db:
                await db.execute(delete(DailySnapshot).where(DailySnapshot.snapshot_date == snapshot_date))
                await db.commit()

        await _clean()
        await run_daily_snapshot(snapshot_date=snapshot_date)
        await run_daily_snapshot(snapshot_date=snapshot_date)  # rerun for the same date

        async with AsyncSessionLocal() as db:
            rows = (
                await db.execute(
                    select(DailySnapshot).where(
                        DailySnapshot.material_id == material_id, DailySnapshot.snapshot_date == snapshot_date
                    )
                )
            ).scalars().all()

        try:
            assert len(rows) == 1, f"expected exactly 1 row after two runs, got {len(rows)}"
        finally:
            await _clean()

    asyncio.run(_run())
