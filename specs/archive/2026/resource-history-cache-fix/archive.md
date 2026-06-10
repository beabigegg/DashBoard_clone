# Archive: resource-history-cache-fix

> **Cold Data Warning**: This archive is historical evidence. Current requirements live in `contracts/` and active project guidance.

## Change Summary

The resource-history canonical spool key previously included `granularity` as part of its hash, causing every granularity switch (day/week/month/year) to miss the cache and issue a fresh Oracle query. Additionally, the warmup scheduler wrote a canonical spool for the full 90-day window but `try_compute_query_from_canonical_spool` only performed exact-match key lookups — so any user query for a sub-range (e.g., last 7 days) would also miss. This change removes granularity from the canonical key, adds a warmup-superset lookup so any sub-range query within the 90-day warmup window hits DuckDB directly, introduces an in-process TTL view-result cache for repeated granularity/filter switches on a warm dataset, and removes a silent `except Exception: pass` that was hiding spool errors at the route layer.

## Final Behavior

- **Canonical spool key** = `hash(schema_version + start_date + end_date)` — granularity and filters excluded; one parquet covers all views for that date range.
- **Warmup superset lookup**: if `[req_start, req_end] ⊆ [today-89d, today]` and the warmup parquet exists, the request is served from DuckDB with a `WHERE DATA_DATE BETWEEN …` / `WHERE SHIFT_DATE BETWEEN …` filter injected into the temp view — no Oracle call.
- **View-result cache** (`MemoryTTLCache`, default TTL 300 s, configurable via `RESOURCE_VIEW_CACHE_TTL`): repeated `apply_view` calls with the same `query_id` + `granularity` return the cached structure without re-running DuckDB aggregation.
- **Empty-filter co-write** (IP-3): when a user query has no filters, `execute_primary_query` also writes the result under the canonical key, priming the cache for future canonical hits.
- **Schema version** bumped 1 → 2; old parquet files produce key misses and fall through to Oracle with no error.
- Route-layer `except Exception: pass` removed; genuine spool errors now surface as 500 rather than silently falling to Oracle.

## Final Contracts Updated

| Contract | Change | Evidence |
|---|---|---|
| `contracts/env/env-contract.md` | schema-version 1.0.4 → 1.0.5; `RESOURCE_VIEW_CACHE_TTL` added | agent-log/backend-engineer.yml |
| `contracts/env/env.schema.json` | `RESOURCE_VIEW_CACHE_TTL` property added | agent-log/backend-engineer.yml |
| `contracts/business/business-rules.md` | schema-version 1.14.0 → 1.15.0; RH-05 + RH-06 added | agent-log/backend-engineer.yml |
| `contracts/CHANGELOG.md` | `## [env 1.0.5]`, `## [business 1.15.0]` entries | agent-log/backend-engineer.yml |

## Final Tests Added / Updated

| Test | Coverage |
|---|---|
| `tests/test_resource_dataset_cache.py::TestCanonicalKeyParity` (3 tests) | ensure_dataset_loaded writes canonical key; empty-filter co-write; non-empty skip |
| `tests/test_resource_dataset_cache.py::TestCanonicalSpoolHit` | warmup produces canonical hit |
| `tests/test_resource_dataset_cache.py::TestWarmCacheFilterSwitch` | filter switch on warm cache: no Oracle call |
| `tests/test_resource_dataset_cache.py::TestSchemaVersionInvalidation` | schema version bump invalidates stale spool |
| `tests/test_resource_dataset_cache.py::{TestRedisDownFallback,TestStaleParquetFallback,TestOracleFallbackPath}` | resilience paths |
| `tests/test_resource_dataset_cache.py::TestViewResultCache` (4 tests) | TTL cache hit/miss/zero-disable/atomic-write |
| `tests/test_resource_history_sql_runtime.py::TestCanonicalKeyGranularity` | day/week/month/year → identical canonical key |
| `tests/test_resource_history_sql_runtime.py::TestWarmupSupersetLookup` (3 tests) | subset uses warmup key; date filter injected; outside warmup → miss |
| `tests/test_env_contract.py::TestResourceViewCacheTTLDefault` (2 tests) | default=300; documented in contract |

Final passing count: **59 new/modified tests**; full suite **all green**.

## Final CI/CD Gates

| Gate | Result |
|---|---|
| `pytest` resource cache suite (AC-1–AC-8) | PASS |
| `backend-tests.yml` unit-and-integration-tests | PASS (CI confirmed) |
| `contract-driven-gates.yml` contract-and-fast-tests | PASS (CI confirmed) |
| `real-infra-smoke` (Tier 2 informational) | informational only |

## Production Reality Findings

- Warmup runs **async via RQ** at startup (`init_warmup_scheduler` → `run_warmup_cycle` → RQ job); not synchronous. The first request after a cold start that arrives before the RQ job completes still hits Oracle.
- ISO date string lexicographic comparison (`_warmup_start <= start_date`) is valid for YYYY-MM-DD format; no date parsing needed.
- Lazy function-body imports (`create_heavy_query_connection`, `_get_filtered_resources`, `_build_resource_lookup`, `_get_workcenter_mapping`) require source-module patches in tests, not `resource_history_sql_runtime.*` patches.

## Lessons Promoted to Standards

| # | Lesson | Target | Evidence |
|---|---|---|---|
| 1 | Two-phase canonical spool key resolution (warmup superset + exact-match fallback); `DATA_DATE` vs `SHIFT_DATE` column split | `CLAUDE.md ## Cache Architecture Notes` (added bullet after "Type-A spool frontend key mismatch") | `resource_history_sql_runtime.py:707-750`; `TestWarmupSupersetLookup` |

Not promoted: canonical key excludes granularity (already in RH-05 contract); warmup async design (implicit in RQ model, not a trap); lazy-import patching list (general rule already in `## Downtime Analysis Service Architecture Notes`).

## Follow-up Work

- AC-3 tautological test (noted non-blocking by QA): `test_day_week_month_year_produce_identical_canonical_key` asserts the post-implementation invariant but doesn't prove pre-implementation failure because the test itself was written after the key was simplified. Low priority — the invariant is covered structurally.
- First-request latency (cold RQ worker): warmup is async; users who query immediately after server restart before the RQ job completes will still hit Oracle for the first request of the 90-day window. Acceptable per design — no fix required.
