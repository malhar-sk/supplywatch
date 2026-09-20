"""Guest-mode isolation test (Chapter 4 non-negotiable): guest traffic must
never write to per-user tables, and the guest code path must not even be
able to reach the live scoring/per-user tables.

This is deliberately a hostile test, not a happy-path one: it asserts a
zero row-count delta on every per-user table (not just "the guest table
got a row"), and it inspects the guest modules' own source for any import
of a per-user model or the authenticated scoring pipeline.
"""

import ast
import asyncio
from pathlib import Path

from sqlalchemy import func, select

from core.database import AlertHistory, AlertSubscription, ApiKey, ApiUsageCounter, AsyncSessionLocal, Base, DisruptionScore, Material, RawSignal, engine
from snapshot.guest import run_guest_snapshot

PER_USER_TABLES = [Material, RawSignal, DisruptionScore, ApiKey, ApiUsageCounter, AlertSubscription, AlertHistory]

FORBIDDEN_NAMES = {
    "Material", "RawSignal", "DisruptionScore", "ApiKey", "ApiUsageCounter",
    "AlertSubscription", "AlertHistory", "require_api_key", "run_pipeline",
}


def _imported_names(module_path: Path) -> set[str]:
    tree = ast.parse(module_path.read_text())
    names = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            for alias in node.names:
                names.add(alias.asname or alias.name)
        elif isinstance(node, ast.Import):
            for alias in node.names:
                names.add(alias.asname or alias.name)
    return names


def test_guest_modules_do_not_import_per_user_models():
    root = Path(__file__).resolve().parents[1]
    for rel_path in ["snapshot/guest.py", "api/routes/guest.py"]:
        imported = _imported_names(root / rel_path)
        leaked = imported & FORBIDDEN_NAMES
        assert not leaked, f"{rel_path} imports per-user/live-scoring names it must never reach: {leaked}"


async def _count_rows(db, model) -> int:
    result = await db.execute(select(func.count()).select_from(model))
    return result.scalar_one()


def test_guest_snapshot_writes_zero_rows_to_any_per_user_table():
    async def _run():
        # See comment in test_snapshot_idempotency.py: dispose before use so
        # this test doesn't inherit a connection bound to a closed loop from
        # an earlier test file's asyncio.run().
        await engine.dispose()
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

        async with AsyncSessionLocal() as db:
            before = {model.__tablename__: await _count_rows(db, model) for model in PER_USER_TABLES}

        await run_guest_snapshot()  # the guest job under test

        async with AsyncSessionLocal() as db:
            after = {model.__tablename__: await _count_rows(db, model) for model in PER_USER_TABLES}

        deltas = {name: after[name] - before[name] for name in before}
        assert all(delta == 0 for delta in deltas.values()), f"guest snapshot changed per-user row counts: {deltas}"

    asyncio.run(_run())
