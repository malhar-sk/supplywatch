"""Minimal in-process TTL cache for free-API responses.

Deliberately not Redis or any external service: the daily snapshot job is
meant to run ~once/day, so real call volume is already small. The actual
problem this solves is redundant calls during testing, backfills, and
manual reruns within the same process/day -- a plain dict with timestamps
is the whole fix, with zero new infrastructure or moving parts.

Scope: process-local only. It does not persist across restarts and is not
shared between processes -- that's a deliberate simplicity tradeoff, not
an oversight, given the actual call volume this needs to absorb.
"""

from __future__ import annotations

import time
from typing import Any, Callable, Coroutine, TypeVar

T = TypeVar("T")

_store: dict[str, tuple[float, Any]] = {}

DEFAULT_TTL_SECONDS = 6 * 60 * 60  # 6 hours: shorter than a day so a genuinely
                                    # new signal during the day isn't hidden
                                    # for a full 24h, but long enough to absorb
                                    # repeated calls within one test/backfill run


def get(key: str) -> Any | None:
    entry = _store.get(key)
    if entry is None:
        return None
    expires_at, value = entry
    if time.monotonic() >= expires_at:
        _store.pop(key, None)
        return None
    return value


def set(key: str, value: Any, ttl_seconds: float = DEFAULT_TTL_SECONDS) -> None:
    _store[key] = (time.monotonic() + ttl_seconds, value)


def clear() -> None:
    """Test-only escape hatch -- production code never needs this."""
    _store.clear()


async def cached_call(key: str, fn: Callable[[], Coroutine[Any, Any, T]], ttl_seconds: float = DEFAULT_TTL_SECONDS) -> T:
    """Await `fn()` and cache the result under `key`, or return the cached
    value if still fresh. `fn` is only called on a miss."""
    cached = get(key)
    if cached is not None:
        return cached
    value = await fn()
    set(key, value, ttl_seconds)
    return value
