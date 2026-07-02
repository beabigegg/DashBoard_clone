# Change Classification

## Change Types
- primary: feature-add (new report page), business-logic-change (new shift-code / output-date rules), api-only-change (new endpoints), data-shape-change (new MySQL target + permission tables + report response shapes)
- secondary: ui-only-change (new page + admin permission block), env-change (`MYSQL_OPS_ENABLED` dependency), ci-cd-change (new page manifests / route-scope matrices)

## Lane
- feature

## Risk Level
- high

Rationale: introduces a NEW authorization primitive (single-flag permission gate) plus a NEW writable persistence path (direct MySQL writes bypassing the established SQLite→sync_worker pattern) plus new domain business rules. New auth + new write path is inherently high-risk even though the report-read portion is medium.

## Impact Radius
- cross-module

Touches: new backend service/routes + `core/permissions.py` + `core/mysql_client.py` + `filter_cache.py` reuse + Oracle read path + admin UI + portal-shell navigation/registry + migration manifests + `page_status.json`.

## Tier
- 1

High risk + cross-module maps to Tier 0–1; the new authorization decision function and new immediately-consistent MySQL write path pull this to Tier 1. Not Tier 0 because there is no system-wide blast radius (isolated new tables, new decorator that does not replace `admin_required`, additive navigation).

## Architecture Review Required
- yes
- reason: Three non-obvious design decisions require a design.md before implementation: (1) a NEW authorization primitive alongside existing `core/permissions.py` (decorator/check design, failure-closed semantics, audit); (2) an explicit deviation from the established SQLite dual-layer sync_worker pattern to direct-MySQL read/write for immediate consistency (data-flow + consistency + `MYSQL_OPS_ENABLED`-off fallback / operational-risk decision, plus table DDL / migration ownership since no existing migration mechanism is shown); (3) re-implementing two Oracle functions (`PJ_GET_CLASSCODE_F`, `PJ_GET_OUTPUTDATE_F`) as Python/SQL business rules with a documented unverified three-shift assumption. These are module-boundary, data-flow, and compatibility trade-off decisions that `spec-architect` must resolve before `implementation-planner`.

## Required Artifacts
Always required: change-request.md, change-classification.md, implementation-plan.md, test-plan.md, ci-gates.md, tasks.yml, context-manifest.md

## Optional Artifacts (default: no — set yes only with explicit reason)
| artifact | create? | reason |
|---|---|---|
| current-behavior.md | no | New feature; no existing behavior being changed. Existing reuse (filter_cache, permissions) is captured in design.md. |
| proposal.md | no | Product intent is fully specified in change-request.md; no separate product investigation needed. |
| spec.md | no | The two re-implemented Oracle functions are formal business rules; they belong in `contracts/business/business-rules.md` (authoritative) + design.md, not a duplicate spec.md. |
| design.md | yes | Architecture Review Required = yes (new auth primitive, direct-MySQL deviation from sync_worker, new-table DDL/migration ownership, Oracle-function re-implementation with unverified assumption). |
| qa-report.md | yes | High-risk change with a new authorization boundary and new write path — durable release-readiness evidence with explicit auth/consistency risk sign-off is warranted. |
| regression-report.md | no | Additive feature; no existing behavior changed. If admin UI / navigation regressions surface, prefer `agent-log/*.yml` pointers unless a blocking finding needs prose. |
| visual-review-report.md | no | New UI, but routine visual evidence fits `agent-log/visual-reviewer.yml`; promote to yes only if a blocking visual finding or evidence bundle is needed. |
| monkey-test-report.md | no | Not a high-fuzz surface; target-value input fuzz fits data-boundary tests + agent-log. |
| stress-soak-report.md | no | Explicit non-goal: not an auto-refresh / big-screen kanban; ordinary filterable report reusing existing spool/report patterns. No new high-load/queue/long-running surface. |

Artifact minimization:
- Prefer optional `agent-log/*.yml` pointers for routine review evidence.
- Create report markdown only for blocking findings, approved-with-risk, visual evidence bundles, or high-risk load/soak results.
- Later artifacts should reference earlier artifacts by path/section/id instead of duplicating full content.

## Required Contracts
- API: yes — new report endpoint(s) (view/summary + filter-options), new target-value read/write endpoint(s), new permission read/write (admin) endpoint(s). Update `contracts/api/api-contract.md`, `api-inventory.md`, and regen BOTH `contracts/openapi.json` and `contracts/api/openapi.json`.
- CSS/UI: yes — new page must be scoped under a `.theme-<name>` block; update `contracts/css/css-contract.md` / `css-inventory.md` for the new authored CSS source.
- Env: yes — document `MYSQL_OPS_ENABLED` dependency (feature requires it `true` in prod) plus any new target/permission MySQL config; `env-contract.md` + `env.schema.json` (enum+default) + `.env.example`.
- Data shape: yes — new MySQL target-value table schema, new MySQL permission-flag table schema, and report response shapes (achievement-rate rows keyed by output_date + shift_code + workcenter_group). Update `contracts/data/data-shape-contract.md`.
- Business logic: yes (primary) — add shift-code rule (two-shift current + three-shift historical), output_date cross-night attribution rule, and the effective-output station/process WHERE predicate as new entries in `contracts/business/business-rules.md`. Mark the three-shift C-band cross-day rule as an unverified assumption.
- CI/CD: yes — new page requires updating `asset_readiness_manifest.json`, `route_scope_matrix.json`, `page_status.json`; released-pages/manifest-completeness gates apply.

## Required Tests
- unit: shift_code classifier (boundary times 07:29:59/07:30:00/19:29:59/19:30:00; two-vs-three-shift date cutoffs 20191231/20200330), output_date attribution (00:00–07:29:59 → prev day; user case 4/26–4/27), achievement-rate math (output ÷ target, zero/missing target), permission-check function (allow/deny/failure-closed), target-value CRUD service.
- contract: response-shape samples for every new endpoint; permission-denied error payload conforms to `error-format.md`.
- integration: direct-MySQL target/permission read-write round-trip via `mysql_client`; `MYSQL_OPS_ENABLED=false` fallback behavior; permission-gated write returns correct 403 when unauthorized; `filter_cache.get_spec_workcenter_mapping()` reuse for grouping.
- E2E: navigate 生產輔助 → 生產達成率, filter (date/shift/workcenter-group), render table/chart; admin permission block assign/revoke; authorized vs unauthorized target-edit path.
- visual: new page + admin permission block render (routine; agent-log evidence unless a blocking finding).
- data-boundary: report handles empty/NULL TRACKOUTQTY, unmapped SPECNAME, missing target rows, malformed target-value input (negative/non-numeric).
- resilience: MySQL unavailable / `MYSQL_OPS_ENABLED` off — report degrades safely, permission check fails closed (deny), no 500 crash.
- fuzz/monkey: (not required)
- stress: (not required — non-goal; ordinary report)
- soak: (not required — non-goal; not auto-refresh)

## Required Agents
- spec-architect (writes design.md: auth primitive, direct-MySQL vs sync_worker deviation, new-table DDL/migration, Oracle-function re-impl + assumption)
- implementation-planner (turns design/contracts/tests into execution packet before implementation agents)
- backend-engineer (Oracle read service, shift/output-date rules, target + permission MySQL tables, new permission decorator, routes)
- frontend-engineer (new report page, filter orchestration + table/chart, admin permission block, navigation/registry/manifest wiring)
- test-strategist (acceptance-criteria → test mapping; boundary/data-boundary/resilience coverage)
- contract-reviewer (API, data-shape, business-rules, env, css, ci contract review — new authorization surface)
- ui-ux-reviewer (new page + admin block interaction/accessibility)
- visual-reviewer (new UI render evidence)
- qa-reviewer (writes qa-report.md; high-risk auth + write-path release readiness)
- ci-cd-gatekeeper (page manifests, route-scope matrix, page_status.json, released-pages gates)

## Inferred Acceptance Criteria
- AC-1: A new "生產達成率" page is reachable under the existing 生產輔助 drawer (alongside /db-scheduling), registered in navigationManifest.js, nativeModuleRegistry.js, asset_readiness_manifest.json, route_scope_matrix.json, and page_status.json.
- AC-2: shift_code is computed in Python/SQL equivalent to `PJ_GET_CLASSCODE_F`: two-shift for dates ≤20191231 or ≥20200330 (00:00:00–07:29:59→N, 07:30:00–19:29:59→D, 19:30:00–23:59:59→N) and three-shift only for 2020/01/01–2020/03/29 (08:00–15:59:59→A, 16:00–23:59:59→B, 00:00–07:59:59→C), verified at all documented boundary seconds.
- AC-3: output_date is computed equivalent to `PJ_GET_OUTPUTDATE_F`: `TRUNC(TRACKOUTTIMESTAMP)` except two-shift 00:00:00–07:29:59 (and three-shift C 00:00:00–07:59:59, marked assumption) attribute to `TRUNC-1`; the user case (4/26 07:30–19:29→4/26 D; 4/26 19:30–4/27 07:29→4/26 N) passes.
- AC-4: The effective-output station/process WHERE predicate (SPECNAME lists + processtypename/WORKFLOWNAME 雙晶/三晶 combinations) is preserved in full and only qualifying trackout events contribute to output; achievement = SUM(TRACKOUTQTY) grouped by output_date + shift_code + workcenter_group ÷ target.
- AC-5: Station grouping (大站點/PACKAGE) is derived by reusing `filter_cache.get_spec_workcenter_mapping()` (`WORK_CENTER_GROUP`), not a newly hardcoded SPECNAME map.
- AC-6: Target values are stored in a new independent MySQL table keyed by shift_code + workcenter_group (no date dimension), read/written directly via `core/mysql_client.py` (never via SQLite sync_worker); when `MYSQL_OPS_ENABLED=false` the feature degrades safely without 500.
- AC-7: A new single-flag permission ("可編輯達成率目標值") is stored in a new independent MySQL table, evaluated by a new permission check distinct from `admin_required`; only whitelisted users can edit target values, unauthorized edit attempts are denied (403, fails closed), and admins manage the whitelist from a new Admin permission block.
- AC-8: The three new business rules (shift_code, output_date, effective-output predicate) are added to `contracts/business/business-rules.md`, with the three-shift C-band cross-day attribution explicitly annotated as an unverified assumption.

## Tasks Not Applicable
- not-applicable: stress-test authoring task(s), soak-test authoring task(s), and the nightly/weekly gate-wiring task (no nightly/weekly gates defined for this feature). Task 1.3 (design review) IS applicable and must NOT be skipped. Exact tasks.yml IDs confirmed against the template when populating tasks.yml.

## Clarifications or Assumptions
- Atomic-split note: cross-surface/contract-heavy/task-heavy triggers are near threshold, but the three pieces form a single dependency chain (permission gate → target-value editing → achievement-rate denominator) rather than independent rollback surfaces, and the user explicitly pre-decided monolithic delivery (change-request 範圍拆分). Proceeding as one Tier-1 change.
- New MySQL table DDL/migration mechanism is unspecified in the indexes; spec-architect must define how the two new tables are created/owned (no existing migration tool is visible in project-map) as part of design.md.
- Exact new frontend app directory name (`production-achievement`) and endpoint paths are proposed from existing naming conventions; implementation-planner/spec-architect finalize them.
- `MYSQL_OPS_ENABLED` default is false; production enablement is a deployment precondition and must be captured in the env contract and design.md operational-risk section.

## Context Manifest Draft

### Affected Surfaces
- backend report service + Oracle read path (new production-achievement service; `DW_MES_LOTWIPHISTORY`)
- backend persistence — direct MySQL (target-value table, permission-flag table) via `core/mysql_client.py`
- backend authorization (`core/permissions.py` — new independent gate)
- shared reuse (`services/filter_cache.py` `get_spec_workcenter_mapping()`)
- backend routes (new report + target-value + admin-permission endpoints)
- frontend new report app (`frontend/src/production-achievement/`) + portal-shell navigation/registry
- admin UI permission block (`frontend/src/admin-*`)
- migration/config manifests (`docs/migration/full-modernization-architecture-blueprint/*`, `data/page_status.json`)
- contracts (api, data, business, env, css, ci)

### Allowed Paths
- specs/changes/production-achievement-kanban/
- specs/context/project-map.md
- specs/context/contracts-index.md
- contracts/api/api-contract.md
- contracts/api/api-inventory.md
- contracts/api/error-format.md
- contracts/api/openapi.json
- contracts/openapi.json
- contracts/business/business-rules.md
- contracts/data/data-shape-contract.md
- contracts/env/env-contract.md
- contracts/env/env.schema.json
- contracts/env/.env.example.template
- contracts/css/css-contract.md
- contracts/css/css-inventory.md
- contracts/ci/ci-gate-contract.md
- src/mes_dashboard/routes/
- src/mes_dashboard/services/
- src/mes_dashboard/core/permissions.py
- src/mes_dashboard/core/mysql_client.py
- src/mes_dashboard/core/response.py
- src/mes_dashboard/core/sync_worker.py
- src/mes_dashboard/config/
- src/mes_dashboard/sql/
- src/mes_dashboard/app.py
- frontend/src/production-achievement/
- frontend/src/portal-shell/
- frontend/src/shared-composables/
- frontend/src/shared-ui/
- frontend/src/admin-pages/
- frontend/src/admin-shared/
- frontend/tests/
- docs/migration/full-modernization-architecture-blueprint/asset_readiness_manifest.json
- docs/migration/full-modernization-architecture-blueprint/route_scope_matrix.json
- data/page_status.json
- tests/

Note: paths are directory-level. `frontend/src/production-achievement/` is a new directory to be created (candidate name derived from the report-app naming convention in project-map: `production-history/`, `yield-alert-center/`).

### Required Contracts (paths)
- contracts/api/api-contract.md
- contracts/api/api-inventory.md
- contracts/api/error-format.md
- contracts/business/business-rules.md
- contracts/data/data-shape-contract.md
- contracts/env/env-contract.md
- contracts/env/env.schema.json
- contracts/css/css-contract.md
- contracts/css/css-inventory.md
- contracts/ci/ci-gate-contract.md

### Required Tests (paths)
- tests/ (backend unit/contract/integration/resilience/data-boundary — new modules)
- tests/e2e/ (new production-achievement E2E)
- tests/integration/ (MySQL target/permission round-trip, `MYSQL_OPS_ENABLED` fallback)
- frontend/tests/ (new report app unit + validation)
- frontend/tests/playwright/ (new page + admin permission E2E; data-boundary dir for target-input malformed cases)

### Agent Work Packets

#### spec-architect
- specs/changes/production-achievement-kanban/
- specs/context/project-map.md
- specs/context/contracts-index.md
- contracts/business/business-rules.md
- contracts/data/data-shape-contract.md
- contracts/env/env-contract.md
- contracts/api/api-contract.md
- src/mes_dashboard/core/permissions.py
- src/mes_dashboard/core/mysql_client.py
- src/mes_dashboard/core/sync_worker.py
- src/mes_dashboard/services/filter_cache.py

#### implementation-planner
- specs/changes/production-achievement-kanban/
- specs/context/project-map.md
- specs/context/contracts-index.md

#### backend-engineer
- specs/changes/production-achievement-kanban/
- contracts/api/, contracts/business/business-rules.md, contracts/data/data-shape-contract.md, contracts/env/
- src/mes_dashboard/routes/
- src/mes_dashboard/services/
- src/mes_dashboard/core/permissions.py
- src/mes_dashboard/core/mysql_client.py
- src/mes_dashboard/core/response.py
- src/mes_dashboard/config/
- src/mes_dashboard/sql/
- src/mes_dashboard/app.py
- tests/

#### frontend-engineer
- specs/changes/production-achievement-kanban/
- contracts/css/, contracts/api/api-contract.md
- frontend/src/production-achievement/
- frontend/src/portal-shell/
- frontend/src/shared-composables/
- frontend/src/shared-ui/
- frontend/src/admin-pages/
- frontend/src/admin-shared/
- frontend/tests/
- docs/migration/full-modernization-architecture-blueprint/asset_readiness_manifest.json
- docs/migration/full-modernization-architecture-blueprint/route_scope_matrix.json
- data/page_status.json

#### test-strategist
- specs/changes/production-achievement-kanban/
- tests/
- frontend/tests/

#### contract-reviewer
- specs/changes/production-achievement-kanban/
- contracts/

#### ui-ux-reviewer
- specs/changes/production-achievement-kanban/
- contracts/css/
- frontend/src/production-achievement/
- frontend/src/admin-pages/

#### visual-reviewer
- specs/changes/production-achievement-kanban/
- contracts/css/
- frontend/src/production-achievement/

#### qa-reviewer
- specs/changes/production-achievement-kanban/
- contracts/

#### ci-cd-gatekeeper
- specs/changes/production-achievement-kanban/
- contracts/ci/ci-gate-contract.md
- docs/migration/full-modernization-architecture-blueprint/asset_readiness_manifest.json
- docs/migration/full-modernization-architecture-blueprint/route_scope_matrix.json
- data/page_status.json

### Context Expansion Requests
- request-id: CER-001
  requested_paths:
    - src/mes_dashboard/services/filter_cache.py
    - src/mes_dashboard/core/permissions.py
    - src/mes_dashboard/core/mysql_client.py
    - src/mes_dashboard/core/sync_worker.py
  reason: spec-architect and backend-engineer must read the exact signatures of `get_spec_workcenter_mapping()`, the existing `is_admin`/`admin_required` shape in `permissions.py`, the `mysql_client` connection/OPS API surface, and the `sync_worker` pattern being deviated from, to design the new gate and direct-MySQL path without guessing. Already included in Allowed Paths; this CER records the justification for reading module internals beyond the index.
  status: approved (paths already included in Allowed Paths above)
- request-id: CER-002
  requested_paths:
    - frontend/src/portal-shell/navigationManifest.js
    - frontend/src/portal-shell/nativeModuleRegistry.js
    - frontend/src/production-history/
  reason: frontend-engineer must read the existing 生產輔助 drawer entry and native-module mount gate to add the new page additively, and needs production-history as the reference report-page architecture (filter orchestration + DataTable/chart) the request cites as the model to follow.
  status: approved (paths already included in Allowed Paths above)
