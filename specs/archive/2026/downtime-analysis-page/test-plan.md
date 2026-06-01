---
change-id: downtime-analysis-page
schema-version: 0.1.0
last-changed: 2026-05-29
risk: medium
tier: 1
---

# Test Plan: downtime-analysis-page

## Acceptance Criteria → Test Mapping

| criterion id | description | test family | test file path | tier | Oracle path | snapshot/cache path |
|---|---|---|---|---|---|---|
| AC-1 | summary endpoint returns UDT/SDT/EGT hours buckets; NST excluded | unit + contract | `tests/test_downtime_analysis_service.py::TestE10StatusFilter` / `tests/test_api_contract.py::TestDowntimeSummaryShape` | 0/1 | yes | yes |
| AC-2 | big-category returns 8 buckets with deterministic mapping (DA-04) | unit | `tests/test_downtime_analysis_service.py::TestBigCategoryMapping` | 0 | yes | yes |
| AC-3 | top-reasons ordered by hours desc, includes event_count + avg_duration | contract | `tests/test_api_contract.py::TestDowntimeTopReasonsShape` | 1 | yes | n/a |
| AC-4 | cross-shift event merge: 3 fragments → 1 row, hours summed, fragment_count correct (DA-02) | unit | `tests/test_downtime_analysis_service.py::TestCrossShiftMerge` | 0 | yes | n/a |
| AC-5 | event detail: match_source enum, JOB null when no match, Path A (JOBID), Path B (overlap) (DA-03, DA-05) | unit | `tests/test_downtime_analysis_service.py::TestJobidBridge` | 0 | yes | n/a |
| AC-6 | filter dropdowns cross-narrow; equipment excludes self (narrow reason/category but not equipment) | unit | `tests/test_downtime_analysis_service.py::TestFilterCrossNarrowing` | 0 | yes | yes |
| AC-7 | page_status.json entry; CSS passes css:check Rule 6; portal lazy-load; theme scoped | integration + visual | `tests/test_modernization_policy_hardening.py::TestDowntimeAnalysisPage` / `frontend/src/downtime-analysis/__tests__/css-scope.test.ts` | 1 | n/a | n/a |
| AC-8 | DOWNTIME_BRIDGE_VERSION bump invalidates spool without purging resource_dataset_* | unit + resilience | `tests/test_downtime_analysis_service.py::TestBridgeVersionCacheKey` | 0/1 | n/a | yes |

## Test Families Required

| family | tier | notes |
|---|---|---|
| unit | 0 | DA-01..DA-06 logic, big-category map, merge key, bridge paths, filter kwargs, wait/repair hours |
| contract | 1 | §3.12.1–3.12.7 shapes vs live response; match_source closed enum; null-sentinel; API envelope §1.1 |
| integration | 1 | route → service → SQL runtime; snapshot path AND Oracle fallback BOTH covered per kwarg |
| e2e | 1 | overview loads, detail loads, filter cross-narrow, match_source='none' row renders "—", view toggle state |
| data-boundary | 0 | Oracle CHAR trailing-space on OLDREASONNAME; null JOBID; null FIRSTCLOCKONDATE; midnight-UTC DATE |
| resilience | 1 | Oracle timeout → spool fallback; Redis-down → spool; multi-worker startup lock; spool rebuild on version bump |
| visual | manual | .theme-downtime-analysis scope; Teleport wrappers carry theme class (css-contract rule 4.4) |
| stress | nightly | register only; not pre-merge gate |
| soak | weekly | register only; not pre-merge gate |

## Test File Index

**`tests/test_downtime_analysis_service.py`**
- `TestE10StatusFilter` — NST rows excluded, UDT/SDT/EGT included, HOURS is authoritative
- `TestCrossShiftMerge` — 3-fragment merge → 1 row; gap >60s stays as 2 rows; fragment_count; cross-resource isolation
- `TestJobidBridge` — Path A direct JOBID; Path B single overlap; Path B multi-overlap tiebreak determinism; Path B no-match → match_source='none', all JOB fields null; match_ambiguous ≥80% threshold
- `TestBigCategoryMapping` — each of 8 buckets maps at least one OLDREASONNAME; TMTT_ prefix; CHAR-stripped lookup; fallback to 其他/未分類; EGT always maps to 工程
- `TestWaitRepairHours` — wait_hours formula; repair_hours formula; both null when match_source='none'; null FIRSTCLOCKONDATE → null wait
- `TestFilterCrossNarrowing` — equipment=X narrows reason options; equipment dropdown excludes self-narrowing; CSV multi-value union; pairwise AND intersection
- `TestFilterKwargsForwarding` — every route kwarg forwarded via call_args.kwargs[key] with non-default value (NOT assert_called_once_with whitelist)
- `TestBridgeVersionCacheKey` — spool key includes DOWNTIME_BRIDGE_VERSION; bumping version produces different key; resource_dataset_* keys unchanged

**`tests/test_downtime_analysis_routes.py`**
- `TestSummaryRoute` — per-kwarg forwarding (workcenter, resource, start_date, end_date, status_type)
- `TestBigCategoryRoute` — per-kwarg forwarding; 404 on unknown resource
- `TestTopReasonsRoute` — top_n param honoured; default top_n=10
- `TestEquipmentDetailRoute` — per-kwarg forwarding; snapshot + Oracle paths
- `TestEventDetailRoute` — per-kwarg forwarding; match_source propagated

**`tests/test_api_contract.py`** (new entries only)
- `TestDowntimeSummaryShape` — DowntimeKpiShape §3.12.1 fields present and typed
- `TestDailyTrendShape` — DailyTrendRow §3.12.2
- `TestBigCategoryShape` — BigCategoryRow §3.12.3
- `TestTopReasonsShape` — TopReasonRow §3.12.4
- `TestEquipmentDetailShape` — EquipmentDetailRow §3.12.5; match_source closed enum
- `TestEventDetailShape` — EventDetailRow §3.12.6; job sub-object null when match_source='none'
- `TestJobEnrichmentShape` — JobEnrichment §3.12.7; wait_hours/repair_hours null contract

**`tests/test_modernization_policy_hardening.py`** (new entries only)
- `test_page_status_contains_downtime_analysis_in_drawer_2` — drawer_id='drawer-2', route='/downtime-analysis'
- `test_asset_readiness_manifest_contains_downtime_analysis` — entry present, asset path resolves
- `test_route_scope_matrix_contains_downtime_analysis` — entry present

**`tests/e2e/test_downtime_analysis_e2e.py`**
- `test_summary_endpoint_integration` — real spool write/read cycle with fixture Oracle rows
- `test_event_detail_match_source_none_rows_present` — no-match events are included, not dropped

**`frontend/tests/playwright/downtime-analysis.spec.js`**
- overview chart renders, KPI cards visible
- filter selection cross-narrows reason dropdown
- event detail row with match_source='none' shows — in all JOB columns
- view toggle (chart ↔ table) preserves filter state
- Teleport tooltip carries .theme-downtime-analysis wrapper

**`frontend/src/downtime-analysis/__tests__/`**
- `formatDowntimeDate.test.ts` — midnight-UTC DATE passthrough (year/month/day extracted from string, no Date() call); non-midnight calls new Date() normally
- `useBigCategory.test.ts` — 8 buckets rendered; unknown category falls back to 其他/未分類
- `useFilterState.test.ts` — filter state initialises empty; cross-narrow callback invoked on selection change

## Fixture Discipline Requirements

**DA-02 cross-shift merge fixtures (must NOT use uniform HOURS values)**
- 3-fragment fixture: R-001, UDT, EE Repair, fragments (1.5h + 12h + 0.5h). Post-merge: 1 row, hours=14.0, fragment_count=3, event_start=18:00, event_end=08:00.
- Gap >60s fixture: same resource/reason/day, gap=120s between fragment_1.LASTSTATUSCHANGEDATE and fragment_2.OLDLASTSTATUSCHANGEDATE. Post-merge: 2 distinct rows.
- Cross-resource isolation: identical key except HISTORYID — must remain 2 separate events.

**DA-03 JOBID bridge fixtures**
- Path A: SHIFT row with JOBID='J001'; JOB row JOBID='J001'. Assert match_source='jobid', symptom non-null.
- Path B no-match: SHIFT JOBID=null, no overlapping JOB rows. Assert match_source='none', all job fields null (not omitted).
- Path B single overlap: one overlapping JOB. Assert match_source='overlap'.
- Path B multi-overlap tiebreak: two JOB rows with different overlap fractions. Assert winner is the larger-overlap row; when overlaps equal, earlier CREATEDATE wins; final tiebreak by JOBID ASC.
- match_ambiguous threshold: non-winner overlap ≥80% of winner → match_ambiguous=true in response.

**Oracle CHAR trailing-space**
- OLDREASONNAME='EE Repair   ' (8 trailing spaces). Assert category='維修' (not '其他/未分類').
- OLDREASONNAME='TMTT_Check  ' (CHAR-padded). Assert strip() before startswith; category='檢查'.

**Filter forwarding discipline (per CLAUDE.md rule)**
- Every test that asserts route-to-service forwarding supplies a non-default value (e.g., `resource_id='R-42'`, `status_type='SDT'`).
- Assert via `mock_service.call_args.kwargs['resource_id'] == 'R-42'`, never `assert_called_once_with(...)` whitelist.
- Snapshot path AND Oracle fallback path both exercised for every kwarg (two separate test methods per kwarg group).

## Out of Scope

- TBD落差分析 (KEY IN / 切換不確實) — marked TBD in change-request; no tests authored here.
- Existing resource-history regression tests — additive change; resource_dataset_* namespace unaffected.
- JOBID backfill operational runbook steps — covered by ci-gates.md §Rollback Policy, not test coverage.
- Stress and soak gates — registered in nightly/weekly registry only (tasks.yml task 6.4 = skipped per change-classification.md).
- Monkey/fuzz tests — change-classification.md explicitly excludes these.

## Notes

- Filter-kwarg forwarding tests follow the per-kwarg style from CLAUDE.md "Test Coverage Discipline" — no `assert_called_once_with` whitelists.
- DA-03 tiebreak must be deterministic across Python dict iteration order; use explicit sorted() in service, assert same winner on two runs.
- Midnight-UTC DATE formatter test mirrors `material-consumption/components/DetailTable.vue::formatTxnDate` pattern.
- `test_modernization_policy_hardening.py` assertions must hard-code `drawer_id='drawer-2'`; if drawer changes post-design, rename the method.
- CSS visual review is manual tier (visual-review-report.md); no automated snapshot comparison required pre-merge.
