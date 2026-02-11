# Portal No-Iframe Migration Parity Checklist

This checklist is the execution companion for `portal-no-iframe-navigation` migration.

## A. Drawer Visibility Parity

- [ ] Non-admin visible drawers/routes match `baseline_drawer_visibility.json` exactly.
- [ ] Admin visible drawers/routes match `baseline_drawer_visibility.json` exactly.
- [ ] Empty drawers remain hidden.
- [ ] `admin_only` drawer behavior remains unchanged.

## B. Route and Query Contract Parity

- [ ] `/wip-overview` preserves `workorder|lotid|package|type|status` URL semantics.
- [ ] `/wip-detail` preserves `workcenter|workorder|lotid|package|type|status` URL semantics.
- [ ] `/hold-detail` preserves required `reason` semantics and fallback behavior.
- [ ] `/resource-history` preserves date/granularity/group/family/resource/flag query semantics.

## C. Core Workflow Smoke Paths

- [ ] Legacy rewrite per-page smoke checklist passes (`legacy_rewrite_smoke_checklists.md`).
- [ ] `/` open portal and switch via drawer navigation.
- [ ] `/wip-overview` apply filters and drill down to `/wip-detail`.
- [ ] `/wip-overview` reason drill-down to `/hold-detail`.
- [ ] `/resource-history` execute query and export path.
- [ ] Legacy rewrite pages (`/job-query`, `/excel-query`, `/query-tool`, `/tmtt-defect`) remain reachable and usable.

## D. API Payload Contract Parity

- [ ] `/api/wip/overview/summary` required keys present.
- [ ] `/api/wip/overview/matrix` required keys present.
- [ ] `/api/wip/hold-detail/summary` required keys present.
- [ ] `/api/resource/history/summary` required keys present.
- [ ] `/api/resource/history/detail` required keys present.

## E. Stability and Performance

- [ ] No unhandled JS runtime errors on critical E2E paths.
- [ ] Route switch latency remains within agreed threshold.
- [ ] Memory footprint does not regress beyond agreed threshold.

## F. Cutover Decision

- [ ] All G1~G7 gates are green.
- [ ] Rollback rehearsal result is recent and valid.
- [ ] Cutover owner and rollback owner are explicitly assigned.
