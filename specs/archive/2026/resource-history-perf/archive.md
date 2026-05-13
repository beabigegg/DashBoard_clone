---
change-id: resource-history-perf
archived: 2026-05-13
ci-commit: 02d3ed6
---

# Archive — resource-history-perf

## Change Summary

Resource-history queries were slow after service restart because the original startup pre-warm wrote to a separate `resource_history_prewarm` Redis namespace that user queries never read from. The fix completely replaced the pre-warm architecture: a new `resource_history_duckdb_cache.py` module loads the last 3 months of `base_facts` + `oee_facts` from Oracle into a persistent DuckDB file (~11.3 MB) at startup. User queries with `end_date ∈ [today-90d, yesterday]` are routed to DuckDB instead of Oracle, reducing per-query latency from 13–20 s to 65–111 ms.

## Final Behavior

- **Startup**: `start_duckdb_prewarm()` fires a background daemon thread 10 s after each gunicorn worker boot.  A file-based lock (`resource_history.duckdb.loading`) ensures only one worker loads from Oracle; others wait and reuse the completed file.  On same-day respawn, `_try_reuse_existing()` detects today's cache and skips Oracle entirely.
- **Query routing**: `execute_primary_query` in `resource_dataset_cache.py` checks `should_use_duckdb(end_date)` before the Oracle path.  If DuckDB is ready and end_date is within the 3-month window (and not today), DuckDB serves the base + OEE data (~65–111 ms).  Queries for today's date or dates outside the window fall through to Oracle with existing TTL logic.
- **Env vars added**: `RESOURCE_HISTORY_HISTORICAL_TTL` (24h Redis TTL for historical queries), `RESOURCE_HISTORY_PREWARM_MONTHS` (DuckDB window in months, default 3), `RESOURCE_HISTORY_DUCKDB_PATH` (DuckDB file path, default `tmp/resource_history.duckdb`).
- **Removed**: wrong `prewarm_last_n_months()` / `start_resource_history_prewarm()` from `resource_history_service.py`; `warmup-resource-history` job from `spool_warmup_scheduler.py`.

## Final Contracts Updated

- `contracts/env/env-contract.md` — schema-version 1.0.2: added `RESOURCE_HISTORY_DUCKDB_PATH`; updated `RESOURCE_HISTORY_PREWARM_MONTHS` description (was Redis pre-warm months, now DuckDB window months)
- `contracts/CHANGELOG.md` — entries `[env 1.0.2]` and `[env 1.0.1]` added
- `contracts/api/api-contract.md` — `[api 1.2.2]`: progress endpoint `GET /api/resource/history/query/progress`
- `contracts/data/data-shape-contract.md` — `[data 1.0.2]`: resource-history batch query progress response shape
- `contracts/ci/ci-gate-contract.md` — `[ci 1.3.10]`: DuckDB prewarm gate compatibility note

## Final Tests Added / Updated

| file | change |
|---|---|
| `tests/test_resource_history_duckdb_cache.py` | NEW — 10 unit tests: `should_use_duckdb` routing, empty-return when not ready, `start_duckdb_prewarm` PREWARM_MONTHS=0 guard |
| `tests/test_cache_integration.py` | `TestResourceHistoryPrewarmIdempotency` → `TestResourceHistoryHistoricalTtl` (tests TTL bifurcation via `_store_df` directly) |
| `tests/test_resource_history_service.py` | `TestTtlBifurcation` imports moved from deleted prewarm symbols to `resource_dataset_cache` |
| `tests/test_resource_dataset_cache.py` | `test_execute_primary_query_uses_cache_ttl` changed end_date to `date.today()` to avoid triggering historical TTL |
| `tests/test_resource_history_prewarm.py` | DELETED — tested the wrong prewarm implementation |

## Final CI/CD Gates

All gates passed on commit `02d3ed6` (2026-05-13):
- contract-validate, lint, unit-mock-integration, frontend-unit, css-governance, playwright-resilience, playwright-data-boundary, playwright-critical-journeys, frontend-type-check (informational)

Nightly/stress gates (schedule-only) not blocking; Oracle/Redis integration verified via live runtime logs.

## Production Reality Findings

1. **Cache namespace mismatch was the root cause**: The original pre-warm used `cache_prefix="resource_history_prewarm"` via `batch_query_engine.execute_plan`, while user queries write to `resource_dataset` and `resource_oee` Redis namespaces via `register_spool_file()`. Zero cache benefit despite successful prewarm execution.
2. **Dual-worker duplicate Oracle load**: Both gunicorn workers started prewarm threads simultaneously and both hit Oracle (2× base_facts + 2× oee_facts). The file-based lock fix (`_try_lock()` / `_release_lock()`) confirmed effective on second restart: both workers logged "reusing today's cache" with no Oracle load.
3. **Runtime latency verified**: Queries at 16:20:09 (65ms), 16:29:22 (65ms), 16:29:33 (69ms), 16:29:44 (111ms) — all served via DuckDB, no Oracle fallback.

## Lessons Promoted to Standards

1. **Cache namespace must match** → `CLAUDE.md` § Cache Architecture Notes
   - Rule: pre-warm must write to the same namespace/key pattern that user queries read from.
   - Evidence: `resource_history_duckdb_cache.py` + runtime logs showing zero Oracle fallback after fix.

2. **Multi-worker startup lock** → `CLAUDE.md` § Cache Architecture Notes
   - Rule: gunicorn startup background tasks must use a file-based exclusive lock to prevent duplicate Oracle loads; losers poll `_try_reuse_existing()`.
   - Evidence: dual "prewarm: loading" log lines in first restart; "reusing today's cache" in second restart after fix.

## Follow-up Work

- `QUERY_SPOOL_DIR` is still a relative path (`tmp/query_spool`) — pre-existing warning, not introduced by this change. Should be addressed in a future Docker hardening pass.
- `container_filter_cache:refresh` Oracle query runs at 45s (unrelated to resource-history); worth investigating separately.

---

> **Cold Data Warning**: This archive is historical evidence. Current requirements live in `contracts/` and active project guidance.
