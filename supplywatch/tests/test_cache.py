"""Cache correctness (Part 1, Pareto item #3): a cached call must not
re-invoke its function while fresh, and must expire correctly."""

import asyncio

from core.cache import cached_call, clear, get, set


def test_cached_call_only_invokes_function_once_while_fresh():
    clear()
    calls = {"count": 0}

    async def _fn():
        calls["count"] += 1
        return "value"

    async def _run():
        first = await cached_call("k", _fn, ttl_seconds=60)
        second = await cached_call("k", _fn, ttl_seconds=60)
        return first, second

    first, second = asyncio.run(_run())
    assert first == second == "value"
    assert calls["count"] == 1


def test_cached_call_reinvokes_after_expiry():
    clear()
    calls = {"count": 0}

    async def _fn():
        calls["count"] += 1
        return calls["count"]

    async def _run():
        first = await cached_call("k2", _fn, ttl_seconds=0)  # expires immediately
        second = await cached_call("k2", _fn, ttl_seconds=0)
        return first, second

    first, second = asyncio.run(_run())
    assert first == 1
    assert second == 2  # re-invoked, not served stale


def test_different_keys_do_not_collide():
    clear()
    set("a", "value-a")
    set("b", "value-b")
    assert get("a") == "value-a"
    assert get("b") == "value-b"
