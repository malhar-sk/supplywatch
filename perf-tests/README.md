# SupplyWatch k6 Load Test

A single, focused k6 load/performance test against a real, running instance of
the SupplyWatch FastAPI service. This is not a full test suite — it is one
staged-load script that produces genuine, measured latency/throughput/error
numbers, run against a live local server.

## What it tests

`supplywatch-load-test.js` exercises a realistic mix of the service's real
endpoints on every virtual-user (VU) iteration:

| Endpoint | Auth | Notes |
|---|---|---|
| `GET /health` | none | Cheap liveness endpoint, no rate limiting. |
| `GET /materials` | `X-API-Key` header | Lists all tracked materials with their latest disruption score. |
| `GET /materials/1/signal` | `X-API-Key` header | Returns the latest scoring signal for material id 1. On a fresh dev DB with no scoring job having run, this legitimately returns `404 signal not found` — that is correct application behavior, not a failure, so the k6 check for this request accepts `200 or 404`. |

## Load profile

Defined via k6 `options.stages` in the script:

1. Ramp 0 -> 10 VUs over 10s
2. Hold at 10 VUs for 20s
3. Ramp 10 -> 50 VUs over 15s
4. Hold at 50 VUs for 20s
5. Ramp down to 0 over 5s

Total runtime: ~70s of stage time (plus a small tail as the last iterations
finish). This is a short demonstration load test against a single-instance
local dev server, not a capacity-planning benchmark.

Thresholds (`http_req_duration: p(95)<1000ms`, `http_req_failed: rate<0.05`)
are configured so k6's summary clearly flags pass/fail, but the goal of this
test is to report whatever the real numbers are — not to tune the script
until thresholds go green.

## Why the test key is tier `pro`, not `free`

`api/auth.py`'s `require_api_key` dependency enforces a daily request quota
(`DEFAULT_RATE_LIMIT_FREE`, default 100/day) but **only when the API key's
`tier` column equals the string `"free"`**:

```python
if api_key.tier == "free":
    ...
    if usage and usage.count >= get_settings().default_rate_limit_free:
        raise HTTPException(status_code=429, detail="Daily request limit reached")
```

Any other tier value skips that branch entirely — there is no allowlist of
"good" tiers, just a single `== "free"` check. A load test ramping to 50 VUs
will exceed 100 requests within the first few seconds, so using a default
(`free`-tier) key would mean nearly every request past the first ~100 comes
back `429 Too Many Requests`. That would swamp the results with a rate-limit
artifact instead of a real performance signal.

To avoid this, `setup()` in the script calls `POST /auth/keys` once, before
any VUs start, with `{"company_name": "k6 Load Test", "tier": "pro"}`, and
the resulting API key is what every VU uses for the rest of the run. This was
verified directly against the running server before writing the script (see
below) — `tier: "pro"` returns 200s from `/materials` with no 429s, while an
unauthenticated request correctly gets 401.

`GET /health` needs no API key and has no rate limiting at all, so it is
unaffected either way.

## Prerequisites

- The SupplyWatch API running and reachable (default assumed:
  `http://127.0.0.1:8020`). It needs a working Postgres connection per its
  `.env` / `DATABASE_URL`.
- k6 installed. This test was run using the portable Windows binary at
  `C:/Users/malha/career-ops/.tools/k6/k6.exe` (k6 v2.1.0), not a system-wide
  install.

## How to run

```
"C:/Users/malha/career-ops/.tools/k6/k6.exe" run C:/Users/malha/supplywatch/perf-tests/supplywatch-load-test.js
```

To target a different host/port, set `BASE_URL`:

```
"C:/Users/malha/career-ops/.tools/k6/k6.exe" run -e BASE_URL=http://127.0.0.1:8020 C:/Users/malha/supplywatch/perf-tests/supplywatch-load-test.js
```

To also dump raw per-request metrics as JSON (used to produce the measured
results below):

```
"C:/Users/malha/career-ops/.tools/k6/k6.exe" run --out json=results.json C:/Users/malha/supplywatch/perf-tests/supplywatch-load-test.js
```

## Results

See the top-level report / CV notes for the actual k6 end-of-run summary from
the real run against the live local server — total requests, requests/sec,
p50/p95/p99 latency (overall and per endpoint via the custom
`health_req_duration` / `materials_req_duration` / `signal_req_duration`
trends), error rate, and checks passed/failed. Only numbers that came out of
an actual k6 run are reported anywhere for this test — nothing here is
estimated.
