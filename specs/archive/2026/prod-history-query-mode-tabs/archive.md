# Archive — prod-history-query-mode-tabs

## Change Summary

Tier 2 follow-up to the shipped `prod-history-first-tier-cache-filters`
change, driven by real-world usability problems: no way to clear filters, the
date filter being forced even when an identifier (WAFER LOT / 工單 / LOT ID)
already fully specifies scope, and a mandatory TYPE selection blocking
identifier-only queries. The Production History 查詢 page was redesigned into
two explicit query-mode tabs — Tab A 依產品分類查詢 (classification) and Tab B
依識別碼查詢 (identifier) — with the active tab as the single source of truth
for payload building.

## Final Behavior

- **Classification mode (Tab A):** `pj_types` + `start_date` + `end_date`
  remain required; validation unchanged.
- **Identifier mode (Tab B):** ≥1 of mfg_orders / lot_ids / wafer_lots makes
  `pj_types` and dates optional. No date row is shown. When dates are absent
  the backend substitutes a deterministic 730-day wide window
  (`end_date = today`, `start_date = today − (MAX_DATE_RANGE_DAYS − 1)`) —
  Option B, no SQL template or chunk-pipeline change.
- A 清除篩選 button resets all filter state and results across both
  composables.
- Node/result row shape unchanged; existing date-bearing callers flow through
  the byte-identical original validation branch.

## Final Contracts Updated

- `contracts/api/api-contract.md` 1.3.0 → 1.4.0 — Section 10 compatibility
  note: `start_date`/`end_date` relaxed to conditionally-required.
- `contracts/api/api-inventory.md` 1.1.3 → 1.1.4 — scope line + compat note.
- `contracts/business/business-rules.md` 1.3.0 → 1.4.0 — PHF-07
  (identifier-mode date optionality) + PHF-08 (classification-mode required
  params) + 2 decision-table rows.
- `contracts/CHANGELOG.md` — 3 entries dated 2026-05-14.
- CSS / data-shape contracts: no-change (tab UI covered by existing tokens;
  all-time query is predicate-only).

## Final Tests Added / Updated

- Backend: 13 new tests — `TestValidateQueryParamsModeSplit` (8),
  `TestQueryModeSplitRoutes` (3), `TestProductionHistoryQueryModeContract` (2);
  full backend sweep 102 passed.
- Frontend: `useProductionHistory.validation.test.js` +24 (45/45); full
  vitest 331/331; legacy 251/251; type-check clean; build + css:check pass.
- E2E: new `production-history-query-mode-tabs.spec.ts` (4 tests); 4 prior
  specs reconciled to the tab split.

## Final CI/CD Gates

No new workflow files; existing `unit-mock-integration`, `frontend-unit`, and
`playwright-critical-journeys` gates absorb the new + reconciled tests. CI
green on commit `7d65423` (user-confirmed 2026-05-14).

## Production Reality Findings

- `frontend/src/production-history/` has no i18n layer — all strings are
  hard-coded zh-TW. New strings added in the same single-language style; AC-8
  (locale sync) satisfied vacuously.
- One Playwright spec (`production-history-multi-line-input.spec.ts`) tested a
  flow — submitting the single-panel form with empty wildcard inputs — that no
  longer exists by design after the tab split. It was rewritten to assert
  client-side blocking. Assessed as an acceptable design-driven intent change,
  not a coverage loss; the underlying mode-gated payload behavior is still
  covered at the data layer.
- Playwright suite not executed locally — verified by static inspection,
  deferred to CI (now green).

## Lessons Promoted to Standards

None promoted at close. The durable product rule (identifier-mode date
optionality + classification-mode required params) was already promoted
**during /cdd-new** to `contracts/api/api-contract.md` §10 and
`contracts/business/business-rules.md` PHF-07/PHF-08. The
removed-by-design Playwright reconcile is standard CDD regression practice,
not a new project-specific rule. No additional contract or guidance lesson
from the evidence.

## Follow-up Work

- proposal.md open risk: `FIRSTNAME` (wafer_lots) Oracle index coverage
  unconfirmed. A wafer-lot-only no-date query stays date-bounded regardless —
  low severity. Revisit only if production Oracle load on wafer-lot lookups is
  observed high.

## Cold Data Warning

This archive is historical evidence. Current requirements live in `contracts/`
and active project guidance (`CLAUDE.md`).
