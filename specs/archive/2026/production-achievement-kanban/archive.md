# Archive: production-achievement-kanban

## Change Summary

Added a new "生產達成率" (production achievement rate) filterable report page under the existing 生產輔助 nav drawer. Re-implemented two Oracle business functions with no prior Python equivalent (shift-code classification and cross-midnight output-date attribution), preserved the effective-output station/process qualifying predicate verbatim from user-supplied SQL, and added target-value management (two new independent MySQL tables, direct-`mysql_client` read/write bypassing the SQLite `sync_worker` dual-layer) gated by a new fail-closed `can_edit_targets` permission primitive independent of `admin_required`.

## Final Behavior

- New page at `/production-achievement` (生產輔助 drawer): date-range + shift_code + workcenter_group filters, table/chart of achievement rows (actual output vs. target, nullable achievement_rate displayed as "—", never Infinity/NaN).
- 6 new endpoints: `GET /api/production-achievement/{report,filter-options,targets}`, `PUT /api/production-achievement/targets` (permission-gated), `GET`/`PUT /admin/api/production-achievement/permissions*` (admin-gated).
- New Admin page block to manage the `can_edit_targets` whitelist.
- Business rules PA-01..PA-07 in `contracts/business/business-rules.md`.

## Final Contracts Updated

business-rules.md, data-shape-contract.md (§3.25/§3.26/§3.27), api-contract.md + api-inventory.md (+ both openapi.json regenerated), env-contract.md + env.schema.json (new `## MySQL OPS` section — closed a pre-existing doc gap), css-contract.md + css-inventory.md, ci-gate-contract.md. All additive; no breaking changes.

## Final Tests Added / Updated

109 backend unit/contract/integration tests, 38 frontend unit tests, 10 Playwright specs (critical-journey, resilience, data-boundary) — all run live against a real built gunicorn+dist server, not just `--list`. `tests/test_permissions.py` extended (additive) for the new gate.

## Final CI/CD Gates

No new gate tier, job, or workflow file. `tests/playwright/production-achievement.spec.js` appended to the existing `playwright-critical-journeys` command. Tier 4 stress/soak explicitly not applicable (non-goal). See `ci-gates.md` for the full promotion/rollback policy.

## Production Reality Findings

Three real bugs surfaced only after deploying and testing against **real production-scale data** — none were caught by the CDD review pipeline (contract review, backend/frontend implementation, e2e-resilience live testing against mocked APIs, ui-ux/visual review, qa-reviewer), because none of those steps exercised a real Oracle connection at realistic data volume, or a real production `npm run build` + startup asset-readiness check:

1. **`frontend/vite.config.ts`'s hand-maintained page-entry `INPUT_MAP`** was never updated for the new page, even though `index.html`/`main.ts` were created following the established per-page convention. The build silently skipped the page; startup's `_validate_in_scope_asset_readiness()` check correctly caught the missing dist asset and refused to boot. **This is a fourth hand-maintained page registry**, distinct from `navigationManifest.js`, `nativeModuleRegistry.js`, `asset_readiness_manifest.json`, and `route_scope_matrix.json` — none of which reference or validate against it.
2. **`frontend/src/portal-shell/routeContracts.js`'s `ROUTE_CONTRACTS` map** — a **fifth** hand-maintained per-route registry (routeId/title/owner/visibilityPolicy/scope) — was also never updated, producing a `部分導覽項目缺少 route contract` console warning at runtime. No test in the repo asserts completeness of this file against `navigationManifest.js`.
3. **Oracle query timeout (DPY-4024, 55s call_timeout)** on the achievement-report query, for any date range including a single day. Root-caused via `ALL_TABLES`/`ALL_IND_COLUMNS` against the real dev DB: `DWH.DW_MES_WIP` has 95M+ rows and **no index on `CONTAINERID`** (only `CONTAINERNAME` and `TXNDATE`) — the WORKFLOWNAME dedup join (`ROW_NUMBER() OVER (PARTITION BY CONTAINERID ...)`, copied from the `mid_section_defect` precedent) forced a full-table scan regardless of date-range or SPECNAME scoping (measured: unscoped → timeout; date-scoped (~36K containers) → 47.5s; +SPECNAME-allowlist-scoped (~16.7K containers) → 41s — cost dominated by the mandatory scan itself, not join cardinality). Fixed by bridging through `DWH.DW_MES_CONTAINER` (5.5M rows, indexed on **both** `CONTAINERID` and `CONTAINERNAME`) to translate the scope into `CONTAINERNAME`s, then joining `DW_MES_WIP` via its indexed `CONTAINERNAME` column. Result: 30-day window ~22-32s (under the 55s timeout).

All three fixes were verified against the real dev Oracle/MySQL databases (`mysqldev.panjit.com.tw`) with explicit user authorization for each live-connection action, shipped as three small follow-up PRs (#20, #21) after the main feature PR (#19), and merged.

## Lessons Promoted to Standards

Reviewed by `contract-reviewer` against this change's evidence; both approved and applied (corrected an existing incomplete line + one new line, net-growth-zero consolidation discipline):

1. **Page registration checklist was incomplete.** `CLAUDE.md`'s "Modernization policy" line corrected in place (was: "update BOTH `asset_readiness_manifest.json` AND `route_scope_matrix.json`") to also name `vite.config.ts` `INPUT_MAP` and `portal-shell/routeContracts.js` `ROUTE_CONTRACTS`, with the boot-blocking-vs-warning-only distinction. Detail section added to `docs/architecture/modernization-policy.md` ("vite.config.ts INPUT_MAP and routeContracts.js ROUTE_CONTRACTS — Also Required"). Evidence: this change's post-merge PR #20/#21.
2. **`DW_MES_WIP` has no `CONTAINERID` index.** New one-line pointer added to `CLAUDE.md`'s "Service architecture" bullet group; detail section added to `docs/architecture/service-patterns.md` ("DW_MES_WIP Has No CONTAINERID Index — Bridge Through DW_MES_CONTAINER"), including the measured timings and the `DW_MES_CONTAINER` bridge fix. Evidence: this change's PR #21, verified against the real dev Oracle DB.

Not promoted (evidence-insufficient or out of scope, per contract-reviewer): adding `navigationManifest.js`/`nativeModuleRegistry.js` to the same checklist (no incident evidence — frontend-engineer wired those correctly); recording the `CONTAINERID` index gap as a new PA-0x business rule (it's a physical-schema/performance fact, not a production-achievement business decision — `service-patterns.md` is the correct home); asserting that `mid_section_defect`'s precedent query is safe from this same issue (no evidence found in read scope — left as an open follow-up question in the promoted text instead).

`cdd-kit validate --contracts` and `cdd-kit context-scan` both re-run clean after applying.

## Follow-up Work

- PA-04 (three-shift historical regime output_date rule) remains an unverified assumption — flagged in code/contract, not an acceptance target for this change.
- UI/UX polish items (no confirmation before revoking `can_edit_targets`, `window.alert()` for admin feedback instead of the in-app error-banner idiom, no focus-transfer into the target-edit input on open) — tracked, non-blocking, candidate for a small follow-up change.
- `frontend/src/production-achievement/App.vue`'s `data-testid="pa-report-table"` is silently dropped by Vue's multi-root-template attrs behavior on `<DataTable>` — cosmetic, tests were adapted to work around it; a future change could wrap `<DataTable>` in a single-root div carrying the testid (pattern already used by `db-scheduling`/`material-trace`).
- No automated test asserts completeness of `vite.config.ts`'s `INPUT_MAP` or `routeContracts.js`'s `ROUTE_CONTRACTS` against `navigationManifest.js`'s registered pages — this exact gap caused two of the three post-merge bugs and could recur for the next new page.

## Cold Data Warning

This archive is historical evidence. Current requirements live in `contracts/` and active project guidance (`CLAUDE.md`).
