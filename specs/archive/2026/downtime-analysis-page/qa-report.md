---
change-id: downtime-analysis-page
schema-version: 0.1.0
last-changed: 2026-05-29
---

# QA Report: downtime-analysis-page

## Gate Results

| gate | command | result | notes |
|---|---|---|---|
| lint | `ruff check` (downtime files) | **PASS** | exit 0 |
| contract-validate | `cdd-kit validate` | **PASS** | all validations passed |
| unit-mock-integration | `pytest test_downtime_analysis_service.py test_downtime_analysis_routes.py test_api_contract.py test_modernization_policy_hardening.py` | **PASS** | 150 passed |
| frontend-unit | `npm run test -- --run` | **PASS** | 486 passed, 1 pre-existing fail (api-dedup.test.js), 1 skipped |
| css-governance | `npm run css:check` | **PASS** | 0 errors, 0 unscoped feature rules |
| frontend-type-check | `npm run type-check` | **PASS (informational)** | 0 errors |
| cdd-kit gate | `cdd-kit gate downtime-analysis-page` | **PASS** | all validators passed |
| playwright-downtime-analysis | not run locally | pending CI | requires live server |
| e2e-backend | not run locally | pending CI | requires Oracle/Redis |

## Acceptance Criteria Coverage

| AC | description | test | result |
|---|---|---|---|
| AC-1 | NST excluded; UDT/SDT/EGT buckets from SHIFT.HOURS | `TestE10StatusFilter` + `TestDowntimeSummaryShape` | PASS |
| AC-2 | 8-bucket big-category taxonomy; deterministic per DA-04 | `TestBigCategoryMapping` + `TestBigCategoryShape` | PASS |
| AC-3 | top-reasons ordered by hours desc; event_count + avg_min present | `TestDowntimeTopReasonsShape` + `TestTopReasonsRoute` | PASS |
| AC-4 | 3-fragment cross-shift event → 1 merged row; hours summed; fragment_count tracked | `TestCrossShiftMerge` | PASS |
| AC-5 | event detail: match_source enum; JOB null when no match; Path A/B working | `TestJobidBridge` + `TestEventDetailShape` + `TestJobEnrichmentShape` | PASS |
| AC-6 | filter dropdowns cross-narrow; equipment dropdown excludes self | `TestFilterCrossNarrowing` + `TestFilterKwargsForwarding` + `TestEquipmentDetailRoute` | PASS |
| AC-7 | page_status.json entry (drawer-2); css:check Rule 6 pass; portal lazy-load | `TestDowntimeAnalysisPage` (3 asserts) + css:check + npm run build | PASS |
| AC-8 | DOWNTIME_BRIDGE_VERSION bump produces different spool key; resource_dataset_* unchanged | `TestBridgeVersionCacheKey` | PASS |

## Known Risk: JOBID Coverage Gap

**Approved-with-risk.** Approximately 50% of UDT events and 14% of SDT events lack a direct JOBID in `DW_MES_RESOURCESTATUS_SHIFT` (data gap since 2025-09). The JOBID-primary + RESOURCEID+time-overlap fallback bridge (DA-03) handles this; events with no JOB match are still surfaced with `match_source='none'` and JOB columns rendered as `—`. IT JOBID backfill runbook documented in `ci-gates.md §Rollback Policy`: when IT confirms backfill, bump `DOWNTIME_BRIDGE_VERSION` constant in `constants.py` → deploy → optional parquet purge.

## Issues Found and Resolved During Review

| issue | severity | found by | resolved |
|---|---|---|---|
| `granularity` param silently ignored (always returned daily) | blocking | contract-reviewer | fixed: returns 400 for non-'day' values; api-contract updated |
| CHANGELOG entries duplicated in individual contract files | blocking | contract-reviewer | fixed: removed from api-contract.md, business-rules.md, data-shape-contract.md; canonical entries in CHANGELOG.md remain |
| FilterBar missing 4 dimension filter controls | blocking | ui-ux-reviewer | fixed: added workcenter/family/resource/status_type MultiSelects |
| Date inputs fired premature queries on each keypress | blocking | ui-ux-reviewer | fixed: date inputs only update draft state; query fires on submit only |
| `start_ts`/`end_ts` could be null despite `nullable=no` contract | non-blocking | contract-reviewer | fixed: `or ''` default added in `_build_event_detail_page` |
| Contract schema-versions not bumped after body edits | blocking | qa-reviewer (gate) | fixed: api 1.13.1, data 1.12.1, business 1.12.1; CHANGELOG updated |

## Pre-existing Test Failures

| test | module | reason |
|---|---|---|
| `api-dedup.test.js` | frontend | POST dedup intentionally removed in commit `c27a9f9`; predates this change; unrelated |

## Verdict

**MERGE READY** — all local Tier 0/1 gates pass. Pending CI-only gates (playwright-downtime-analysis, e2e-backend) will run on PR. No open blocking issues.
