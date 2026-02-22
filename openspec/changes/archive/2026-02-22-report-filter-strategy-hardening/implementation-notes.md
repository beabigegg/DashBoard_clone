# Implementation Notes

## 1) Page classification (exploratory baseline)

- `reject-history`: exploratory
  - Requires draft-driven options narrowing for `WORKCENTER_GROUP` / `Package` / `原因`
  - Requires stale-response protection + invalid-value auto-prune before apply/export
- `resource-history`: exploratory
  - Requires upstream-to-downstream narrowing (`群組/旗標 -> 型號 -> 機台`)
  - Requires family/machine auto-prune and committed query execution model

## 2) Frontend responsibilities mapping

- `frontend/src/reject-history/App.vue`
  - Holds **draft filters** (`draftFilters`) for options narrowing
  - Holds **committed filters** (`committedFilters`) for summary/trend/pareto/list/export
  - Performs debounced options reload and stale response discard
  - Prunes invalid draft values and applies non-blocking prune hint
- `frontend/src/resource-history/App.vue`
  - Holds draft/committed filter split and URL sync on committed only
  - Derives family/machine options from loaded resource metadata before first query
  - Prunes invalid family/machine values on upstream changes
  - Uses apply/clear semantics with deterministic reset
- Shared helper modules for deterministic unit-test coverage:
  - `frontend/src/core/reject-history-filters.js`
  - `frontend/src/core/resource-history-filters.js`

## 3) Debounce & request-guard conventions

- `reject-history` draft options debounce: `300ms`
  - Constant: `OPTIONS_DEBOUNCE_MS = 300`
  - stale-response guard: monotonic request token (`activeOptionsRequestId`)
- `reject-history` data queries and list updates
  - stale-response guard: monotonic request token (`activeDataRequestId`)
- `resource-history`
  - Uses local computed narrowing/prune (no per-change options API call), so no options debounce required
  - Query execution remains explicit on apply/clear

## 4) Manual verification checklist (2026-02-22)

- [x] Reject-history: changing draft `WORKCENTER_GROUP` narrows `Package/原因` options
- [x] Reject-history: changing policy toggles narrows options and keeps list/analytics policy alignment
- [x] Reject-history: invalid selected values auto-prune and show non-blocking hint
- [x] Reject-history: apply/export only use committed valid filters
- [x] Resource-history: first load provides usable family/machine candidates before first query
- [x] Resource-history: upstream (`群組/設備旗標`) changes prune invalid `型號/機台`
- [x] Resource-history: query + URL sync use committed filters only
- [x] Resource-history: clear resets deterministic defaults and reloads data

## 5) Monitoring/drilldown non-goal guard

- No filter strategy rollout changes were applied to monitoring/drilldown page code paths in this change.
- Scope verification: file modifications are limited to reject-history/resource-history flows, related SQL/routes/services, tests, and change artifacts.

## 6) Release note entry (draft)

- Title: `Exploratory filter strategy hardening for Reject History and Resource History`
- Scope:
  - Added interdependent draft option narrowing and invalid-selection pruning on `reject-history`
  - Strengthened upstream-driven family/machine narrowing and prune behavior on `resource-history`
  - Unified apply/clear semantics and non-blocking prune feedback on both exploratory pages
- Non-goals:
  - No global rollout to all released reports
  - No KPI/business formula changes
  - No monitoring/drilldown filtering model migration in this release
