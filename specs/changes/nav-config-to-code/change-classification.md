# Change Classification

## Change Types
- primary: `refactor` (navigation source-of-truth relocation: runtime CMS → code manifest), `api-removal` (breaking removal of drawer CRUD + shrink of `PUT /api/pages/<route>`)
- secondary: `data-shape-change` (writable `page_status.json` → minimal route→status map), `feature-reduction` (admin-pages drawer create/edit/reorder/rename retired), `migration` (port live menu layout into manifest), `modernization-manifest-update`, `ci-cd-change` (regenerated/retired contract samples)

## Lane
- feature

## Risk Level
- medium

## Impact Radius
- cross-module (backend route+service, writable data file, portal-shell nav pipeline, admin-pages app, modernization manifests, contracts/tests). NOT system-wide: blast radius is admin-only (`@admin_required`); the only general-user surface (rendered menu) must stay equivalent (AC-1). No concurrency, queues, caches, payments, PII, Oracle query-cost, or long-running-job surfaces.

## Tier
- 2

Rationale: medium × cross-module, classified up to Tier 2 because it (a) makes a breaking API change (endpoint + request-field removal), (b) changes the shape of a persisted writable store, and (c) moves an architectural source-of-truth — each warranting the stricter contract+architecture review.

## Architecture Review Required
- yes
- reason: Relocates the navigation source-of-truth from a runtime CMS (`page_status.json` + admin endpoints) to a code-side manifest, collapsing the 3-way config duplication (nativeModuleRegistry / routeContracts / page_status.json). Module-boundary + data-flow change with a compatibility decision (which fields move to code vs stay runtime-writable) and a migration/rollback decision (port live layout, rename drawer ids, drop `test` drawer). `spec-architect` writes `design.md` (manifest schema, shrunk writable-store schema, code read-path replacing `GET /api/drawers`, migration mapping, rollback) + the ADR, before `implementation-planner`.

## Required Artifacts
Always required: change-request.md, change-classification.md, implementation-plan.md, test-plan.md, ci-gates.md, tasks.yml, context-manifest.md

## Optional Artifacts (default: no — set yes only with explicit reason)
| artifact | create? | reason |
|---|---|---|
| current-behavior.md | yes | AC-1 demands a "structurally identical" menu; needs a captured baseline (drawers, order, page order, display names, visible set) to diff against. Regression anchor. |
| proposal.md | no | Scope + Option B already decided with requester. |
| spec.md | no | User-facing decision fully captured in change-request + design.md. |
| design.md | yes | Forced by Architecture Review = yes. Owns manifest schema, shrunk store schema, code read-path, migration mapping, rollback. |
| qa-report.md | no | Routine evidence → `agent-log/qa-reviewer.yml`. |
| regression-report.md | yes | Changes existing behavior (removed endpoints, shrunk request contract + writable store) with a hard "no user-visible menu change" guarantee (AC-1). Durable regression evidence is the core safety proof. |
| visual-review-report.md | no | No new visual design; menu-parity asserted structurally, not pixel diff. |
| monkey-test-report.md | no | No new untrusted-input surface (status is a single enum write). |
| stress-soak-report.md | no | No load/queue/cache/long-running surface. |

ADR: required (recorded under `docs/adr/`), owned by `spec-architect`.

## Required Contracts
- API: yes — `contracts/api/api-contract.md` (remove `POST/PUT/DELETE /api/drawers` + `GET /api/drawers`; shrink `PUT /api/pages/<route>` body to status-only; slim `GET /api/pages` response), `contracts/api/api-inventory.md` (drop drawer endpoints), regenerate `contracts/api/openapi.json` + `contracts/openapi.json`, breaking entry in `contracts/CHANGELOG.md`.
- CSS/UI: no.
- Env: no.
- Data shape: yes — `contracts/data/data-shape-contract.md` for the shrunk writable store (`data/page_status.json` → route→status map) + the code-side manifest shape + slimmed `GET /api/pages` response.
- Business logic: conditional — `contracts/business/business-rules.md` only if `released`/`dev` visibility semantics need wording changes (likely no-op; contract-reviewer confirms).
- CI/CD: yes — regenerated/retired samples must pass `cdd-kit validate --contracts`, `test_schema_coverage`, `test_manifest_completeness`. Modernization manifests (`docs/migration/full-modernization-architecture-blueprint/{asset_readiness_manifest,route_scope_matrix}.json`) are mandatory deliverables (project modernization policy), not CDD contracts.

## Required Tests
- unit: backend `admin_routes` (removed drawer endpoints reject; `PUT /api/pages` accepts only `status`; `GET /api/pages` slimmed) + `page_registry` service (page_status get/set on shrunk store; drawer read now sources code manifest); frontend `navigationState.js` (menu from manifest, not `GET /api/drawers`) + new manifest module.
- contract: regenerate `get_admin_pages.json` (slimmed); retire `get_admin_drawers.json`, `delete_admin_drawers_id.json`; rerun `test_schema_coverage`, `test_manifest_completeness`, `test_api_contract`.
- integration: removed-endpoint behavior under `@admin_required` (404/405).
- E2E: `admin-pages.spec` (drawer controls gone; status toggle round-trips → AC-2); portal-shell non-admin menu-parity (AC-1).
- visual: not required (structural parity).
- data-boundary: slimmed `GET /api/pages` shape + legacy-format `page_status.json` back-compat read (fail safe to manifest defaults).
- resilience: light — page/drawer read fails safe on missing/legacy store (in service unit tests).
- fuzz/monkey: no. stress: no. soak: no.

## Required Agents
spec-architect → contract-reviewer → test-strategist → ci-cd-gatekeeper → implementation-planner → backend-engineer → frontend-engineer → ui-ux-reviewer → qa-reviewer.
(spec-architect runs first: this is architecture-led, contracts depend on its schema decisions. dependency-security-reviewer NOT required — no lockfile/dep/DB-migration change. visual-reviewer NOT required — no new visual design.)

## Inferred Acceptance Criteria
- AC-1: Non-admin navigation menu is structurally identical post-change (same drawers, drawer order, page order, display names, visible-page set), sourced entirely from the code manifest; only internal drawer ids cleaned up. [confirmed]
- AC-2: Admin can still set a page's status `released`/`dev` from the admin-pages frontend; persists to the shrunk store and takes effect on next nav load. [confirmed]
- AC-3: Drawer CRUD (`POST/PUT/DELETE /api/drawers`) + `GET /api/drawers` + name/drawer_id/order fields of `PUT /api/pages/<route>` are gone; admin UI no longer offers drawer create/edit/reorder/rename. [confirmed]
- AC-4: API/data/modernization contracts + affected contract samples updated; `admin_routes` + `navigationState` tests updated/retired; ADR recorded; `cdd-kit gate` passes. [confirmed]
- AC-5 (migration parity): Manifest reproduces current live layout 1:1 — every visible page maps to the same drawer/order/display-name; auto-default drawer ids renamed with no placement change; empty `test` drawer dropped. [derived — makes AC-1 machine-checkable]
- AC-6 (store shape + back-compat): `data/page_status.json` reduced to route→status map; read path fails safe on a missing/legacy full-CMS file (falls back to manifest defaults). [derived]
- AC-7 (removed-endpoint behavior): removed drawer routes + non-`status` fields on `PUT /api/pages` are rejected consistently (404/405 for removed routes) under `@admin_required`. [derived]
- AC-8 (sample regen/retire): `get_admin_pages.json` slimmed; `get_admin_drawers.json` + `delete_admin_drawers_id.json` retired in lockstep; `cdd-kit validate --contracts` + schema/manifest coverage pass; both `openapi.json` regenerated; `CHANGELOG.md` records breaking removal. [derived]

## Tasks Not Applicable
- not-applicable: 2.2, 2.3, 3.5, 4.3, 5.2, 6.4

## Clarifications or Assumptions
1. **CER-001 RESOLVED**: page/drawer service is `src/mes_dashboard/services/page_registry.py` (admin_routes imports it L42; defines get_all_pages/get_all_drawers/create_drawer/update_drawer/delete_drawer/set_page_status/get_page_status). `navigation_contract.py` is NOT involved.
2. **CER-002 RESOLVED**: sample-capture harness present — `tests/contract/capture_samples.py` + `tests/contract/response-samples.json`.
3. **Manifests RESOLVED**: `docs/migration/full-modernization-architecture-blueprint/{asset_readiness_manifest,route_scope_matrix}.json`.
4. **Code-manifest location/format** is a design decision (new `frontend/src/portal-shell/navigationManifest.*` vs extend `routeContracts.js`; whether backend reads same manifest or a backend copy for `GET /api/pages`/drawer reads). spec-architect fixes in design.md.
5. **`GET /api/pages` stays, slimmed** — admin status-toggle UI reads it; exact retained fields fixed in design.md (drives `get_admin_pages.json` regen + data-shape contract).
6. **business-rules edit conditional** — released/dev semantics unchanged in behavior; at most a wording/pointer touch.

## Context Manifest Draft
Full draft written to `context-manifest.md` (Allowed Paths, Required Contracts/Tests, per-agent work packets, approved expansions). CER-001/002 resolved there.
