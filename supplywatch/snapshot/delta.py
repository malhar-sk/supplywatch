"""Delta / trend module (Chapter 5.3.3).

Pure comparison logic over the daily_snapshots history: today's score
against the most recent prior snapshot, plus a short rolling history for
the dashboard sparkline. Does not modify disruption_score() or the
snapshot job; reads DailySnapshot rows only.
"""

from __future__ import annotations

from datetime import date, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from core.database import DailySnapshot

TREND_RISING = "rising"
TREND_FALLING = "falling"
TREND_UNCHANGED = "unchanged"


def compute_trend(scores: list[int]) -> str:
    """Compare the two most recent scores in an oldest-to-newest sequence.

    Matches Chapter 5.3.3: "the current day's score is compared against
    the most recent prior snapshot." Fewer than two points is unchanged
    by definition — there is nothing yet to compare against.
    """
    if len(scores) < 2:
        return TREND_UNCHANGED
    latest, prior = scores[-1], scores[-2]
    if latest > prior:
        return TREND_RISING
    if latest < prior:
        return TREND_FALLING
    return TREND_UNCHANGED


async def get_history(db: AsyncSession, material_id: int, days: int = 7) -> list[DailySnapshot]:
    cutoff = date.today() - timedelta(days=days)
    rows = (
        await db.execute(
            select(DailySnapshot)
            .where(DailySnapshot.material_id == material_id, DailySnapshot.snapshot_date >= cutoff)
            .order_by(DailySnapshot.snapshot_date.asc())
        )
    ).scalars().all()
    return list(rows)


async def get_daily_brief(db: AsyncSession, material_id: int, days: int = 7) -> dict:
    """Assemble the daily-brief payload: trend + short sparkline history."""
    history = await get_history(db, material_id, days)
    scores = [row.score for row in history]
    return {
        "material_id": material_id,
        "dates": [row.snapshot_date.isoformat() for row in history],
        "scores": scores,
        "trend": compute_trend(scores),
        "latest_score": scores[-1] if scores else None,
        "latest_summary": history[-1].summary if history else None,
    }
