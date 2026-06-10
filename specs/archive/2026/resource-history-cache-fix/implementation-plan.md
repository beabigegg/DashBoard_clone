---
change-id: resource-history-cache-fix
schema-version: 0.1.0
last-changed: 2026-06-10
---

# Implementation Plan: resource-history-cache-fix

## Objective
Make the canonical (filter-less, granularity-less) spool key the single storage key for the warm resource-history dataset so the warmup job and the route's canonical read path agree, eliminating the permanent SPOOL_MISS. Bump the canonical schema version to invalidate stale parquet, stop the route from silently swallowing canonical errors, and add an optional short-TTL view-result cache. API response shape and source SQL are unchanged. See `design.md §Summary`.

## Execution Scope

### In Scope
- `resource_dataset_cache.py`: drop `granularity` from canonical key builders (D1); bump `_CANONICAL_BASE_SCHEMA_VERSION` 1→2 (D1); add a canonical-write warmup helper and rewire `ensure_dataset_loaded()` to use it (D2); co-write the canonical key on an empty-filter Oracle fetch inside `execute_primary_query()` (D3); add the view-result cache in `apply_view()` behind `RESOURCE_VIEW_CACHE_TTL` (D5).
- `resource_history_sql_runtime.py`: drop `granularity` from the canonical key composition in `try_compute_query_from_canonical_spool()` to match D1.
- `resource_history_routes.py`: remove the `except Exception: pass` swallow around the canonical call in `/query` (D3 route); SPOOL_MISS stays a normal `None` fallthrough, not an exception.
- `contracts/env/env-contract.md`, `contracts/env/env.schema.json`, `contracts/CHANGELOG.md`: register `RESOURCE_VIEW_CACHE_TTL` (env schema-version 1.0.4→1.0.5) — BLOCKING.
- Tests per `test-plan.md` (TDD order below).
- `contracts/business/business-rules.md`: add RH-05 / RH-06 — RECOMMENDED, non-blocking.

### Out of Scope (Non-goals)
- Do NOT change the API response shape (route contract; AC-5).
- Do NOT change `base_facts.sql` / `oee_facts.sql` or any file under `src/mes_dashboard/sql/resource_history/`.
- Do NOT remove System A (filter-inclusive key) — it stays as the Oracle fallback path (`design.md` D4).
- Do NOT touch frontend code.
- Do NOT change the multi-worker startup lock in `resource_history_duckdb_cache.py` (`design.md` D6 — independent substrate).
- Do NOT change the warmup scheduler (`spool_warmup_scheduler.py`) — behavior verified only.
- Do NOT opportunistically refactor `execute_primary_query` chunking / OEE paths.

## Required Changes

| id | area | required action | owner agent |
|---|---|---|---|
| IP-1 | canonical key builders | Remove `granularity` param/field from `make_canonical_base_query_id` + `make_canonical_oee_query_id` (lines 581-606); bump `_CANONICAL_BASE_SCHEMA_VERSION` 1→2 (line 578) | backend-engineer |
| IP-2 | warmup loader | Add internal `_query_and_store_canonical_dataset` helper that queries Oracle unfiltered and `register_spool_file`s base + OEE under canonical keys; call it from `ensure_dataset_loaded()` (609-631) instead of bare `execute_primary_query()` | backend-engineer |
| IP-3 | primary query co-write | In `execute_primary_query`, when filters are empty, also `register_spool_file(_REDIS_NAMESPACE, canonical_base_key, ...)` (and OEE canonical key) | backend-engineer |
| IP-4 | canonical read path | In `try_compute_query_from_canonical_spool`, drop `granularity` from `make_canonical_base_query_id` (≈line 706) / `make_canonical_oee_query_id` (≈line 716) calls | backend-engineer |
| IP-5 | route swallow removal | Remove `try/except Exception: pass` wrapper at `routes/resource_history_routes.py:200,219-220`; keep `if canonical_result is not None` HIT and let `None` fall through to `execute_primary_query` | backend-engineer |
| IP-6 | view-result cache | Add `_RESOURCE_VIEW_CACHE_TTL` constant + result cache in `apply_view()` (D5) | backend-engineer |
| IP-7 | env contract (BLOCKING) | Add `RESOURCE_VIEW_CACHE_TTL` row + prose to `env-contract.md` (bump schema-version 1.0.4→1.0.5), `env.schema.json` property, `## [env 1.0.5]` to `contracts/CHANGELOG.md` | backend-engineer |
| IP-8 | tests | Write 5 failing TDD anchors first, then full suite per `test-plan.md` | backend-engineer |
| IP-9 | business rules (RECOMMENDED) | Add RH-05 / RH-06 to `business-rules.md` | backend-engineer |

## Source Artifact Pointers

| source | relevant pointer | used for |
|---|---|---|
| design.md | D1–D7 (Key Decisions) | implementation constraints for IP-1..IP-6 |
| design.md | §Migration / Rollback | schema_version bump + parquet cleanup |
| test-plan.md | AC mapping table + §Tests That Must Fail | test files / names / TDD order |
| test-plan.md | §Notes | mock-boundary + `assert_called_once()` discipline |
| ci-gates.md | §Required Gates table | verification commands |
| ci-gates.md | §Rollback Policy | post-deploy parquet cleanup |
| change-classification.md | §Inferred Acceptance Criteria AC-1..AC-8 | acceptance mapping |
| contracts/env/env-contract.md | line 6 `schema-version`, line 86 row pattern | env entry format for IP-7 |
| contracts/CHANGELOG.md | line 39 `## [env 1.0.4]` | next env CHANGELOG entry header |

## File-Level Plan

| path or glob | action | notes |
|---|---|---|
| `src/mes_dashboard/services/resource_dataset_cache.py` | edit | IP-1 (578, 581-606), IP-2 (`ensure_dataset_loaded` 609-631 + new helper), IP-3 (empty-filter co-write near `register_spool_file` 410-451 / store helpers), IP-6 (`apply_view` 496-523 + new `_RESOURCE_VIEW_CACHE_TTL` near line 38). Reuse existing `register_spool_file`, `store_spooled_df`, `_get_cache_ttl`, `ProcessLevelCache`. |
| `src/mes_dashboard/services/resource_history_sql_runtime.py` | edit | IP-4: drop `granularity` arg at `make_canonical_base_query_id(...)` (≈706) and `make_canonical_oee_query_id(...)` (≈716). Do NOT change `_query_trend`/`_query_heatmap`/`_query_detail_by_date` bucketing — granularity is still applied at view compute time. |
| `src/mes_dashboard/routes/resource_history_routes.py` | edit | IP-5: lines 198-227 — remove inner `try/except Exception: pass` (200, 219-220). Keep import, HIT branch (216-218), and outer `try/except` → `internal_error` (191/230-231). |
| `contracts/env/env-contract.md` | edit | IP-7: bump `schema-version: 1.0.4`→`1.0.5`; add `RESOURCE_VIEW_CACHE_TTL` row (default `300`) + prose, mirroring `RESOURCE_HISTORY_HISTORICAL_TTL` (lines 86/91). |
| `contracts/env/env.schema.json` | edit | IP-7: add `RESOURCE_VIEW_CACHE_TTL` property (integer, default 300). |
| `contracts/CHANGELOG.md` | edit | IP-7: add `## [env 1.0.5] — <date>` entry above line 39. CHANGELOG is the ONLY location `cdd-kit validate --versions` scans. |
| `contracts/business/business-rules.md` | edit | IP-9 (recommended): RH-05 (canonical key excludes granularity + filters) and RH-06 (view-result cache TTL staleness window). |
| `tests/test_resource_dataset_cache.py` | create/edit | IP-8: TDD anchors 1,2,4 + AC-2/AC-4/AC-6/AC-7/AC-8 rows. |
| `tests/test_resource_history_sql_runtime.py` | edit | IP-8: TDD anchor 3 (`TestCanonicalKeyGranularity`). |
| `tests/test_resource_history_routes.py` | edit | IP-8: AC-5 (response keys unchanged) + extend `test_query_bootstrap_render_failure_returns_500` to assert canonical exception now propagates. |
| `tests/test_env_contract.py` | edit | IP-8: TDD anchor 5 (`TestResourceViewCacheTTLDefault`). |
| `tests/e2e/test_resource_history_e2e.py` | edit | IP-8: extend `TestResourceHistorySpoolReuse` integration rows (AC-1/AC-3/AC-4). |

## Contract Updates

- API: none — response shape unchanged (read-only verify, AC-5).
- CSS/UI: none.
- Env: ADD `RESOURCE_VIEW_CACHE_TTL` (default 300; TTL=0 disables view cache). Bump env schema-version 1.0.4→1.0.5 in `env-contract.md`; add `## [env 1.0.5]` to `contracts/CHANGELOG.md`; add property to `env.schema.json`. BLOCKING for `cdd-kit validate`.
- Data shape: none — source columns unchanged.
- Business logic: RECOMMENDED RH-05 / RH-06 in `business-rules.md` (non-blocking).
- CI/CD: none — existing workflows cover all gates (`ci-gates.md §CI/CD Workflow`).

## Test Execution Plan

TDD: write the 5 anchors first and confirm they FAIL, then implement IP-1..IP-7, then confirm all green (`test-plan.md §Tests That Must Fail Before Implementation`).

| acceptance criterion | test file / command | expected signal |
|---|---|---|
| AC-2 (TDD #1) | `tests/test_resource_dataset_cache.py::TestCanonicalKeyParity::test_ensure_dataset_loaded_writes_canonical_key` | warmup `register_spool_file` called with canonical base key (assert key positional/kwarg == `make_canonical_base_query_id(...)`) |
| AC-1 (TDD #2) | `tests/test_resource_dataset_cache.py::TestCanonicalSpoolHit::test_ensure_dataset_loaded_produces_canonical_hit` | after warmup, `try_compute_query_from_canonical_spool` returns non-None (HIT, not SPOOL_MISS) |
| AC-3 (TDD #3) | `tests/test_resource_history_sql_runtime.py::TestCanonicalKeyGranularity::test_day_week_month_year_produce_identical_canonical_key` | all four granularities map to identical canonical key string |
| AC-7 (TDD #4) | `tests/test_resource_dataset_cache.py::TestViewResultCache::test_apply_view_result_cached_within_ttl` | second `apply_view` within TTL does not re-invoke `try_compute_view_from_spool` |
| AC-7+env (TDD #5) | `tests/test_env_contract.py::TestResourceViewCacheTTLDefault::test_resource_view_cache_ttl_default_equals_300` | imported module-level `RESOURCE_VIEW_CACHE_TTL` == 300 |
| AC-2/4/5/6/8 + rest AC-7 | full mapping in `test-plan.md` table | all green |
| gate (all) | `pytest tests/test_resource_dataset_cache.py tests/test_resource_cache_version_check.py tests/test_resource_history_routes.py tests/test_resource_history_sql_runtime.py tests/test_resource_cache.py -v --tb=short` | green (`ci-gates.md §Required Gates`) |
| gate (env) | `pytest tests/test_env_contract.py -v` | green |
| gate (contract) | `cdd-kit validate` | env 1.0.5 parity passes |

## Handoff Constraints

- Implementation agents must not infer missing requirements from chat history.
- Do not re-copy full design, test strategy, CI policy, or contract prose into this plan; follow the source pointers above.
- Empty-filter detection in IP-3 must be exactly: `not workcenter_groups and not families and not resource_ids and not is_production and not is_key and not is_monitor and not package_groups`. Misclassification writes the wrong key — pin with the AC-2 parity test (`design.md` Open Risks).
- Per CLAUDE.md / `test-plan.md §Notes`: assert `mock.assert_called_once()` + `call_args.kwargs[key] == value`; never `assert_called_once_with(...)` as a kwarg whitelist. Mock at the Redis/spool-store boundary (`store_spooled_df`, `register_spool_file`, `redis_df_store`), not internal methods.
- `RESOURCE_VIEW_CACHE_TTL` is read into a module-level constant at import — `test_env_contract.py` must import the constant directly; `monkeypatch.setenv` is ineffective (CLAUDE.md frozen-constant rule).
- Env version entry goes ONLY in `contracts/CHANGELOG.md` (`## [env 1.0.5]`), never inside `env-contract.md` body (CLAUDE.md cdd-kit rule).
- Cache-namespace discipline (CLAUDE.md): the canonical write MUST land in `_REDIS_NAMESPACE = "resource_dataset"` / `_OEE_REDIS_NAMESPACE = "resource_oee"` — the exact namespaces the read path queries. Do not introduce a new prefix.
- After editing `env-contract.md`/CHANGELOG, run `cdd-kit validate` to confirm version parity before commit.
- If this plan omits a required file, behavior, contract, or test, stop and report `blocked`.
- Keep implementation within the file-level plan unless a Context Expansion Request is approved.

## Known Risks

- Empty-filter co-write (IP-3) misclassification writes the wrong canonical key → silent zero cache benefit. Mitigated by AC-2 parity test.
- Schema-version bump (IP-1) invalidates all v1 parquet; old files miss → Oracle (no `BinderException`). Post-deploy `rm tmp/query_spool/resource_dataset/*.parquet` + `rm tmp/query_spool/resource_oee/*.parquet` required — see `ci-gates.md §Rollback Policy`.
- View-cache TTL 300s can serve up to 5-min-stale derived numbers on a warm dataset (`design.md` Open Risks). Acceptable for a reporting surface; documented in RH-06.
- D4 leaves System A live; a future filter param added to System A but not the canonical view-time filter would diverge silently — out of scope here, flagged for the follow-up deprecation change.
- IP-5 route swallow removal changes failure semantics: a genuine canonical runtime error now surfaces (covered by extending `test_query_bootstrap_render_failure_returns_500`). SPOOL_MISS must remain a `None` return, not an exception.
