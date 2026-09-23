import http from 'k6/http';
import { check, group, sleep } from 'k6';
import { Rate, Trend } from 'k6/metrics';

// ---------------------------------------------------------------------------
// SupplyWatch load test
//
// Targets a real, locally-running instance of the SupplyWatch FastAPI service.
// See perf-tests/README.md for full context, including why setup() creates a
// "pro" tier API key instead of a default "free" tier key.
// ---------------------------------------------------------------------------

const BASE_URL = __ENV.BASE_URL || 'http://127.0.0.1:8020';

// Per-endpoint latency trends so the end-of-run summary breaks out timing
// for each route individually, not just as one blended number.
const healthDuration = new Trend('health_req_duration');
const materialsDuration = new Trend('materials_req_duration');
const signalDuration = new Trend('signal_req_duration');
const errorRate = new Rate('errors');

export const options = {
  stages: [
    { duration: '10s', target: 10 },  // ramp 0 -> 10 VUs
    { duration: '20s', target: 10 },  // hold at 10 VUs
    { duration: '15s', target: 50 },  // ramp 10 -> 50 VUs
    { duration: '20s', target: 50 },  // hold at 50 VUs
    { duration: '5s', target: 0 },    // ramp down to 0
  ],
  thresholds: {
    http_req_duration: ['p(95)<1000'],
    http_req_failed: ['rate<0.05'],
  },
};

// setup() runs once, before any VUs start iterating. It provisions a real
// API key against the live server via POST /auth/keys, using tier "pro" so
// that the free-tier daily rate limiter (100 req/day, see api/auth.py) never
// kicks in and corrupts the load test's error-rate numbers with 429s.
export function setup() {
  const res = http.post(
    `${BASE_URL}/auth/keys`,
    JSON.stringify({ company_name: 'k6 Load Test', tier: 'pro' }),
    { headers: { 'Content-Type': 'application/json' } }
  );

  const ok = check(res, {
    'setup: /auth/keys returned 200': (r) => r.status === 200,
    'setup: response has api_key': (r) => {
      try {
        return !!JSON.parse(r.body).data.api_key;
      } catch (e) {
        return false;
      }
    },
  });

  if (!ok) {
    throw new Error(
      `setup() failed to obtain API key from ${BASE_URL}/auth/keys - status=${res.status} body=${res.body}`
    );
  }

  const apiKey = JSON.parse(res.body).data.api_key;
  return { apiKey };
}

export default function (data) {
  const authHeaders = { headers: { 'X-API-Key': data.apiKey } };

  group('GET /health (no auth)', () => {
    const res = http.get(`${BASE_URL}/health`);
    healthDuration.add(res.timings.duration);
    const passed = check(res, {
      'health: status is 200': (r) => r.status === 200,
    });
    errorRate.add(!passed);
  });

  group('GET /materials (authenticated)', () => {
    const res = http.get(`${BASE_URL}/materials`, authHeaders);
    materialsDuration.add(res.timings.duration);
    const passed = check(res, {
      'materials: status is 200': (r) => r.status === 200,
    });
    errorRate.add(!passed);
  });

  group('GET /materials/1/signal (authenticated)', () => {
    const res = http.get(`${BASE_URL}/materials/1/signal`, authHeaders);
    signalDuration.add(res.timings.duration);
    // On a fresh DB with no scoring job having run yet, a 404 here is
    // correct, expected behavior — not a test failure. Only genuine errors
    // (5xx, connection failures, unexpected 4xx) should count against us.
    const passed = check(res, {
      'signal: status is 200 or 404': (r) => r.status === 200 || r.status === 404,
    });
    errorRate.add(!passed);
  });

  sleep(1);
}
