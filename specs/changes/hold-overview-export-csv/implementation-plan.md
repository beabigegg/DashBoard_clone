---
change-id: hold-overview-export-csv
schema-version: 0.1.0
last-changed: 2026-06-16
---

# Implementation Plan: hold-overview-export-csv

## Objective
Add a client-side "匯出 CSV" export button to the hold-overview Hold Lot Details
table. Clicking it fetches the full filtered Lot Details dataset via an additive
`export` mode on `GET/POST /api/hold-overview/lots` (pagination cap bypassed,
bounded by `HOLD_OVERVIEW_EXPORT_MAX_ROWS`), assembles a 13-column UTF-8-BOM CSV
in the browser, and triggers a Blob download. Existing paginated behavior must be
byte-for-byte unchanged when `export` is absent.

## Execution Scope

### In Scope
- Backend: add `export` boolean param to `api_hold_overview_lots` route
  (GET query `export=true`, POST body `"export": true`); forward to the service
  so the per_page cap (200) is bypassed in export mode, bounded by
  `HOLD_OVERVIEW_EXPORT_MAX_ROWS` (env, default 10000).
- Backend service: `get_hold_detail_lots` (and its Oracle path
  `_get_hold_detail_lots_from_oracle`) honor an export/full-data flag that
  returns all matching rows up to the cap; both snapshot and Oracle paths.
- Frontend: `exportLoading` ref, `exportLots()` handler, CSV helper module,
  "匯出 CSV" button in the Hold Lot Details card header (reuse `ui-btn
  ui-btn--secondary`, `LoadingSpinner size="sm"`, disabled in-flight).
- Tests per `test-plan.md` (new + extended; see Test Execution Plan).
- New contract sample `tests/contract/samples/get_hold_overview_lots_export.json`.
- Regenerate `contracts/openapi.json` / `contracts/api/openapi.json` if the
  request/response schema cells change.

### Out of Scope
- Server-side CSV streaming / `Content-Disposition` (client-side assembly only —
  data-shape §3.15).
- `core/post-export.ts` server-export path (not used here).
- Any new npm dependency for CSV generation (pure-JS BOM + RFC 4180).
- Any new authored CSS source rule (reuse `ui-btn` tokens only).
- Refactoring the existing pagination logic, filter parsing, or the
  `pagination` envelope keys returned by the service beyond what export mode
  requires.
- i18n file updates — hold-overview ships no i18n JSON (none found under
  `frontend/src/hold-overview/`); button label is a literal string as in
  hold-history.

## Required Changes
| id | area | required action | owner agent |
|---|---|---|---|
| IP-1 | backend route | Parse `export` via `parse_bool_query` in `api_hold_overview_lots`; when true, forward a full-data flag to `get_hold_detail_lots` and bypass the per_page<=200 clamp | backend-engineer |
| IP-2 | backend service | `get_hold_detail_lots` + `_get_hold_detail_lots_from_oracle`: accept export/full-data flag; return all matching rows capped at `HOLD_OVERVIEW_EXPORT_MAX_ROWS`; preserve `summary`/`specs`/`sys_date`; set pagination block to single-page totals | backend-engineer |
| IP-3 | backend config | Read `HOLD_OVERVIEW_EXPORT_MAX_ROWS` (int, default 10000) at the enforcement point; cap enforced even in export mode (AC-7) | backend-engineer |
| IP-4 | contract sample | Add `tests/contract/samples/get_hold_overview_lots_export.json` (export-mode envelope) | backend-engineer |
| IP-5 | openapi | Regenerate `contracts/openapi.json` + `contracts/api/openapi.json` only if request/response schema cells change | backend-engineer |
| IP-6 | frontend CSV helper | Extract `_buildCsvRow`/`_buildCsv`/`_downloadCsv` into an importable module (importable at definition site per test-plan note) | frontend-engineer |
| IP-7 | frontend App.vue | Add `exportLoading` ref + `exportLots()`; call `/api/hold-overview/lots` with `export: true` + current filters; build + download CSV `hold-overview-<YYYY-MM-DD>.csv` | frontend-engineer |
| IP-8 | frontend UI | Add "匯出 CSV" button in Hold Lot Details card header after `FilterIndicator`; `ui-btn ui-btn--secondary`, loading spinner, disabled in-flight (AC-1/AC-8) | frontend-engineer |

## Source Artifact Pointers
| source | relevant pointer | used for |
|---|---|---|
| test-plan.md | AC->test mapping table; Test Families Required; Test Update Contract | tests to write/extend |
| ci-gates.md | Required Gates table; Promotion Policy | verification commands |
| contracts/api/api-contract.md | §10 compat note `hold-overview-export-csv (2026-06-16)` (L424-428); rows L100-101 `/api/hold-overview/lots`; CHANGELOG `[api 1.23.0]` | request param + response envelope contract (already authored) |
| contracts/data/data-shape-contract.md | §3.15 Hold-Overview Lots Export Column Set (L970-1003) | 13-column order, CSV format rules, row boundary |
| change-classification.md | Inferred Acceptance Criteria AC-1..AC-8; Required Contracts | scope + acceptance |

## File-Level Plan
(Ordered: backend tests -> backend impl -> contract sample -> frontend tests -> frontend impl)

| path or glob | action | notes |
|---|---|---|
| tests/test_hold_overview_routes.py | extend | Extend `TestHoldOverviewLotsRoute`: `test_lots_export_bypasses_pagination`, `test_lots_export_capped_at_max_rows`; extend `TestHoldOverviewNonIndexedFilterForwarding` per-kwarg `export` forwarding; assert paginated path unchanged when `export` absent. Do NOT alter existing pagination tests. Per-kwarg `call_args.kwargs[...]` style (test-discipline). |
| tests/stress/test_hold_overview_export_stress.py | create | Tier-3 nightly. Service returns exactly `HOLD_OVERVIEW_EXPORT_MAX_ROWS` rows; assert response row count <= cap, no timeout. |
| src/mes_dashboard/routes/hold_overview_routes.py | modify | `api_hold_overview_lots` (L231-287): add `export = parse_bool_query(args.get('export'))`; when true, skip the `per_page = max(1, min(per_page, 200))` clamp (L264) and forward export flag to the service call (L266-284). `parse_bool_query` already imported (L16). |
| src/mes_dashboard/services/wip_service.py | modify | `get_hold_detail_lots` (3416-3593) snapshot path (slice L3529-3530, pagination L3554-3558) and `_get_hold_detail_lots_from_oracle` (3596-3741) Oracle path (limit/offset L3667-3670, pagination L3716-3724): add export/full-data kwarg; in export mode return all rows capped at `HOLD_OVERVIEW_EXPORT_MAX_ROWS`; keep `summary`/`specs`/`sys_date`. |
| tests/contract/samples/get_hold_overview_lots_export.json | create | Export-mode `success_response` envelope; follow `get_hold_overview_lots.json` structure; full `data.lots` array, single-page pagination block. |
| frontend/tests/hold-overview/csv-export.test.js | create | Unit tests for the CSV helper module: 13 columns + header order (AC-3), UTF-8 BOM prefix (AC-4), RFC 4180 escaping comma/quote/newline (AC-5), null/missing->empty string, empty result->header-only. Import helper at definition site, not via Vue template. |
| frontend/tests/validation/useHoldOverview.validation.test.js | extend | Add export-mode assertion: `export: true` sent + pagination bypassed; preserve existing summary/treemap schema tests. |
| frontend/tests/playwright/hold-overview.spec.js | extend | Click "匯出 CSV": assert request hits export mode + Blob download triggers; button disabled + loading during flight (AC-8) and re-enabled after. Preserve existing filter/render tests. |
| frontend/tests/playwright/data-boundary/hold-overview-export-csv.spec.js | create | Mocked payload with null/undefined fields + empty `lots`; assert no thrown error, header-only CSV download (AC-5 boundary). |
| frontend/src/hold-overview/<csv-helper>.ts | create | CSV helper module (`_buildCsvRow`, `_buildCsv`, `_downloadCsv`) mirroring hold-history App.vue L1027-1054; exact filename is an open decision (see below). |
| frontend/src/hold-overview/App.vue | modify | Add `exportLoading = ref(false)` + `exportLots()` (mirror hold-history App.vue L1018-1095): build full-data params from `buildLotsParams()` (~L338) with `export:true`, call via the same `apiPost('/api/hold-overview/lots', ...)` used by `fetchLots` (L381-382), unwrap, build + download. Add button in Hold Lot Details card header (template L957-966, after `FilterIndicator`). |

## Contract Updates
- API: `contracts/api/api-contract.md` — already authored (rows L100-101, §10 note
  L424-428, CHANGELOG `[api 1.23.0]`). No new edit required unless review finds a
  gap. Regenerate `contracts/openapi.json` only if schema cells change (IP-5).
- CSS/UI: none — reuse `ui-btn ui-btn--secondary`. No `css-contract.md` edit
  (confirm during impl; only add if a new authored rule is introduced).
- Env: `HOLD_OVERVIEW_EXPORT_MAX_ROWS` (int, default 10000). data-shape §3.15
  pins it; the change brief also asks to record it in `contracts/env/env-contract.md`,
  which is NOT in the manifest Allowed Paths — see CER-002 and Open Decision 5
  before editing it.
- Data shape: `contracts/data/data-shape-contract.md` §3.15 — already authored
  (13-column set, format rules, row boundary). No new edit required.
- Business logic: none.
- CI/CD: none (existing PR + nightly jobs cover all gates per ci-gates.md).

## Test Execution Plan
| acceptance criterion | test file / command | expected signal |
|---|---|---|
| AC-1, AC-3, AC-4, AC-5 (CSV helpers) | frontend/tests/hold-overview/csv-export.test.js | 13 cols/header order, BOM prefix, RFC 4180 escaping, null->empty, empty->header-only |
| AC-2 (composable export flag) | frontend/tests/validation/useHoldOverview.validation.test.js | `export:true` sent, pagination bypassed |
| AC-2, AC-6, AC-7 (route forward + cap + paginated unaffected) | tests/test_hold_overview_routes.py | per-kwarg `export` forwarded; cap enforced; paginated path unchanged |
| AC-3 (column set vs contract) | tests/contract/samples/get_hold_overview_lots_export.json | sample validates via `cdd-kit validate --contracts` |
| AC-5 (boundary) | frontend/tests/playwright/data-boundary/hold-overview-export-csv.spec.js | no error, header-only CSV download |
| AC-8 (button loading/disabled/re-enable + download) | frontend/tests/playwright/hold-overview.spec.js | disabled+loading in-flight, enabled after, Blob download |
| AC-7 (stress, Tier-3 nightly) | tests/stress/test_hold_overview_export_stress.py | row count <= `HOLD_OVERVIEW_EXPORT_MAX_ROWS`, no timeout |

Required test phases (cdd-kit test run): `collect`, `targeted`, `changed-area`;
`contract` (new sample) and `quality` (lint/type-check) triggers apply. Stress is
Tier-3 nightly — not a PR gate and must not be listed as waived/skipped. Full
ladder lives in test-plan.md / references/sdd-tdd-policy.md.

## Handoff Constraints
- Implementation agents must not infer missing requirements from chat history.
- Do not re-copy full design, test strategy, CI policy, or contract prose into this plan; follow the source pointers above.
- If this plan omits a required file, behavior, contract, or test, stop and report `blocked`.
- Keep implementation within the file-level plan unless a Context Expansion Request is approved.
- The `export` parameter is strictly additive (AC-6): omitting it must reproduce
  current responses exactly. The row cap must apply even in export mode (AC-7).

## Open Decisions (lock before implementation starts)
1. **Service flag plumbing**: `get_hold_detail_lots` is the single service entry
   (code-map: defined in `wip_service.py`, imported by `hold_overview_routes.py`
   L21, patched in route tests as
   `mes_dashboard.routes.hold_overview_routes.get_hold_detail_lots`). Decide the
   flag name/shape. Recommended: add an explicit `export: bool = False` kwarg
   rather than overloading `page_size`, so per-kwarg route-forwarding tests are
   unambiguous.
2. **Pagination envelope keys**: the existing service returns
   `pagination: {page, perPage, total, totalPages}` (camelCase, wip_service
   L3554-3558 / L3720-3724), but api-contract §10 / data-shape describe
   `meta.pagination: {page, per_page, total_count, total_pages}` (snake_case).
   These differ. Lock whether export mode keeps the existing camelCase service
   keys (lower-risk, additive) or whether the contract note intends a new
   `meta.pagination`. backend-engineer + contract-reviewer must reconcile the
   contract wording with the actual envelope before writing the sample
   (`get_hold_overview_lots_export.json`) — the sample must match the real route
   output, not the prose if they conflict.
3. **Cap enforcement point**: decide whether `HOLD_OVERVIEW_EXPORT_MAX_ROWS` is
   enforced in the route (truncate `page_size`) or in the service (slice/limit
   the result). Recommended: enforce in the service so both snapshot and Oracle
   paths share one cap and the stress test can target it directly.
4. **CSV helper module path**: pick the exact filename for the extracted helper
   (e.g. `frontend/src/hold-overview/csvExport.ts`). Must be importable by
   `csv-export.test.js` without instantiating the Vue component.
5. **env-contract write target**: `contracts/env/env-contract.md` is outside the
   manifest Allowed Paths. Either (a) approve CER-002 to edit it, or (b) accept
   data-shape §3.15 as the env-var pin of record and skip env-contract. Resolve
   before backend-engineer touches env documentation.

## Context Expansion Requests
- request-id: CER-002
  requested_paths:
    - contracts/env/env-contract.md
  reason: The change brief asks to document `HOLD_OVERVIEW_EXPORT_MAX_ROWS` in
    env-contract.md, but that file is not in the context-manifest Allowed Paths.
    Needed only if Open Decision 5 chooses to pin the env var there rather than
    relying on data-shape §3.15.
  status: pending

## Known Risks
- The api-contract §10 / data-shape pagination wording (snake_case
  `meta.pagination`) diverges from the live service envelope (camelCase
  `perPage`/`totalPages`). If the contract sample is authored to the prose,
  contract-validation may pass while the real route output diverges — Open
  Decision 2 must be locked first.
- Full-data fetch can be large; the cap (`HOLD_OVERVIEW_EXPORT_MAX_ROWS`) is the
  only guard. If production filtered hold sets exceed the cap, exports silently
  truncate — data-shape §3.15 notes a higher cap / warning banner may be needed
  (out of scope here; flag if observed).
- code-map digest is from 2026-06-16 (cdd-kit 3.2.0) at the current HEAD commit;
  cited line ranges (route L231-287, service L3416-3741) were cross-checked via
  Grep and are current.
- CER-001 (hold-overview/hold-history `components/` dirs) is still `pending` in
  the manifest, but the export button lives in `hold-overview/App.vue` (Hold Lot
  Details card header, L957-966 — not a separate DetailTable component), so
  CER-001 is not blocking for this plan.
