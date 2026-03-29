## Context

### Current Architecture

After Phase 2, the L2 cache write path no longer stores large DataFrames in Redis. However, the view request path still has a pandas-based fallback in all four historical domains:

```
apply_view(query_id, params)
  └─ DuckDB SQL runtime (try_compute_view_from_spool / apply_view)
       ├─ [success] → return DuckDB result
       └─ [fail / spool miss] → _get_cached_df(query_id)  ← Phase 3 target
                                   └─ load_spooled_df()
                                        └─ _derive_*(df)  ← pandas in-memory derivation
```

Each `_derive_*()` call materializes the full spool DataFrame in the gunicorn request thread:
- resource: `_derive_kpi()`, `_derive_trend()`, `_derive_heatmap()`, `_derive_comparison()`, `_derive_detail()` — up to 50–100 MB
- hold: `_derive_all_views()` — up to 30–80 MB
- yield-alert: pandas fallback block (L1497–1623) — up to 30–80 MB
- reject: `_get_cached_df()` → inline derive — up to 50–100 MB

### Reference Model

`production-history` — `apply_view()` calls `try_compute_view_from_spool()` (DuckDB), and if that returns no result, it returns `cache_expired` (410). There is no pandas fallback.

### DuckDB Runtimes

All four domains already have production-ready DuckDB SQL runtimes:
- `resource_history_sql_runtime.py` (`try_compute_query_from_canonical_spool()`)
- `hold_history_sql_runtime.py` (`try_compute_view_from_spool()`)
- `yield_alert_sql_runtime.py` (`apply_view_sql()` embedded)
- `reject_cache_sql_runtime.py` (`try_compute_view_from_spool()` or equivalent)

## Goals

- DuckDB SQL runtime becomes the sole view compute engine for all four domains
- `_get_cached_df()` and all `_derive_*()` functions are retired from the view path
- Per-view RAM reduction: eliminate up to 50–100 MB per-worker DataFrame materialization
- Simplify service code: dual-path view logic collapses to single DuckDB path

## Non-Goals

- Changes to `execute_primary_query()` (spool write path) — Phase 2 handled this
- Changes to the async RQ path in reject-history
- Changes to `production-history`, `material-trace`, `MSD` — already DuckDB-only
- Frontend contract changes — Phase 4 concern
- Removing `_get_cached_df()` entirely — it may still be called by `execute_primary_query()` warmup path; Phase 3 only removes it from the view path

## Decisions

### D1: No pandas fallback for spool miss

**Decision**: When DuckDB runtime cannot compute a view (spool file missing, DuckDB error, or runtime unavailable), `apply_view()` SHALL return `cache_expired` (410). No pandas fallback.

**Rationale**: The spool file should always exist if the primary query completed successfully. If it doesn't, the client must re-query — same as `production-history` behavior. Keeping a pandas fallback creates a hidden RAM bomb and makes the dual-path code permanently necessary.

**Rejected alternative**: Keep pandas fallback behind a feature flag. Rejected because it adds complexity and the fallback has never been the "safe" path — it's the high-RAM path. The correct response to spool miss is cache_expired.

### D2: One domain per PR, resource-history first

**Decision**: Implement Phase 3 domain-by-domain in the order: resource-history → hold-history → yield-alert → reject-history.

**Rationale**: Each domain has independent DuckDB runtime. Starting with resource-history (cleanest separation, most similar to production-history) reduces risk. If a domain's DuckDB runtime has gaps, fixing them is bounded to that domain.

### D3: Delete dead code (pandas _derive_* functions) immediately

**Decision**: Remove `_derive_kpi()`, `_derive_trend()`, `_derive_heatmap()`, `_derive_comparison()`, `_derive_detail()`, `_derive_all_views()` and their sub-functions from each service module as part of the same commit as the view path change.

**Rationale**: Leaving dead code creates false impression that the fallback is still available. Deletion is the correct signal that Phase 3 is complete for that domain.

**Exception**: `_get_cached_df()` may remain if still called by warmup/engine-path routines; remove only if it becomes fully unreachable.

### D4: DuckDB feature flag behavior unchanged

**Decision**: If the DuckDB feature flag is set to `0` (disabled), `apply_view()` returns `cache_expired` rather than falling back to pandas.

**Rationale**: The feature flag was designed for incremental rollout of DuckDB, not as a permanent pandas/DuckDB toggle. With Phase 3, there is no pandas path to fall back to. Operators disabling the DuckDB flag should expect cache_expired responses.

## Risk Table

| Risk | Severity | Mitigation |
|---|---|---|
| DuckDB runtime has missing coverage (some query params not handled) | High | Audit each runtime's SQL coverage against pandas output before removing fallback; add missing SQL cases |
| reject-history async path touches `_get_cached_df()` indirectly | Medium | Trace `reject_dataset_cache.py` apply_view call graph carefully; only remove pandas derive, not cache read |
| yield-alert pandas fallback covers edge cases DuckDB doesn't | Medium | Run side-by-side comparison tests before removing fallback |
| spool file corruption triggers permanent 410 instead of re-query | Low | Client already handles 410 as re-query signal (per Phase 2 spec) |

## Migration Steps

1. **resource-history**: Audit `resource_history_sql_runtime.py` coverage → remove pandas derive from `apply_view()` → delete `_derive_*` functions → pytest
2. **hold-history**: Audit `hold_history_sql_runtime.py` coverage → same pattern
3. **yield-alert**: Audit `yield_alert_sql_runtime.py` coverage → remove pandas fallback block (L1497–1623) → pytest
4. **reject-history**: Audit `reject_cache_sql_runtime.py` coverage → remove pandas derive from view path → pytest
5. **Update governed specs**: `parquet-spool-view-engine`, `resource-dataset-cache`, `hold-dataset-cache`, `yield-alert-spool-query`, `reject-history-api`
