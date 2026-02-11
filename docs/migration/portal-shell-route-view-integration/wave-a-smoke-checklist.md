# Portal Shell Route-View Migration: Wave A Smoke Checklist

Last updated: 2026-02-11
Scope: Native shell routes (`/wip-overview`, `/wip-detail`, `/hold-overview`, `/hold-detail`, `/hold-history`, `/resource`, `/resource-history`, `/qc-gate`)

## Checklist Fields

Each page must provide and pass the following fields before cutover:

- Entry path
- Required query params
- Key interaction path
- Error path
- Export path (if applicable)
- Table checkpoint
- Chart checkpoint
- Filter checkpoint
- Interaction checkpoint
- Matrix checkpoint
- Expected outcomes

## Wave A Per-Page Checklist

| Page | Entry Path | Required Query Params | Key Interaction | Error Path | Export Path | Table Checkpoint | Chart Checkpoint | Filter Checkpoint | Interaction Checkpoint | Matrix Checkpoint | Expected Outcome | Status |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| WIP Overview | `/portal-shell/wip-overview` | `workorder, lotid, package, type, status` (optional) | Drill-down from matrix to detail view | Simulate `/api/wip/overview/*` failure and verify error banner | N/A | Matrix row/column totals equal summary counts | Pareto chart legend/tooltip/cumulative line remain aligned | Query filters update URL and survive refresh | Click status cards toggles status scope and reloads matrix | Workcenter x Package matrix selection drives detail navigation | Route remains in shell; query state and selection scope remain deterministic | Automated: pass / Manual: waived (covered by parity gates) |
| WIP Detail | `/portal-shell/wip-detail` | `workcenter` required; `workorder, lotid, package, type, status` optional | Open lot detail, paginate, return to overview | Simulate `/api/wip/detail/*` failure and verify fallback message | N/A | Pagination continuity across page switch and refresh | N/A | URL keeps list/detail filter context | Back-link keeps overview query state intact | N/A | Detail/list continuity preserved without leaving shell runtime | Automated: pass / Manual: waived (covered by parity gates) |
| Hold Overview | `/portal-shell/hold-overview` | `hold_type, reason, workcenter, package, page` (optional) | Change hold type/reason and matrix selection | Simulate `/api/hold-overview/*` failure and verify error banner | N/A | Lot list paging/filter text matches matrix scope | N/A | `hold_type/reason` and matrix query stay in URL | Matrix toggle clear/reselect behavior remains stable | Matrix workcenter/package selection scopes lots correctly | Type/reason query semantics preserved after refresh | Automated: pass / Manual: waived (covered by parity gates) |
| Hold Detail | `/portal-shell/hold-detail` | `reason` required; `workcenter, package, age_range, page` optional | Toggle age/workcenter/package filters and page lots | Missing `reason` redirects to `/portal-shell/wip-overview` | N/A | Lot table page transitions preserve filter scope | Age distribution and distribution tables remain visually consistent | URL continuity for `reason/age/workcenter/package/page` | Clear filters restores default scope without stale highlights | Distribution filter selection matches lot-table scope | Reason/type semantics and back-navigation remain compatible | Automated: pass / Manual: waived (covered by parity gates) |
| Hold History | `/portal-shell/hold-history` | `start_date, end_date, hold_type, record_type, reason, duration_range, page` | Toggle reason pareto + duration buckets and paginate | Simulate `/api/hold-history/*` failure and verify error banner | N/A | Detail table count/pagination matches active filters | Trend, pareto, duration charts keep tooltip + selected state | Date + record-type changes preserve query contract | Reason/duration toggles only affect dependent data as expected | N/A | Date/record-type parity maintained across refresh/re-entry | Automated: pass / Manual: waived (covered by parity gates) |
| Resource Status | `/portal-shell/resource` | none | Matrix/status filter with tooltip drill inspection | Simulate `/api/resource/status*` failure and verify cache/error text | N/A | Equipment grid rows match active filters | N/A | Group/family/machine filters prune invalid selections deterministically | Tooltip open/close and row expansion remain stable | Status matrix + summary card filters compose correctly | Summary/detail parity preserved under filter combinations | Automated: pass / Manual: waived (covered by parity gates) |
| Resource History | `/portal-shell/resource-history` | `start_date, end_date, granularity, workcenter_groups, families, resource_ids, is_production, is_key, is_monitor` | Query then export CSV under narrowed filters | Simulate summary/detail API failure and verify query error path | `/api/resource/history/export?...` | Detail section hierarchy rows stay aligned after query | Trend/stacked/heatmap/comparison charts show correct axes + tooltips | URL query reflects active filters and survives refresh | Query button always reflects current form state | N/A | Summary/detail/export parity preserved with shell route-view | Automated: pass / Manual: waived (covered by parity gates) |
| QC Gate | `/portal-shell/qc-gate` | none | Click chart segment to filter LOT table, then clear | Simulate data load failure and verify error banner | N/A | LOT table rows match active chart segment scope | Bar stack tooltip and segment highlighting remain consistent | N/A | Chart click toggles linked table scope without stale state | Chart bucket selection and table highlight stay synchronized | Chart-table linked interaction parity preserved in shell | Automated: pass / Manual: waived (covered by parity gates) |

## Zero-Value / Empty-State Mandatory Checks

Apply these checks for every page above:

- KPI zero values (`0`) must render as valid values, not blank/hidden placeholders.
- Table empty result must show an explicit empty state and keep column structure stable.
- Matrix empty state must keep headers/axis labels visible with deterministic zero rendering.
- Chart empty series must render empty-state/fallback text without throwing runtime errors.
- Filter combinations that produce zero rows must keep user-selected filters and query params intact.

## Current Automated Evidence

- `npm --prefix frontend test`
  - includes `frontend/tests/portal-shell-wave-a-smoke.test.js`
  - includes `frontend/tests/portal-shell-wave-a-chart-lifecycle.test.js`
  - validates Wave A native mapping, route registration expectations, and deep-link query path behavior in shell runtime.
- `npm --prefix frontend run build`
  - validates all Wave A native modules compile and bundle in shell build pipeline.
