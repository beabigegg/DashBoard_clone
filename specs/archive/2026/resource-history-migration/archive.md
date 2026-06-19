---
change-id: resource-history-migration
closed: 2026-06-19
ci: passed (contract-driven-gates ✅, backend-tests ✅, released-pages-hardening-gates ✅)
---

# Archive: resource-history-migration

## Change Summary

Migrated resource-history query execution off the in-gunicorn full-DataFrame Oracle reads onto the unified `BaseChunkedDuckDBJob` pipeline (P3 of the query-dataflow-unification roadmap). Two new chunked workers were added behind `RESOURCE_HISTORY_USE_UNIFIED_JOB` (default `off`, restart required): `ResourceHistoryBaseJob` (`requires_cross_chunk_reduction=False`, namespace `resource_dataset`) handles shift/base facts via ChunkStrategy.TIME + multi-parquet append; `ResourceHistoryOeeJob` (`requires_cross_chunk_reduction=True`, namespace `resource_oee`) handles OEE trackout+NG via per-chunk ±30d reject-window widening and `post_aggregate` GROUP BY EQUIPMENTID ratio-of-SUMs in job-temp DuckDB. Both use `always_async=True`; flag-on degraded → 503 (no sync fallback). Legacy `export_csv` + `iterrows` path is byte-for-byte unchanged at flag=off.

## Final Behavior

- **Flag=off (default):** No behavioral change. Legacy `export_csv()` Oracle read + `iterrows` OEE computation path unchanged.
- **Flag=on:** Export route enqueues two RQ jobs (`resource-history-base`, `resource-history-oee`) via `enqueue_query_job`. If `is_async_available()` is False → HTTP 503 with `Retry-After: 30`. Both job results awaited; CSV streamed from DuckDB spool join via `export_csv_from_spools()`. OEE formula: `yield = ΣTRACKOUT/(ΣTRACKOUT+ΣNG)`, `oee = availability * yield / 100` — identical to legacy iterrows.
- **Spool schema:** `resource_dataset` schema unchanged. `resource_oee` unified path outputs `{EQUIPMENTID, TRACKOUT_QTY, NG_QTY}` — SHIFT_DATE absent (post_aggregate groups by EQUIPMENTID only; no consumer reads SHIFT_DATE from this spool).

## Final Contracts Updated

| contract | version | change |
|---|---|---|
| `contracts/env/env-contract.md` | 1.0.16 → 1.0.17 | `RESOURCE_HISTORY_USE_UNIFIED_JOB` (default `off`, restart) |
| `contracts/env/env.schema.json` | — | `RESOURCE_HISTORY_USE_UNIFIED_JOB` property (enum/default) |
| `contracts/business/business-rules.md` | 1.24.0 → 1.25.0 | ASYNC-09: dual-job unified execution rule |
| `contracts/data/data-shape-contract.md` | 1.20.0 → 1.21.0 | §3.19 spool-schema UNCHANGED assertion; clarified resource_oee column set per path |
| `contracts/ci/ci-gate-contract.md` | 1.3.27 → 1.3.28 | P3 gate compat note |
| `contracts/CHANGELOG.md` | — | All four version entries |

## Final Tests Added / Updated

| file | type | count |
|---|---|---|
| `tests/test_resource_history_unified_job.py` | new | 18 tests (AC-2/3/4/6) |
| `tests/test_resource_history_job_service.py` | new | 5 tests (AC-5; route-driven dispatch via Flask client) |
| `tests/test_resource_history_service.py` | extended | +4 tests (AC-1/7/8); duplicate class renamed |
| `tests/test_query_cost_policy.py` | extended | `_APPROVED_CALLERS` + 2 worker stems (AC-8) |
| `tests/test_async_query_job_service.py` | extended | +4 tests with importlib.reload (AC-9) |
| `tests/integration/test_resource_history_rq_async.py` | stub | 2 stubs (integration_real; nightly gate pre-flag-promotion) |

Final targeted test count: **142 pass**.

## Final CI/CD Gates

| gate | tier | result |
|---|---|---|
| contract-driven-gates | 1 | ✅ CI passed |
| backend-tests | 1 | ✅ CI passed |
| released-pages-hardening-gates | 1 | ✅ CI passed |
| nightly-integration (OEE parity) | 3 | 🔵 deferred; required before flag=on promotion |
| stress-load | 4 | 🔵 deferred; required before flag=on promotion |

## Production Reality Findings

1. **SHIFT_DATE drop in unified OEE path**: `post_aggregate` groups by EQUIPMENTID only; SHIFT_DATE present in the raw job-temp table but absent from the final `resource_oee` parquet. The data-shape-contract.md §3.19 initially claimed the column set was "unchanged" — corrected by contract-reviewer (CR-2). No consumer reads SHIFT_DATE from the OEE spool, so non-breaking. AC-6 `_OEE_LEGACY_COLS` was correctly written as `{EQUIPMENTID, TRACKOUT_QTY, NG_QTY}`.

2. **env.schema.json omission**: `RESOURCE_HISTORY_USE_UNIFIED_JOB` was missing from `env.schema.json` (only added to `env-contract.md`). Caught by contract-reviewer (CR-1). Machine validation does not enforce enum constraints on properties absent from the schema.

3. **Tautological AC-5 dispatch tests**: Two tests in `test_resource_history_job_service.py` called `_mock_enqueue()` directly without invoking the route. Caught by qa-reviewer (QA-3). Fixed by using Flask test client + `patch aqs.enqueue_query_job` + real GET request.

4. **Duplicate test class shadow**: `TestExportCsv` appeared twice in `test_resource_history_service.py`; second definition shadowed the first (Python class re-definition semantics), silently dropping `test_successful_export` (AC-1 guard) from collection. Caught by qa-reviewer (QA-1). Fixed by renaming duplicate class to `TestFlagOffRegression`.

## Lessons Promoted to Standards

1. **env.schema.json feature-flag completeness** — promote-to-guidance
   - `CLAUDE.md` (Test coverage discipline section): "New feature-flag rows in `env-contract.md` must also be added to `contracts/env/env.schema.json` with `enum` + `default`; entries absent from the schema bypass machine enum validation (`cdd-kit validate --contracts` will not catch the typo) — see contracts/env/env.schema.json"
   - Evidence: contract-reviewer.yml CR-1

2. **Spool-schema UNCHANGED assertion — per-path column documentation** — promote-to-guidance
   - `CLAUDE.md` (Cache & spool patterns section): "Spool-schema "UNCHANGED" assertions: when legacy and unified paths produce different column sets, document each path's columns separately — a blanket "UNCHANGED" claim when columns differ is a false contract — see docs/architecture/cache-spool-patterns.md"
   - `docs/architecture/cache-spool-patterns.md`: new section "Spool-Schema 'UNCHANGED' Assertion — Per-Path Column Documentation"
   - Evidence: contract-reviewer.yml CR-2

## Follow-up Work

- **Nightly OEE parity** (`tests/integration/test_resource_history_rq_async.py`): Run Tier 3 nightly-integration gate before promoting `RESOURCE_HISTORY_USE_UNIFIED_JOB=on`. Tests verify ±30d seam cross-chunk correctness against real Oracle.
- **Stress gate**: Tier 4 stress-load gate (two RQ jobs per export doubles queue traffic) required before production flag promotion.
- **Worker systemd env-var parity**: `resource-history-query` systemd unit must export `RESOURCE_HISTORY_USE_UNIFIED_JOB` before flag-on promotion (ci-gates.md Deploy Checklist #5).
- **Flag promotion sequence**: Both jobs (base + OEE) must be validated and promoted together — no partial enablement.

---

*This archive is historical evidence. Current requirements live in `contracts/` and active project guidance.*
