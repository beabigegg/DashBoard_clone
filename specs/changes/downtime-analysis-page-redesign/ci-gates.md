# CI/CD Gate Plan

## Change ID
downtime-analysis-page-redesign

# CI/CD Gate Review

## Required Gates for This Change

| gate | tier | required | trigger | command/workflow | artifact |
|---|---:|:---:|---|---|---|
| backend-unit | 0 | yes (local) | pre-commit / push | `pytest tests/test_downtime_analysis_service.py::TestApplyViewFilter` | exit 0 |
| frontend-unit | 0 | yes (local) | pre-commit / push | `cd frontend && npm test` (covers StatusMachineJobTable.test.ts, MachineEventRows.test.ts) | exit 0 |
| css-governance | 0 | yes (local) | pre-commit / push | `cd frontend && npm run css:check` | exit 0 |
| type-check | 1 | yes | pull_request | `cd frontend && npm run type-check` (job: `frontend-unit-tests`) | exit 0 |
| vitest-suite | 1 | yes | pull_request | `cd frontend && npm test` (job: `frontend-unit-tests`, step: Run vitest suite) | exit 0 |
| css-check | 1 | yes | pull_request | `cd frontend && npm run css:check` (job: `frontend-unit-tests`, step: CSS governance check) | exit 0 |
| vite-build | 1 | yes | pull_request | `cd frontend && npm run build` — run locally before PR; CI gate via build-on-push | exit 0 |
| pytest-backend | 1 | yes | pull_request | `pytest` (covers TestApplyViewFilter, TestEquipmentDetailRoute, TestEventDetailRoute, TestFilterDataBoundary, TestDowntimeSummaryShape) | exit 0 |
| playwright-e2e | 1 | yes | pull_request | `npx playwright test tests/playwright/downtime-analysis.spec.js` (job: `frontend-unit-tests`, step: Run Playwright downtime-analysis spec) | exit 0 |
| cdd-validate | 1 | yes | pull_request | `cdd-kit validate` (contracts/CHANGELOG.md must contain `## [api 1.14.0]` entry) | exit 0 |
| cdd-gate-strict | 2 | informational | pull_request | `cdd-kit gate downtime-analysis-page-redesign --strict` | warning only |

## CI/CD Workflow

### Existing workflow: `.github/workflows/frontend-tests.yml`

No workflow file changes are required for this change. All required gates are already wired:

- **Browser install**: `npx playwright install --with-deps chromium` is present at line 53-54.
- **Playwright spec**: `npx playwright test tests/playwright/downtime-analysis.spec.js` is present at line 57-58.
- **Type-check**: present at line 36-38 (`continue-on-error: true` — see note below).
- **Vitest**: present at line 40-42.
- **CSS governance**: present at line 44-46.

#### Note on `type-check` `continue-on-error: true`

The `type-check` step is currently informational in CI (line 37: `continue-on-error: true`). This change introduces new TypeScript types (`ChartFilter`, `TierThreeEntry`) and new component props — type errors here would be silent in CI. The gate is enforced locally at Tier 0 (`npm run type-check` must pass before push). If the project policy upgrades type-check to a hard-fail step in a future change, no additional workflow edit is needed here.

#### Concurrency

The `frontend-tests` workflow does not currently set a concurrency group. This is pre-existing and out of scope for this change. Noted as informational.

### Backend gate: existing `pytest` run

No new pytest workflow file exists; `pytest` is assumed to run in the project's existing CI backend job. All new test classes (`TestApplyViewFilter`, `TestEquipmentDetailRoute` extensions, `TestEventDetailRoute` extensions, `TestFilterDataBoundary`, `TestDowntimeSummaryShape` extensions) live in existing test files and are picked up automatically by `pytest`'s default discovery.

### Workflow changes applied

None. Existing `.github/workflows/frontend-tests.yml` already covers all Tier 1 gates for this change.

## Promotion Policy

This change is **Tier 2 (medium risk)**. The following must be true before merge:

1. All Tier 1 required gates pass green on the PR head commit.
2. `cdd-kit validate` exits 0 — confirms `contracts/CHANGELOG.md` contains the `## [api 1.14.0]` entry.
3. `cdd-kit gate downtime-analysis-page-redesign --strict` exits 0 (all tasks.yml section-6 entries resolved to `done` or `skipped`).
4. UI/UX reviewer has signed off on `.theme-downtime-analysis` scoping and single-page layout (agent-log/ui-ux-reviewer.yml must exist).
5. No shared-ui regression: existing shared-ui component tests pass unchanged (AC-7).

Promotion from `main` to production is via normal deploy pipeline; no additional gate is required beyond the above.

## Rollback Policy

**Backend**: This change adds only optional query params (`big_category`, `status_types`, `resource_id`) to two existing endpoints. The previous callers supply none of these params, so reverting the frontend while leaving the backend in place is safe — all three params default to no-op. A full rollback reverts App.vue to the three-tab structure; `EquipmentDetail.vue` and `EventDetail.vue` remain on disk and are re-wired to the tabs.

**No parquet cleanup required**: No spool schema change, no column rename, no namespace change. The in-memory spool filter is applied post-read; existing parquet files at `tmp/query_spool/downtime_analysis/` are fully compatible.

**No DB migration rollback required**: No SQLite, Oracle, or DuckDB schema changes are made.

**Rollback trigger**: Any Tier 1 gate regression in shared-ui (AC-7) or CSS bleed confirmed in production is sufficient cause to revert the frontend commit. Backend can remain deployed independently.

## Artifact Retention

- Playwright trace artifacts: `retention-days: 7` (hot; failures diagnosed within the sprint).
- Vitest/pytest XML reports: `retention-days: 14`.
- Build dist artifacts: not retained in CI (rebuilt on each deploy).

## Merge Eligibility

**mergeable** — all required Tier 1 gates are covered by the existing workflow without modification; no new workflow file is needed; Playwright browser-install step is pre-existing; `cdd-kit validate` and `cdd-kit gate --strict` are the final local checks before the PR is raised.

Blocked conditions (do not merge if any are true):
- `pytest` fails on any of: `TestApplyViewFilter`, `TestEquipmentDetailRoute`, `TestEventDetailRoute`, `TestFilterDataBoundary`, `TestDowntimeSummaryShape`.
- `npm run css:check` reports any unscoped top-level rule in downtime-analysis CSS.
- `npx playwright test tests/playwright/downtime-analysis.spec.js` fails.
- `cdd-kit validate` fails (missing `## [api 1.14.0]` entry in `contracts/CHANGELOG.md`).
- Any shared-ui component test regression (AC-7).

## Notes

- test-plan.md row references: AC-1 through AC-8 map to gate commands above; see test-plan.md §Acceptance Criteria → Test Mapping for full file-path and tier detail.
- `view_toggle_chart_to_events_preserves_filter_state` (existing Playwright test) must be retired or updated before merge; its removal is a pre-condition for `no_tab_switcher_present_in_redesigned_layout` to be the authoritative AC-3 gate.
- Task 2.6 (CI/CD contract): confirmed satisfied. Browser-install step (`npx playwright install --with-deps chromium`) and Playwright spec invocation (`npx playwright test tests/playwright/downtime-analysis.spec.js`) were already present in `.github/workflows/frontend-tests.yml` lines 53-58 at the time of this review. No workflow edit required.
