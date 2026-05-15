# Archive: prod-history-detail-partial-merge

change-id: prod-history-detail-partial-merge
tier: 2
closed-date: 2026-05-15
status: complete

## Change Summary

Re-introduce partial-trackout aggregation in the production-history detail
table, replacing the raw-row view from `prod-history-detail-raw-rows`. Rows
sharing the same `(CONTAINERNAME, SPECNAME, EQUIPMENTID, TRACKINTIMESTAMP)`
4-tuple are merged: `MAX(TRACKOUTTIMESTAMP)`, `SUM(TRACKOUTQTY)`,
`MAX(TRACKINQTY)`, `COUNT(*) AS partial_count`. Lots whose intra-lot order
interleaves with a different lot on the same machine (different
`TRACKINTIMESTAMP`) are NOT merged, preserving A→B→A diagnostic history.
A strict guard (`HAVING COUNT(DISTINCT col)=1` over remaining attributes)
falls back to raw rows when a non-key column diverges within a group.

## Final Behavior

- API: `GET /production-history/detail` returns aggregated rows with new
  `partial_count` integer field (≥1). `pagination.total_rows` reflects the
  post-aggregation count.
- CSV export: appends new `PartialCount` column after `TrackOutQty`.
- Frontend: production-history detail table renders an inline badge
  `×N 合併` (gray pill, aria-label `此列合併了 N 筆 partial trackout`) only
  when `partial_count > 1`.
- DuckDB path and pandas fallback path produce identical output; both share
  the 4-tuple GROUP BY + strict-guard semantics.
- INFO log emitted once per page query when any group has `partial_count>1`,
  reporting total raw rows and merged groups (not per-group).

## Final Contracts Updated

- `contracts/business/business-rules.md` 1.5.0 → 1.6.0 → 1.6.1
  - Added PH-06 (4-tuple aggregation; `TRACKINQTY = MAX(TRACKINQTY)`)
  - Added PH-07 (strict guard for non-key column divergence)
  - Amended PH-01 (cross-reference PH-06), PH-04 (sort key)
  - Added 2 decision-table rows
- `contracts/api/api-contract.md` 1.4.0 → 1.5.0 → 1.5.1
  - §10 compatibility note for 2026-05-15 partial-trackout aggregation
    (additive `partial_count` + `PartialCount` CSV column + `total_rows`
    post-aggregation semantics)
- `contracts/data/data-shape-contract.md` 1.3.0 → 1.4.0 → 1.4.1
  - §3.4 added `partial_count` column; row-grain rewritten; TRACKINTIMESTAMP
    is the sole group key; TRACKINQTY documented as `MAX` of group
- `contracts/CHANGELOG.md`: 6 new entries (1.6.0/1.5.0/1.4.0 + same-day
  patch entries 1.6.1/1.5.1/1.4.1 for the 5→4-tuple correction)

## Final Tests Added / Updated

- `tests/test_production_history_sql_runtime.py` — new `TestPartialMergeAggregation`
  class (10 tests), including:
  - `test_compute_detail_page_succeeds_with_non_empty_filter` (regression
    for double-WHERE SQL parser bug)
  - `test_partial_merge_same_trackin_time_different_trackin_qty` (regression
    using real lot `GA26041607-A00-005` values 99424→26624 to prove the
    4-tuple key correctly merges what 5-tuple would have split)
- `tests/test_production_history_service.py` — new `TestPandasFallbackAggregation`
  class (6 tests, mirrors DuckDB path)
- `tests/test_api_contract.py` — new `TestProductionHistoryPartialMergeContract`
  class (2 tests for `partial_count` schema + pagination semantics)
- `frontend/tests/components/ProductionDetailTable.test.js` — NEW file
  (3 Vitest cases for badge visibility/aria-label/text)
- `frontend/tests/legacy/production-history.test.js` — extended with 5
  `node:test` cases

Verified locally: pytest prod-history sweep 98/98 pass; vitest 32 files /
340 tests pass; vue-tsc clean; css:check pass; cdd-kit gate ✓.

## Final CI/CD Gates

Per `ci-gates.md` (no new workflow files; existing gates exercise new tests):

| gate | tier | required |
|---|---:|---:|
| lint (`ruff check .`) | 0 | yes |
| cdd-kit-validate | 0 | yes |
| unit-mock-integration (pytest) | 1 | yes |
| frontend-unit (vitest) | 1 | yes |
| css-governance (`npm run css:check`) | 1 | yes |
| playwright-critical-journeys | 1 | yes |
| frontend-type-check (`vue-tsc`) | 1 | informational |
| visual-regression | 2 | informational |

Promotion: merge to main → auto-deploy staging → manual smoke (verify
badge appears on multi-partial lot + aggregated row count < raw count
for known range + CSV `PartialCount` column populated) → production.

Rollback: pure view-layer; revert PR; no parquet cleanup needed (spool
schema unchanged); no Redis flush needed (cache namespace unchanged).

CI run on commit `49f5e48`: backend-tests ✓, frontend-tests ✓,
released-pages-hardening-gates ✓.

## Production Reality Findings

Two production-reality defects were caught during the implementation
window (not in tests, because both depended on inputs the fixtures did
not cover):

1. **Double-WHERE SQL parser error** — `compute_detail_page` failed with
   `Parser Error: syntax error at or near "WHERE"` whenever any non-empty
   filter was applied. The raw-CTE branch already had
   `WHERE (key-tuple) IN (...)`, then the user filter was appended as a
   second `WHERE`. Fix: convert the second clause to `" AND " + …` (lines
   176, 844 of `production_history_sql_runtime.py`). Tests previously used
   `filters={}` exclusively, so the bug was invisible. Added regression
   `test_compute_detail_page_succeeds_with_non_empty_filter`.

2. **5-tuple key broken for real MES data** — original spec used
   `(lot, spec, eq, trackin_time, trackin_qty)`. Real production data
   showed the same upload's partials have different `TRACKINQTY` values
   (it is the *remaining* qty at each partial's start, not the original
   load). Real example: lot `GA26041607-A00-005` on `GWBA-0146`,
   TrackIn `2026-04-30 00:09:29`: first partial TRACKINQTY=99424
   (TRACKOUTQTY=72800), second partial TRACKINQTY=26624
   (= 99424−72800, TRACKOUTQTY=26606). 5-tuple key would never merge
   these. Fix: dropped TRACKINQTY from key, added `MAX(TRACKINQTY)` to
   the aggregated projection; same-day patch bumps to all three contracts
   (1.6.0→1.6.1, 1.5.0→1.5.1, 1.4.0→1.4.1); regression test added with
   real lot values.

## Lessons Promoted to Standards

Reviewed by `contract-reviewer` at close-out (2026-05-15); two of three
candidates accepted as durable guidance, one rejected as one-off.

- **L1 (TRACKINQTY = remaining-per-partial)** — promoted to `CLAUDE.md`
  §MES Domain Semantics Notes (bullet 1). Already encoded in
  `contracts/business/business-rules.md` PH-06; CLAUDE.md note serves as
  the agent-facing pointer so future MES partial-trackout work does not
  re-derive the wrong key.
- **L2 (same-TrackInTime / different-TrackInQty fixture)** — promoted to
  `CLAUDE.md` §MES Domain Semantics Notes (bullet 2). The fixture rule is
  the test-fixture corollary to L1; bundled in the same section.
- **L3 (double-WHERE SQL parser bug)** — `do-not-promote`. One-off
  implementation defect in a single CTE string-build path; durable
  artifact is the regression test
  `test_compute_detail_page_succeeds_with_non_empty_filter`.

Validators after promotion: `cdd-kit validate --contracts` ✓ (no contract
schema bumps needed), `cdd-kit context-scan` regenerated
`specs/context/project-map.md` and `specs/context/contracts-index.md`.

## Follow-up Work

- Visual-regression baselines (desktop/tablet/mobile) are informational
  only this cycle. If team wants regression coverage, capture post-merge
  baselines for the badge.
- Staging smoke checklist documented in `ci-gates.md` §Promotion Policy
  step 4 (badge present, row-count < raw-count, CSV column populated).

## Cold Data Warning

This archive is historical evidence. Current requirements live in
`contracts/` and active project guidance (`CLAUDE.md`). Do not promote
claims from this file unless they are also reflected in those hot
sources.
