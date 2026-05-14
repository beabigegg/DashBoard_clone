---
change-id: prod-history-first-tier-cache-filters
schema-version: 0.1.0
last-changed: 2026-05-14
risk: high
tier: 1
---

# QA Report — prod-history-first-tier-cache-filters

## Verdict

**approved-with-conditions** — All AC-1..AC-8 covered by automated tests; all
12 required agents ran and produced verdicts (pass / approved / approved-with-
changes already remedied). Two conditions remain for the release captain:
empirical staging measurements for AC-1 p95 latency and AC-6 multi-worker lock,
captured below under "Manual Gate Evidence Required Before Close".

## AC Compliance Matrix

| AC | status | evidence |
|---|---|---|
| AC-1 (empty selection → full distinct sets, no Oracle) | covered | unit: `tests/test_container_filter_cache.py` (v2 4-tuple round-trip, new) + route: `tests/test_production_history_routes.py` filter-options empty-selection test (backend-engineer log §test-files; routes/+5 tests) |
| AC-2 (selection narrows other 3 fields, symmetric) | covered | unit + property: `tests/test_container_filter_cache.py::cross_filter_narrow_by_package`, `tests/property/test_cross_filter.py` (50 param + 2 Hypothesis — monkey-test-engineer.yml §test-counts) |
| AC-3 (main query accepts 6 new params, back-compat Type-only) | covered | `tests/test_production_history_service.py` (+7 tests including back-compat type-only); E2E `production-history-multi-line-input.spec.ts` empty-wildcard omission test |
| AC-4 (wildcard meta-char rejection, parameter-bound LIKE) | covered | parser: `tests/test_common_filters.py` (+9 tests); SQL-runtime: `test_production_history_sql_runtime.py::TestExtraFiltersWildcardEmit`; route fuzz: 18 meta + 87 control char cases (monkey-test-engineer §test-counts → 214 new fuzz cases) |
| AC-5 (multi-line parse idempotent) | covered | property: `tests/property/test_wildcard_parser.py` (3 Hypothesis properties); legacy frontend `production-history.test.js` (7 new tests incl. idempotence) |
| AC-6 (multi-worker lock, exactly-one rebuild) | covered (mock); pending (real) | mock: `tests/integration/test_multi_worker_concurrency.py::test_container_filter_cache_lock_under_4_workers` + `test_lock_holder_crash_releases_lock` (e2e-resilience-engineer.yml — both PASS under `--run-integration-real`); nightly real-Oracle scheduled |
| AC-7 (4 MultiSelects + 3 textareas; 2nd-tier chip suppression) | covered | Playwright `production-history-cross-filter.spec.ts` (3 tests with 9 stable testids — e2e-resilience-engineer §files-touched) |
| AC-8 (schema_version mismatch → rebuild) | covered | `tests/test_container_filter_cache.py::test_schema_version_mismatch_triggers_rebuild` + `test_stale_schema_v1_payload_ignored` (backend-engineer §test-files) |

## Test Coverage Summary

| layer | count | result | tier |
|---|---|---|---|
| unit-mock-integration (backend full sweep) | 3470 (28 new) | pass, 0 failed, 131 skipped | 1 |
| route fuzz (test_fuzz_routes.py + property/) | 372 (214 new) | pass | 1 |
| property (wildcard parser + cross-filter) | 55 (3 + 52 new) | pass | 1 |
| frontend vitest | 316 (4 new shape + 7 parser + 3 url) | pass | 1 |
| legacy node --test | 251 (7 new composable + 11 pre-existing) | pass | 1 |
| Playwright specs (new) | 5 specs / 10 tests | discoverable; pending live server in CI | 1 |
| integration (multi-worker + Redis chaos/timeout) | 3 new + 1 lock-crash | pass under `--run-integration-real` | 1 mock / 3 real-Oracle |
| build / css:check / type-check | — | pass (0 errors) | 0/2 |

## Open Items Resolution

- **U1 — env var for max-patterns** — Resolved by contract-reviewer: hard-coded
  constant (100/field) in v1; no env contract entry. Future-tunable noted.
- **U2 — shared wildcard emitter** — Backend-engineer chose `lift-to-shared`:
  new `src/mes_dashboard/sql/wildcards.py`. Single audit chokepoint;
  material-trace migration deferred (see Recommendations).
- **U3 — Oracle hostile sequences (q'[...], ||, DBMS_*)** — Cleared by
  dependency-security-reviewer: q'[...] and /*…*/ caught by meta regex; || and
  identifier-shaped sequences are bound-only via oracledb named bind and cannot
  escape the LIKE/IN string context. Pin test
  `test_wildcard_oracle_hostile_concat_passes_as_literal` documents behaviour.
- **U4 — stale-sentinel reaper** — Deferred. Matches `resource-history-perf`
  precedent; runbook documents manual `rm` for crashed-mid-rebuild scenario.
- **Non-blocking deferrals:**
  - VR-04 hint contrast (text-gray-500 → 600) — informational, WCAG passes today.
  - VR-05 per-picker loading indicator — current behaviour matches material-trace.
  - VR-06 option-count indicator on MultiSelect — shared-ui enhancement, future.
  - R1 per-token length cap (10 KB single token currently accepts) — pinned by
    `test_main_query_oversized_wildcard_input_single_huge_token_accepted` so a
    future cap deliberately breaks the test and forces a contract update.
  - `material_trace_service` migration to shared `sql/wildcards.py` — follow-up.
  - Frontend i18n locales — app surface has no `useI18n()` adoption; no rule
    triggered today, backlog for project-wide adoption.

## Risk Assessment

| risk | severity | mitigation |
|---|---|---|
| Infix wildcard `*A*` patterns may bypass Oracle indexes under heavy production load | medium | Per D5, 2-char anchor + chunked TRACKINTIMESTAMP window bounds scope; monitor staging; ROWNUM cap reserved for v1.5 |
| 10 KB single-token acceptance creates 10 KB Oracle LIKE pattern (R1 known gap) | low | MAX_JSON_BODY_BYTES (262 KB) bounds aggregate; MES tokens are < 30 chars in practice; pinned by fuzz test |
| Stale `tmp/container_filter_cache.loading` after worker crash mid-rebuild | low | Documented in runbook (`rm` step); D4 fall-through to direct Oracle in degraded mode covered by `test_lock_holder_crash_releases_lock` |
| Playwright specs not yet executed against live Flask + Redis | medium | Specs are discoverable and syntactically valid; CI must bring up gunicorn + redis-server before merge |
| `material_trace_service` still uses older inline pattern (no PHF-06 meta rejection) | low | Out of scope for this change; tracked as security follow-up (R3 / MATERIAL-TRACE-MIGRATION-FOLLOWUP) |

## Manual Gate Evidence Required Before Close

- **AC-1 — filter-options p95 latency (warm cache):** target ≤ 100 ms warm.
  Needs live measurement against staging (4 gunicorn workers, Redis up). Unit
  + mock proves correctness; this confirms SLA.
- **AC-6 — multi-worker lock under 4 gunicorn workers in staging:** confirm
  exactly one Oracle round-trip across the worker pool at startup. Mock harness
  + 4-subprocess integration test proves the algorithm; staging confirms env.
- **Spool/cache parity — empty cache cold-start < 60 s:** boot with empty Redis
  on staging and time the rebuild to completion across all 4 workers.
- **(optional)** 1000-LOT pasted query end-to-end latency at the wildcard
  textarea — stress thundering-herd is covered, but a real Oracle 1000-LOT IN
  list query is a useful production-shape probe.

## Recommendations

1. Add a **schema_version 2 → 3 rollback drill** to the next deploy runbook so
   the schema-version primitive is exercised at least once in staging before
   relying on it in production.
2. Track **10 KB single-token acceptance (R1)** as documented behaviour; flip
   `test_main_query_oversized_wildcard_input_single_huge_token_accepted` to
   the 400-cap form when a per-token length cap lands.
3. File a **follow-up ticket: `material_trace_service` → shared
   `sql/wildcards.py`** to consolidate the audit chokepoint and pick up PHF-06
   meta-char rejection across all wildcard-accepting surfaces.
4. Once a project-wide i18n adoption begins, **backfill production-history
   locales** alongside hold-history, reject-history, etc.
