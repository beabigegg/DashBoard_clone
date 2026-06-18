# Archive — eap-alarm-analysis

> Cold Data Warning: This archive is historical evidence. Current requirements live in contracts/ and active project guidance.

---

## Change Summary

Added a new EAP ALARM Analysis report page to the MES Dashboard. The feature introduces a full async spool pipeline: an RQ worker fetches ALARM_TEXT/ALARM_START/ALARM_END pairs from Oracle (SECS/GEM SET→CLEAR pairing via ALCD < 0 convention), stores them as a versioned Parquet file (_SCHEMA_VERSION = 2), and serves DuckDB-computed views (summary cards, Pareto top-50, trend by ALARM_TEXT top-10, paginated detail table) through a fine-filter composable with snapshot-diff _lastCommitted re-sync. The feature is always-async with no synchronous Oracle fallback.

---

## Final Behavior

- `/eap-alarm` SPA available from the new "EAP" top-level nav category in portal-shell.
- Coarse filter (date range + machine list) submits a job to the `eap-alarm-query` RQ queue.
- Worker builds a Parquet spool from Oracle; frontend polls `/api/spool/status` and transitions on completion.
- Fine filter (alarm text ILIKE, equipment ID exact) drives DuckDB views without re-querying Oracle.
- Summary cards: total alarm count, affected equipment count, unresolved count, avg duration (minutes).
- Pareto chart: top-50 alarm texts by occurrence count with cumulative percentage.
- Trend chart: stacked bar by top-10 ALARM_TEXT, bucketed by day (switchable to hour granularity).
- Detail table: paginated (50/page, max 200), ALARM_START descending, with detail_params row expansion.
- AlarmCategory codes (0–7, 64) decoded to Chinese labels via `decode_alarm_category` in `eap_alarm_cache.py`.

---

## Final Contracts Updated

- `contracts/api/api-contract.md` — EAP ALARM endpoints (§EAP ALARM, rows EA-01/03/05/06/07): submit query, status poll, summary, pareto, trend, detail, filter-options
- `contracts/env/env-contract.md` — EAP_ALARM_* env vars: `EAP_ALARM_WORKER_QUEUE`, `EAP_ALARM_JOB_TIMEOUT_SECONDS`, `EAP_ALARM_SPOOL_TTL`, `EAP_ALARM_SPOOL_DIR`
- `contracts/business/business-rules.md` — EA-05 AlarmCategory decode table; EA-ALCD SECS/GEM convention (ALCD < 0 = SET, ≥ 0 = CLEAR)
- `contracts/ci/ci-gate-contract.md §1.3.25` — Playwright eap-alarm.spec.js registered in playwright-critical-journeys gate
- `contracts/api/openapi.json` — regenerated to include EAP ALARM endpoints

---

## Final Tests Added / Updated

Backend (all in `tests/test_eap_alarm_service.py`):
- `TestSpoolKeyComposition` — 6 tests: EA-01 determinism, format, hash, schema version in key
- `TestMissingDateRangeRaisesValueError` — 6 tests: EA-03 mandatory date filter guard
- `TestMachinesValidation` — 5 tests: empty/None/invalid machines → ValueError
- `TestAlarmCategoryDecode` — 9 tests: EA-05 all known codes, unknown, None, string/float coercion
- `TestSchemaVersionIsPinned` — 2 tests: EA-06 _SCHEMA_VERSION == 2

Other backend tests added:
- `tests/test_spool_routes.py::test_eap_alarm_in_allowed_namespaces`
- `tests/integration/test_eap_alarm_rq_async.py` (pytestmark=integration_real, nightly)
- `tests/integration/test_eap_alarm_resilience.py` (pytestmark=integration)
- `tests/integration/test_eap_alarm_data_boundary.py` (pytestmark=integration)
- `tests/test_rq_monitor_service.py` — updated queue count 9→10

Frontend tests:
- `frontend/tests/unit/eap-alarm-filter.test.js` — 13 unit tests for useEapAlarmFilter composable (snapshot-diff _lastCommitted re-sync, buildFineFilterParams, setQueryId)
- `frontend/tests/playwright/eap-alarm.spec.js` — 5 Playwright critical-journey tests

---

## Final CI/CD Gates

All gates run within existing workflows:
- **unit-mock-integration** (Tier 1, required): `pytest … tests/test_eap_alarm_service.py`
- **frontend-unit** (Tier 1, required): `cd frontend && npm run test`
- **css-governance** (Tier 1, required): `cd frontend && npm run css:check`
- **response-shape-validate** (Tier 1, required): `cdd-kit validate --contracts`
- **playwright-critical-journeys** (Tier 1, required): includes `tests/playwright/eap-alarm.spec.js`
- **playwright-resilience** / **playwright-data-boundary** (Tier 1, required)
- **nightly-integration** (Tier 3): `tests/integration/test_eap_alarm_rq_async.py`
- **visual-regression** (Tier 2, informational — not yet wired to screenshot tooling)

---

## Production Reality Findings

- **Trend chart series key bug**: Initial implementation used `eqp_type` as the series key; `get_trend()` was rewritten mid-session to group by `ALARM_TEXT` (top-10) instead, matching the contract intent. Series key corrected to `alarm_text`.
- **AlarmCode display bug**: ALARM_TEXT was rendering numeric ALCD code ("6075") instead of the alarm description text because the wrong column was selected. Fixed by reading ALARM_TEXT from the correct Oracle column.
- **Summary cards zero-values**: SummaryCards showed 0 due to per-endpoint staleness counters racing in the Vue composable `fetchAllViews`. Fixed with per-endpoint counter dict in `useEapAlarmViews.js`.
- **CI failures on push**: Three separate failures: (1) `eap-alarm-filter.test.js` tested removed fields (`alarm_category`, `eqp_types`); (2) `contract-driven-gates` lacked `pip install jsonschema` and used `cdd-kit validate` without `--contracts`; (3) `decode_alarm_category` was removed from `eap_alarm_cache.py` and needed restoration, plus schema version pin bumped 1→2.
- **SECS/GEM ALCD convention**: Oracle EAP tables use negative ALCD for SET events, non-negative for CLEAR. Worker explicitly filters `ALCD < 0` for SET and joins CLEAR via `RESOURCEID + ALARMID + timestamp window`. This is the correct domain model; the documentation was absent before this change.

---

## Lessons Promoted to Standards

1. **EA-ALCD row** — promoted to `contracts/business/business-rules.md` §EAP ALARM Rules table. Row was claimed in CHANGELOG 1.22.0 but missing from the table body; inserted as an in-place correction (no version bump).
   - Rule: `ALCD < 0` = SET event; `ALCD >= 0` = CLEAR. Full-table scans without EA-03 predicate forbidden.
   - Evidence: archive.md §Production Reality Findings; `agent-log/backend-engineer.yml` known-risks.

2. **Multi-View Staleness Counter pattern** — promoted to `docs/architecture/frontend-patterns.md` §Multi-View Staleness Counters (new section) with full code example. One-line pointer added to `CLAUDE.md` §Frontend patterns.
   - Rule: `fetchAllViews()` fan-out must use a per-endpoint dict, not a shared counter.
   - Evidence: archive.md §Production Reality Findings ("Summary cards zero-values"); `agent-log/frontend-engineer.yml`.

Not promoted (already documented):
- Parquet `_SCHEMA_VERSION` in spool key → already in `docs/architecture/cache-spool-patterns.md` and `CLAUDE.md:132`
- `spool_routes._ALLOWED_NAMESPACES` + parametrized test in same PR → already in `docs/architecture/cache-spool-patterns.md` and `CLAUDE.md:141`
- Playwright `pageRendered` guard `.theme-<name>` → already in `docs/architecture/ci-workflow.md` and `CLAUDE.md:186`
- `pip install jsonschema` before `cdd-kit validate --contracts` → already in `CLAUDE.md:111`

---

## Follow-up Work

- **DETAIL_PARAMS second Oracle query** (medium risk): fetches non-primary EAV params in a second query per job; if EAP tables are very large this doubles Oracle load — profiled only after first production spool.
- **visual-regression gate** (informational, not wired): needs screenshot tooling to be promoted to required per ci-gate-contract.md Informational Gate Promotion Policy (20 days / 60 runs).
- **nightly integration tests**: `test_eap_alarm_rq_async.py` requires a live Oracle connection; AC-4/6/7 deferred to nightly per test-layer governance.
- **IP-16** `test_navigation_contract.py` EAP top-level category assertion — carried over from backend-engineer to frontend-engineer; confirmed added.
