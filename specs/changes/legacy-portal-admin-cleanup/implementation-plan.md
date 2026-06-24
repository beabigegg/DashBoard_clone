---
change-id: legacy-portal-admin-cleanup
schema-version: 0.1.0
last-changed: 2026-06-24
---

# Implementation Plan: legacy-portal-admin-cleanup

## Objective

Remove the dead legacy non-SPA portal render path so `portal_index` (`/`)
unconditionally `redirect(url_for("portal_shell_page"))`, delete
`templates/portal.html` and the tests that rendered it (deliberate deletes),
strip orphaned drawer-era CSS from `admin-pages/style.css`, and add
`aria-pressed` + `role="alert"` a11y semantics to admin-pages. No user-visible
change in the default (SPA-on) deployment.

## Execution Scope

### In Scope
- Backend: delete the `PORTAL_SPA_ENABLED=false` else-branch in `portal_index`
  (`app.py:1055-1060`) so it unconditionally redirects to `portal_shell_page`.
- Backend: delete `src/mes_dashboard/templates/portal.html`.
- Backend tests: delete the 8 portal.html-render / non-SPA-render cases; add the
  route-name pin, status-key, template-deleted, and AST-no-`portal.html`-reference
  tests in `tests/test_app_factory.py` (see `test-plan.md` AC-1/AC-2/AC-5/AC-6/AC-7).
- Frontend: remove dead drawer-era CSS rules (`admin-pages/style.css:192-272`).
- Frontend: add `aria-pressed` to the status toggle and `role="alert"` to the
  load-error panel; add two vitest files under `frontend/src/admin-pages/__tests__/`
  (see `test-plan.md` AC-3/AC-4).

### Sequencing (mandatory)
**backend-engineer FIRST, then frontend-engineer.** The two engineers touch
disjoint files but share one `test-evidence.yml`; running them sequentially
avoids the test-ladder race on that shared artifact. backend-engineer must
complete its bounded ladder (collect/targeted/changed-area) and write
`test-evidence.yml` before frontend-engineer starts.

### Out of Scope (do NOT do these)
- Do NOT change default SPA navigation behavior — AC-1 parity is real:
  `config/settings.py:79` defaults the flag to `True` (`design.md` Key Decisions).
- Do NOT re-introduce any backend navigation-structure source (ADR 0012 forbids it:
  `docs/adr/0012-navigation-source-of-truth-code-manifest.md`).
- Do NOT remove, rename, or default-change `PORTAL_SPA_ENABLED`. Keep
  `_resolve_portal_spa_enabled` (`app.py:262-272`), its wiring (`app.py:763`), the
  status key `portal_spa_enabled` (`app.py:1048`), and
  `modernization_policy.should_apply_canonical_redirect()` UNCHANGED. Removing the
  flag promotes this to an env-contract change (`design.md` Key Decisions).
- Do NOT rename the `portal_index` route function — load-bearing
  `url_for('portal_index')` back-links in `404/403/500.html` + `admin/pages.html`.
- Do NOT touch the dead drawer-CRUD JS in `templates/admin/pages.html`
  (`#drawers-tbody`, `/admin/api/drawers`, ~L315-666). Only its
  `url_for('portal_index')` back-link is in scope, and it stays valid because the
  route name is kept.
- Do NOT use `skip`/`xfail` for removed tests — deliberate hard deletes (AC-7).
- Do NOT touch `docs/migration/` modernization manifests (CER-001 resolved).
- No opportunistic refactor of `app.py`, `style.css`, `App.vue`, or
  `PagesManagementPanel.vue` beyond the lines named below.

## Required Changes

| id | area | required action | owner agent |
|---|---|---|---|
| IP-1 | backend route | In `portal_index` (`app.py:1055-1060`) delete the `else`/second `return` so the body is only `return redirect(url_for("portal_shell_page"))`. Drop the `if bool(app.config.get("PORTAL_SPA_ENABLED", False))` guard and the `render_template('portal.html', drawers=get_navigation_config())` line. Keep `@app.route('/')` and the function name `portal_index`. | backend-engineer |
| IP-2 | backend template | Delete `src/mes_dashboard/templates/portal.html` (only consumer was the removed branch). | backend-engineer |
| IP-3 | backend preserve | Leave UNCHANGED: `_resolve_portal_spa_enabled` (`app.py:262-272`), `app.config["PORTAL_SPA_ENABLED"] = ...` (`app.py:763`), status key `portal_spa_enabled` (`app.py:1048`), and `core/modernization_policy.py` `should_apply_canonical_redirect()`. (Constraint only — no edit.) | backend-engineer |
| IP-4 | backend tests (delete) | Hard-delete the 8 render/non-SPA cases listed in File-Level Plan; verify none survive `pytest --collect-only`. No skip/xfail. | backend-engineer |
| IP-5 | backend tests (add) | In `tests/test_app_factory.py`: strengthen `test_routes_registered` to assert `/` registers under name `portal_index` AND its handler redirects to the SPA unconditionally; add `test_status_payload_exposes_portal_spa_enabled`, `test_portal_html_template_deleted` (`pathlib.Path.exists()` False), `test_no_portal_html_reference_in_app_source` (AST walk per `docs/architecture/test-discipline.md`). KEEP the 3 flag-resolution tests unchanged. | backend-engineer |
| IP-6 | frontend CSS | Remove dead drawer-era rules `admin-pages/style.css:192-272` (`.input`, `.input:focus`, `.order-input`, `.drawer-create`, `.checkbox-label`, `.action-btn` + `.primary`/`.danger`/hover variants, `.actions-cell`). Stop before `.empty-state` (L274). `css:check` must still pass. | frontend-engineer |
| IP-7 | frontend a11y (toggle) | `components/PagesManagementPanel.vue` status toggle button (L46-53): add `:aria-pressed="page.status === 'released'"` so it reflects Released/Dev state. No new visible text. | frontend-engineer |
| IP-8 | frontend a11y (error) | `App.vue` load-error panel (L112): add `role="alert"` (or `aria-live="assertive"`) to `<div v-if="errorMessage" class="panel error-panel">` so it is announced. No new visible text. | frontend-engineer |
| IP-9 | frontend tests (add) | Add `frontend/src/admin-pages/__tests__/App.test.ts` (load-error panel exposes `role="alert"`) and `frontend/src/admin-pages/__tests__/PagesManagementPanel.test.ts` (`aria-pressed` reflects toggle state). Mirror the existing vitest convention in `frontend/src/admin-dashboard/tabs/__tests__/`. | frontend-engineer |

## Source Artifact Pointers

| source | relevant pointer | used for |
|---|---|---|
| design.md | `## Affected Components` table | per-file change scope + line anchors |
| design.md | Key Decisions (portal_index always SPA; KEEP `PORTAL_SPA_ENABLED`; default parity real) | implementation constraints + why-not-alternatives |
| design.md | Open Risks (Test Impact blast radius; route-name load-bearing; admin/pages.html out of scope) | exact tests to delete + hard constraints |
| test-plan.md | Acceptance Criteria → Test Mapping (AC-1..AC-7) | tests to delete/add + node IDs |
| test-plan.md | Out of Scope | confirms no contract/E2E/integration test work |
| ci-gates.md | Required Gates table + Merge Eligibility | verification gates (pytest, vitest, css:check, e2e-critical, released-pages-hardening) |
| change-classification.md | §Required Contracts / Clarifications | flag-removal would promote to env-contract change |
| docs/adr/0012-navigation-source-of-truth-code-manifest.md | whole | forbids backend nav-structure re-introduction |
| docs/architecture/test-discipline.md | AST-walk absence-proof rule | how to write `test_no_portal_html_reference_in_app_source` |

## File-Level Plan

| path or glob | action | notes |
|---|---|---|
| `src/mes_dashboard/app.py` | edit | IP-1: collapse `portal_index` (L1055-1060) to a single unconditional `return redirect(url_for("portal_shell_page"))`. Do NOT touch L262-272, L763, L948, L1048. |
| `src/mes_dashboard/templates/portal.html` | delete | IP-2: remove file entirely. |
| `src/mes_dashboard/core/modernization_policy.py` | none | IP-3 constraint: `should_apply_canonical_redirect()` must remain reading the flag. No edit. |
| `src/mes_dashboard/templates/{404,403,500}.html`, `templates/admin/pages.html` | none | `url_for('portal_index')` back-links must still resolve (route name kept). No edit. |
| `tests/test_template_integration.py` | edit (delete cases) | Delete `TestPortalDynamicDrawerRendering::test_portal_uses_navigation_config_for_sidebar_links_without_iframe`, `TestPortalDynamicDrawerRendering::test_portal_hides_admin_only_drawer_for_non_admin`, `TestTemplateIntegration::test_portal_includes_base_scripts`, `TestToastCSSIntegration::test_portal_includes_toast_css`. If a class becomes empty, remove the class too. |
| `tests/test_portal_shell_routes.py` | edit (delete branch) | Remove the `PORTAL_SPA_ENABLED=false` render branch from `test_wave_b_native_routes_are_reachable`. |
| `tests/test_hold_routes.py` | edit (delete case) | Delete `TestHoldDetailPageRoute::test_hold_detail_page_requires_reason_non_spa_mode`. |
| `tests/test_yield_alert_shell_coverage.py` | edit (delete case) | Delete `test_yield_alert_page_fallback_contains_vite_entry`. |
| `tests/test_app_factory.py` | edit (strengthen + add) | IP-5: extend `test_routes_registered`; add status-key, template-deleted, AST-no-reference tests; KEEP the 3 `test_portal_spa_flag_*` resolution tests verbatim. |
| `frontend/src/admin-pages/style.css` | edit (delete rules) | IP-6: remove L192-272 only; keep everything from `.empty-state` (L274) onward and all of L1-190. |
| `frontend/src/admin-pages/components/PagesManagementPanel.vue` | edit | IP-7: add `:aria-pressed` to the status toggle button (L46-53). |
| `frontend/src/admin-pages/App.vue` | edit | IP-8: add `role="alert"` to the error panel `<div>` (L112). |
| `frontend/src/admin-pages/__tests__/App.test.ts` | create | IP-9: assert `role="alert"` on error panel. |
| `frontend/src/admin-pages/__tests__/PagesManagementPanel.test.ts` | create | IP-9: assert `aria-pressed` reflects `released`/`dev`. |

## Contract Updates

- API: none. `portal_index` still 200/redirect; status payload keeps the
  `portal_spa_enabled` key (AC-5). No `contracts/api/` or `openapi.json` edit; no
  openapi-sync trigger expected (`ci-gates.md` Workflow section).
- CSS/UI: none. Dead-rule removal stays within the already `.theme-admin-pages`-scoped
  file; confirm no `contracts/css/css-inventory.md` entry is invalidated. `css:check`
  must pass (AC-3).
- Env: none. `PORTAL_SPA_ENABLED` kept — `contracts/env/env-contract.md`,
  `contracts/env/env.schema.json`, `.env.example` untouched. (Touching the flag would
  promote scope to an env-contract change — see `design.md` Key Decisions; if that
  becomes necessary, STOP and report `blocked`.)
- Data shape: none.
- Business logic: none.
- CI/CD: none. No workflow file added/modified; rides existing gates (`ci-gates.md`
  Workflow section).

## Test Execution Plan

Required test phases (floor): `collect`, `targeted`, `changed-area`. No `contract`
phase (no contract change — `test-plan.md` Out of Scope). Each engineer runs the
bounded ladder in their own turn:

1. `cdd-kit test select legacy-portal-admin-cleanup --json`
2. `cdd-kit test run legacy-portal-admin-cleanup --phase collect`
3. `cdd-kit test run legacy-portal-admin-cleanup --phase targeted`
4. `cdd-kit test run legacy-portal-admin-cleanup --phase changed-area`

→ each writes/updates `test-evidence.yml`. backend-engineer runs the full ladder and
writes evidence BEFORE frontend-engineer starts (see Sequencing). The gate validates
`test-evidence.yml`; the full ladder lives in `references/sdd-tdd-policy.md`.

| acceptance criterion | test file / command | expected signal |
|---|---|---|
| AC-1 (redirect) | `tests/test_app_factory.py::AppFactoryTests::test_routes_registered` | `/` handler redirects to SPA unconditionally; pass |
| AC-1 (deletes) | `pytest --collect-only` | none of the 8 deleted node IDs appear; collection count still non-zero |
| AC-2 (route-name pin) | `tests/test_app_factory.py::AppFactoryTests::test_routes_registered` | rule name `portal_index` maps to `/`; pass |
| AC-2 (flag resolution kept) | `tests/test_app_factory.py::AppFactoryTests::test_portal_spa_flag_default_enabled` | unchanged; pass |
| AC-2 (flag resolution kept) | `tests/test_app_factory.py::AppFactoryTests::test_portal_spa_flag_disabled_via_env` | unchanged; pass |
| AC-2 (flag resolution kept) | `tests/test_app_factory.py::AppFactoryTests::test_portal_spa_flag_enabled_via_env` | unchanged; pass |
| AC-3 (css) | `cd frontend && npm run css:check` | exit-0; no unscoped rule introduced |
| AC-4 (toggle a11y) | `frontend/src/admin-pages/__tests__/PagesManagementPanel.test.ts` | `aria-pressed` true when released, false when dev; pass |
| AC-4 (error a11y) | `frontend/src/admin-pages/__tests__/App.test.ts` | error panel exposes `role="alert"`; pass |
| AC-5 (status key) | `tests/test_app_factory.py::test_status_payload_exposes_portal_spa_enabled` | payload contains `portal_spa_enabled`; pass |
| AC-6 (template gone) | `tests/test_app_factory.py::test_portal_html_template_deleted` | `portal.html` does not exist; pass |
| AC-6 (no reference) | `tests/test_app_factory.py::test_no_portal_html_reference_in_app_source` | AST walk finds no `portal.html` string in app source; pass |
| AC-7 (deliberate delete) | `pytest --collect-only` | no `skip`/`xfail` marker on any removed path |

## Handoff Constraints

- Implementation agents must not infer missing requirements from chat history.
- Do not re-copy full design, test strategy, CI policy, or contract prose into this
  plan; follow the source pointers above.
- If this plan omits a required file, behavior, contract, or test, stop and report
  `blocked`.
- Keep implementation within the file-level plan unless a Context Expansion Request is
  approved. Read scope is `context-manifest.md` → `## Allowed Paths`.
- **Hard constraints (must hold at handoff):**
  1. Keep the `portal_index` route NAME (`url_for('portal_index')` resolves from
     404/403/500 + admin/pages templates).
  2. Keep `PORTAL_SPA_ENABLED` + status key `portal_spa_enabled` +
     `modernization_policy.should_apply_canonical_redirect()` UNCHANGED. If the flag
     must be removed/simplified, STOP and report `blocked` (env-contract escalation).
  3. The 8 portal-render tests are DELIBERATE deletes — never `skip`/`xfail`.
  4. `cd frontend && npm run css:check` must still pass after CSS removal.
  5. `aria-pressed`/`role` are attributes, not visible text → no i18n change expected.
     If any new visible label or `aria-label` STRING is introduced, sync ALL i18n
     files (CLAUDE.md Hard Rule 5).
- **Sequencing:** backend-engineer completes and writes `test-evidence.yml` BEFORE
  frontend-engineer begins (shared evidence artifact; sequential avoids the ladder race).
- CER-001 is `resolved` — no `docs/migration/` modernization-manifest read/touch.

## Known Risks

- **Route-name regression is a hard 500.** Renaming `portal_index` 500s the error
  pages and admin back-link. Mitigated by the route-name pin in `test_app_factory.py`
  (`design.md` Open Risks). Backend-engineer must not rename the function.
- **Empty test class after deletes.** Removing `test_portal_includes_base_scripts` /
  the `TestPortalDynamicDrawerRendering` / `TestToastCSSIntegration` cases may leave an
  empty class — remove the now-empty class so collection stays clean; do not leave a
  bare `pass`.
- **Shared `test-evidence.yml` race.** Backend and frontend ladders both write evidence;
  enforced sequential order (backend → frontend) is the mitigation.
- **CSS removal boundary.** Stop the deletion at `style.css:272`; `.empty-state` (L274+)
  and the status-badge rules (≤L190) are live — over-deleting breaks admin-pages layout
  and may flip `css:check`.
- **`admin/pages.html` is dirty but out of scope.** It still contains dead drawer-CRUD
  JS; only its `url_for('portal_index')` back-link matters here. Do not "clean it up."
- **Code-map note:** `portal_index` is a nested route function inside `create_app`, so
  it is not a top-level symbol in `.cdd/code-map.yml`; the L-anchors above were verified
  directly against `app.py` and are authoritative for this plan.
