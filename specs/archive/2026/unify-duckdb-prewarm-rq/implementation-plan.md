---
change-id: unify-duckdb-prewarm-rq
schema-version: 0.1.0
last-changed: 2026-06-12
---

# Implementation Plan: unify-duckdb-prewarm-rq

## Objective
Move the resource-history and downtime-analysis DuckDB prewarms off gunicorn
daemon threads onto the existing RQ warmup queue (`_WARMUP_JOBS`), register a
downtime-analysis warmup entry (currently absent), and realign the Redis spool
metadata TTL for these two services only to 20h (72000 s) via per-service env
vars, leaving the global `CACHE_TTL_DATASET` (7200) and all other datasets
(hold/reject/yield_alert) untouched. Contracts and CHANGELOG are already written
(RH-07/08, DA-07/08, env rows); implementation must make the code and tests match
them.

## Execution Scope

### In Scope
- Add two RQ worker fns + `_WARMUP_JOBS` tuples in `spool_warmup_scheduler.py`
  (`warmup-resource-history-duckdb`, `warmup-downtime-duckdb`) per design D2.
- Expose the existing per-service prewarm body as a callable RQ entry in
  `resource_history_duckdb_cache.py` and `downtime_analysis_duckdb_cache.py`;
  retire the daemon-thread wrapper. The `_try_reuse_existing()` + fcntl lock +
  `loaded_at == today` reuse logic already exists — do not rewrite it.
- Delete both single-run `start_*_prewarm()` calls in `app.py:834-839`.
- Change `_CACHE_TTL` derivation in `resource_dataset_cache.py:37` and
  `downtime_analysis_cache.py:37` to per-service env vars (default 72000) per D4.
- Write/extend the test files named in test-plan.md §New Test Names.
- Update existing daemon-thread sentinel assertions in
  `tests/integration/test_preload_fork_safety.py` to RQ-enqueue log lines.

### Out of Scope
- No change to DuckDB refresh frequency (stays daily) or 3-month window size
  (change-request §Non-goals).
- No change to Oracle segmented batch-query logic / >3-month query path.
- No change to `CACHE_TTL_DATASET` (7200) or hold/reject/yield_alert TTLs.
- No parquet/DuckDB file deletion on deploy or rollback (schema unchanged,
  design §Migration/Rollback).
- No API/payload/CSS/UI change. Do not refactor unrelated scheduler or cache code.
- No env var to toggle RQ-vs-daemon at runtime — daemon path is removed, not gated.

## Required Changes

| id | area | required action | owner agent |
|---|---|---|---|
| IP-1 | warmup scheduler | Add 2 RQ worker fns + 2 `_WARMUP_JOBS` tuples (D2); leave existing 4 entries and enqueue/leader-lock logic untouched | backend-engineer |
| IP-2 | resource-history cache | Expose prewarm body as RQ-callable; remove daemon-thread wrapper; keep fcntl lock + `loaded_at==today` reuse | backend-engineer |
| IP-3 | downtime DuckDB cache | Same as IP-2 for downtime_analysis_duckdb_cache | backend-engineer |
| IP-4 | app startup | Delete both `start_*_prewarm()` calls at `app.py:834-839` inside the `if not is_testing_runtime:` block; remove now-unused imports | backend-engineer |
| IP-5 | resource spool TTL | `resource_dataset_cache.py:37` `_CACHE_TTL` → `int(os.getenv("RESOURCE_HISTORY_SPOOL_TTL", "72000"))` | backend-engineer |
| IP-6 | downtime spool TTL | `downtime_analysis_cache.py:37` `_CACHE_TTL` default → `"72000"` (env var name already present) | backend-engineer |
| IP-7 | unit tests | Write/extend test files per test-plan.md §New Test Names (AC-1..AC-5) | backend-engineer |
| IP-8 | resilience tests | New `tests/test_rq_warmup_resilience.py` (AC-7) | backend-engineer |
| IP-9 | integration tests | Extend `test_preload_fork_safety.py`; update daemon sentinels to RQ-enqueue log lines (AC-1, AC-6) | backend-engineer |
| IP-10 | contracts verify | Confirm code matches already-written RH-07/08, DA-07/08, env rows, CHANGELOG; no new contract prose needed | contract-reviewer |

## Source Artifact Pointers

| source | relevant pointer | used for |
|---|---|---|
| design.md | D1, D2, D3, D4; Affected Components table | implementation constraints |
| test-plan.md | AC→test mapping table; §New Test Names; §Notes | tests to write/run |
| ci-gates.md | Required Gates table; Promotion/Rollback Policy | verification commands |
| contracts/business/business-rules.md | RH-07, RH-08, DA-07, DA-08 | TTL + RQ-prewarm semantics (already written) |
| contracts/env/env-contract.md | rows `RESOURCE_HISTORY_SPOOL_TTL`, `DOWNTIME_ANALYSIS_CACHE_TTL` (defaults 72000) | env pin-test targets |
| contracts/ci/ci-gate-contract.md | lines 40-45 unit assertions + deploy note | gate assertions |
| contracts/CHANGELOG.md | business 1.11.0 / env / ci entries for this change | confirm versioned; do not duplicate |
| design.md §Migration/Rollback | no parquet cleanup | rollback runbook |

## File-Level Plan

| path or glob | action | notes |
|---|---|---|
| `src/mes_dashboard/core/spool_warmup_scheduler.py` | edit | Add 2 worker fns (mirror existing `_warmup_*_dataset_job` shape) + 2 `(prefix, fn)` tuples to flat `_WARMUP_JOBS` (~line 119). Worker fn = thin wrapper calling the per-service prewarm callable + completion log line. No enqueue/leader-lock change. |
| `src/mes_dashboard/services/resource_history_duckdb_cache.py` | edit | Expose existing prewarm body as a module-level callable (e.g. `run_prewarm_job()`) invoked by the RQ worker fn; remove `start_duckdb_prewarm()` daemon-thread spawn. Preserve fcntl `_try_lock`/`_release_lock`, `_try_reuse_existing()`, `loaded_at==today` gate. |
| `src/mes_dashboard/services/downtime_analysis_duckdb_cache.py` | edit | Same as above for downtime; expose callable, retire daemon thread. |
| `src/mes_dashboard/app.py` | edit | Delete both `start_*_prewarm()` calls at lines 834-839 (inside `if not is_testing_runtime:`). Remove now-unused imports of those symbols (AC-1 absence test inspects module attrs). |
| `src/mes_dashboard/services/resource_dataset_cache.py` | edit | Line 37 `_CACHE_TTL = int(os.getenv("RESOURCE_HISTORY_SPOOL_TTL", "72000"))`. Ensure `import os` present. |
| `src/mes_dashboard/services/downtime_analysis_cache.py` | edit | Line 37: change default from `str(CACHE_TTL_DATASET)` to `"72000"`; keep env var name `DOWNTIME_ANALYSIS_CACHE_TTL`. |
| `tests/test_app_startup.py` | create | AC-1 absence tests (AST/`importlib` attr inspection, not mock). |
| `tests/test_spool_warmup_scheduler.py` | create/extend | AC-3 membership tests; keep `test_warmup_jobs_does_not_contain_production_history` green. |
| `tests/test_resource_history_duckdb_cache.py` | extend | AC-2/AC-4/AC-5 (TTL==72000, `loaded_at==today` skip vs yesterday reload, fresh-read after refresh). |
| `tests/test_downtime_analysis_duckdb_cache.py` | extend | AC-2/AC-4 (TTL==72000, loaded_at gate). |
| `tests/test_env_contract.py` | extend | AC-4 env pin tests; assert imported constants, not just var name in contract. |
| `tests/test_rq_warmup_resilience.py` | create | AC-7 (RQ absent→Oracle fallback no crash; parquet readable past metadata-TTL expiry). |
| `tests/integration/test_preload_fork_safety.py` | edit in place | AC-1/AC-6 new enqueue tests; update (do not duplicate) daemon sentinel strings to RQ-enqueue log lines. |

## Contract Updates

- API: none.
- CSS/UI: none.
- Env: `RESOURCE_HISTORY_SPOOL_TTL` and `DOWNTIME_ANALYSIS_CACHE_TTL` rows already in `contracts/env/env-contract.md` (default 72000). No new edit; pin-test code must match these defaults.
- Data shape: none (parquet schema unchanged).
- Business logic: RH-07, RH-08, DA-07, DA-08 already written in `contracts/business/business-rules.md`. No new prose; code must satisfy them. `contracts/CHANGELOG.md` business 1.11.0 entry already present.
- CI/CD: assertions already in `contracts/ci/ci-gate-contract.md` (lines 40-45). No new gate tier/command.

## Test Execution Plan

Write failing tests before implementation (TDD order below). Run under conda env:
`conda run -n mes-dashboard pytest <path>`.

TDD order:
1. IP-7 unit tests for TTL constants + `_WARMUP_JOBS` membership + `loaded_at` gate (fast, drive IP-1/IP-5/IP-6).
2. IP-8 resilience tests (drive fallback paths in IP-2/IP-3).
3. IP-7 `tests/test_app_startup.py` absence tests (drive IP-4).
4. Implement IP-1..IP-6 to green.
5. IP-9 integration tests last (GunicornHarness; Tier 3 nightly).

| acceptance criterion | test file / command | expected signal |
|---|---|---|
| AC-1 (no daemon `start_duckdb_prewarm` in app.py) | `pytest tests/test_app_startup.py` | symbol absent via attr/AST inspection |
| AC-1 (RQ enqueued at startup, both services) | `pytest tests/integration/test_preload_fork_safety.py` (nightly) | RQ-enqueue log line present; no daemon-thread log line |
| AC-2 (`loaded_at==today` refresh gate, both) | `pytest tests/test_resource_history_duckdb_cache.py tests/test_downtime_analysis_duckdb_cache.py` | today→skip reload; yesterday→fresh load |
| AC-3 (downtime entry in `_WARMUP_JOBS`) | `pytest tests/test_spool_warmup_scheduler.py` | both new entries present; production-history guard still green |
| AC-4 (per-service TTL==72000; CACHE_TTL_DATASET==7200) | `pytest tests/test_resource_history_duckdb_cache.py tests/test_downtime_analysis_duckdb_cache.py tests/test_env_contract.py` | constants resolve to 72000; global unchanged at 7200 |
| AC-5 (fresh read after daily refresh) | `pytest tests/test_resource_history_duckdb_cache.py` | post-refresh query reads new parquet |
| AC-6 (multi-worker leader lock, one Oracle prewarm) | `pytest tests/integration/test_preload_fork_safety.py --run-integration-real` (nightly) | Oracle call count == 1 across N workers |
| AC-7 (RQ absent→fallback; parquet readable past TTL) | `pytest tests/test_rq_warmup_resilience.py` | Oracle fallback no crash; parquet still readable |
| all Tier 1 gates | per ci-gates.md Required Gates table: `ruff check .`, `npm run type-check`, `pytest tests/ -m "not integration_real"`, `cdd-kit validate`, `pytest tests/test_rq_warmup_resilience.py`, `npm run css:check` | all green |

## Handoff Constraints

- Implementation agents must not infer missing requirements from chat history.
- Do not re-copy full design, test strategy, CI policy, or contract prose into this plan; follow the source pointers above.
- TTL constants are module-level (frozen at import): override tests MUST use `monkeypatch.setattr` on the module constant, never `setenv` (CLAUDE.md Test Coverage Discipline; design.md D4).
- AC-1 absence test must inspect module attributes / AST, not mock — a mock cannot detect a removed symbol (test-plan.md §Notes).
- GunicornHarness env isolation: pop `FLASK_ENV`/`FLASK_TESTING`/`PYTEST_CURRENT_TEST`, set `REDIS_ENABLED=true` (conftest pattern; CLAUDE.md GunicornHarness notes). Sentinel asserts on the RQ-enqueue "background thread started"-style line, not "prewarm complete".
- `_WARMUP_JOBS` change must be additive; do not alter the existing reject/yield_alert/hold/resource_dataset tuples or the enqueue/leader-lock loop (design.md D2).
- `CACHE_TTL_DATASET` in `config/constants.py` must remain 7200 — do not edit it.
- If this plan omits a required file, behavior, contract, or test, stop and report `blocked`.
- Keep implementation within the file-level plan unless a Context Expansion Request is approved.

## Known Risks

- R1 (medium): no RQ warmup worker in an environment → daily refresh never runs; all queries serve Oracle until a worker appears. Mitigation: deploy runbook must assert a warmup worker is up; resilience tests cover no-crash fallback (design.md R1).
- R2 (low): daily refresh drifting >20h after prior load leaves a metadata-expired / DuckDB-not-yet-refreshed gap forcing an Oracle rebuild — accepted; Tier-3 nightly soak boundary only (design.md R2; test-plan §Out of Scope).
- R3 (low): two lock layers (Redis leader lock + per-service fcntl) — misconfig could re-introduce duplicate Oracle prewarms; pinned by AC-6 multi-worker integration test (design.md R3).
- CER-001 in context-manifest is `pending` (exact per-service cache test filenames). The test-plan now names them explicitly (`tests/test_resource_history_duckdb_cache.py`, `tests/test_downtime_analysis_duckdb_cache.py`); if those files do not exist at implementation time, backend-engineer creates them under the already-allowed `tests/` paths — no expansion blocker.
