# Current Behavior

## Current User Flow

1. User navigates to resource-history page and selects a date range + filters.
2. User clicks "Query" → frontend POSTs to `/api/resource/history/query`.
3. Backend runs Oracle queries (batched into 31-day chunks for ranges > 10 days), writes results to a Parquet spool file in `tmp/query_spool/resource_dataset/` and `resource_oee/`.
4. Backend returns `{ spool_download_url, row_count, ... }` (or inline data for small results).
5. Frontend either renders inline data or activates DuckDB-WASM to load the Parquet spool for local view computation.
6. No progress feedback is given during step 3; the user sees a spinner with no percentage indication.

## Current API / Data Flow

- `POST /api/resource/history/query` — submits the query; Oracle → Parquet spool → response
- `GET /api/resource/history/view` — DuckDB view computation on the spool file
- Redis cache key: based on date range + granularity (filter-at-view-time pattern)
- Current Redis TTL: **7 200 seconds (2 hours)** for all queries regardless of date recency
- No pre-warming: cache is cold on service restart; first query for any date range hits Oracle

## Current Business Rules

- Batch engine splits date ranges > 10 days into 31-day chunks and queries Oracle in parallel.
- Cache key is canonical and keyed on base date range + granularity only (filters applied at view time).
- DuckDB-WASM activated client-side when `row_count >= threshold` and `spool_download_url` present.

## Current UI States

- Loading: generic spinner shown during query execution; no progress percentage or estimated time.
- Done: results table + KPI cards rendered.
- Error: error banner with message.

## Current Tests

- `tests/test_resource_history_service.py` — unit tests for query/view logic
- `tests/test_resource_history_routes.py` — route tests
- `tests/test_cache_integration.py` — cache integration (generic, not resource-history specific)
- `tests/e2e/test_resource_history_e2e.py`, `test_resource_history_browser_e2e.py` — E2E
- `tests/stress/test_resource_history_stress.py` — stress tests
- `frontend/tests/legacy/resource-history.test.js` — OEE formula parity (16 tests)

## Known Issues

- Long date ranges (e.g. 90 days) cause Oracle batch queries taking 30–60+ seconds with no progress signal.
- 2h Redis TTL causes unnecessary Oracle re-queries for immutable historical data (end_date < today − 2 days) on every new user session after cache expires.
- Cold start: first user after service restart always hits Oracle regardless of query recency.

## Compatibility Constraints

- `index.html` still references `./main.js` (cosmetic, Vite resolves `main.ts` automatically).
- DuckDB-WASM activation threshold is governed by `frontend/src/core/duckdb-activation-policy.ts`.

## Regression Scope

- Any change to Redis TTL assignment must not reduce cache effectiveness for recent data.
- Pre-warm startup must not block gunicorn worker readiness.
- Progress endpoint must return JSON matching the declared data-shape-contract payload shape.
