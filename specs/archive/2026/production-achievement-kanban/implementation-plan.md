---
change-id: production-achievement-kanban
schema-version: 0.1.0
last-changed: 2026-07-02
---

# Implementation Plan: production-achievement-kanban

## Objective
Ship the additive "生產達成率" filterable report page under the existing 生產輔助 drawer, backed by:
1. an Oracle read service that computes shift_code + output_date (PA-01..PA-04) and the PA-05 effective-output predicate as SQL CASE inside the source query, groups by `(output_date, shift_code, workcenter_group)`, and computes achievement_rate (PA-06/PA-07) reusing `filter_cache.get_spec_workcenter_mapping()`;
2. two new MySQL tables (target values, edit-permission whitelist) read/written directly via `core/mysql_client.get_mysql_connection()` — never via `core/sync_worker.py`;
3. a new fail-closed authorization primitive (`can_edit_targets()` + `targets_edit_required` decorator) added to existing `core/permissions.py`;
4. six REST endpoints (api-contract.md rows 256-261), a new report page, and an admin permission-management block, with all page manifests/nav wired.

All contracts (api, data-shape, business-rules, env, css, ci) are already authored and registered by the contract-reviewer stage — implementation agents conform to them, they do not re-edit them except to add response-sample rows (see Contract Updates).

## Execution Scope

### In Scope
- Backend: 3 new services + 1 SQL file + 1 routes module + permissions.py additions + DDL script (see File-Level Plan).
- Frontend: new `production-achievement/` report app, admin permission block, and the 5 manifest/registry/nav wiring edits.
- Tests: all files enumerated in test-plan.md §Test File / Case Index (backend unit/contract/integration + frontend playwright critical/resilience/data-boundary); extend `tests/test_permissions.py` per Test Update Contract.
- Env: confirm `MYSQL_OPS_*` usage; no new env var authoring needed (already in env-contract.md §MySQL OPS + env.schema.json — verify only).
- Response samples: add samples for all 6 new endpoints (incl. the `PUT /api/production-achievement/targets` 403 path) to `tests/contract/response-samples.json`.

### Out of Scope (do NOT do)
- PA-04 three-shift C-band cross-day correctness is NOT an acceptance target — implement the assumed rule per business-rules.md PA-04 and log/flag three-shift-regime queries as unverified; do not attempt production-data verification.
- No general/multi-permission framework — only the single `can_edit_targets` flag. Do NOT touch/replace `admin_required` or `login_required`.
- No new SPECNAME→大站點 map — reuse `get_spec_workcenter_mapping()` only.
- No routing of target/permission writes through `sync_worker`; no SQLite dual-layer for these tables.
- No DuckDB spool, no RQ worker, no async-job wiring, no auto-refresh/big-screen kanban, no stress/soak tests.
- Do NOT `DROP` the two MySQL tables on rollback; do NOT edit contracts beyond adding response samples.
- No refactor of `filter_cache.py`, `mysql_client.py`, or existing report pages beyond additive reuse.

## Required Changes
| id | area | required action | owner agent |
|---|---|---|---|
| IP-1 | permissions | Add `can_edit_targets(user_identifier: str \| None = None) -> bool` + `targets_edit_required` decorator to `core/permissions.py`; delegate MySQL lookup to permission service; fail closed (deny) on no-row / OPS-off / any exception; decorator returns `forbidden_error` (403). Defaults identifier to session username (design.md §Open Risks: canonical identity = `session["user"]["username"]` verbatim). | backend-engineer |
| IP-2 | persistence (permission) | New `services/production_achievement_permission_service.py` — direct-MySQL read + `INSERT ... ON DUPLICATE KEY UPDATE` on `user_identifier` for `production_achievement_edit_permissions` (data-shape §3.27). Read/write wrapped in try/except → deny/`False` (reads) or raise-for-503 (writes) when OPS off/unreachable. | backend-engineer |
| IP-3 | persistence (target) | New `services/production_achievement_target_service.py` — direct-MySQL read + upsert on `(shift_code, workcenter_group)` for `production_achievement_targets` (data-shape §3.26). Validate `target_qty` non-negative integer (400 `VALIDATION_ERROR`) before write. Read degrades to `target_qty=null` when OPS off/unreachable; write raises for 503. | backend-engineer |
| IP-4 | oracle read | New `services/production_achievement_service.py` + `sql/production_achievement.sql` — PA-05 predicate verbatim + shift_code/output_date CASE (PA-01..PA-04) in-query, `GROUP BY (output_date, shift_code, workcenter_group)`, `SUM(TRACKOUTQTY)`. Resolve workcenter_group via `filter_cache.get_spec_workcenter_mapping()` (exclude unmapped SPECNAME). Join target table + compute achievement_rate per PA-07. Also author a thin Python mirror of shift_code/output_date for unit tests (not on query hot path). 730-day date cap (SYS-04). | backend-engineer |
| IP-5 | routes | New `routes/production_achievement_routes.py` — 6 endpoints exactly per api-contract.md rows 256-261; register blueprint in `app.py`. Report/targets/filter-options reads never 500 on MySQL fault. `PUT targets` gated by `targets_edit_required`. Admin permission endpoints gated by `admin_required`. Per-endpoint MySQL-fault behavior per design.md §"Per-endpoint MySQL-failure behavior". | backend-engineer |
| IP-6 | DDL | New `scripts/sql/production_achievement_tables.sql` — idempotent `CREATE TABLE IF NOT EXISTS` for both tables, columns + unique constraints exactly per data-shape §3.26/§3.27. Applied manually pre-deploy (design.md §Migration/Rollback). Do NOT wire into `sync_worker._ensure_mysql_tables()` or app startup. | backend-engineer |
| IP-7 | frontend page | New `frontend/src/production-achievement/` report app — FilterBar (date range + shift_code + workcenter_group) + table/chart of achievement rows; model on `frontend/src/production-history/` (filter orchestration + DataTable/chart). Target-value edit UI shown/enabled only when server reports edit permission; CSS scoped under `.theme-production-achievement`. | frontend-engineer |
| IP-8 | admin block | Add permission-management block to `frontend/src/admin-pages/` (+ `admin-shared/` as needed) — list/assign/revoke `can_edit_targets` whitelist via the two admin endpoints. | frontend-engineer |
| IP-9 | nav/manifests | Additive edits: `portal-shell/navigationManifest.js` (生產輔助 drawer sub-page), `portal-shell/nativeModuleRegistry.js` (mount gate), `docs/migration/full-modernization-architecture-blueprint/asset_readiness_manifest.json`, `.../route_scope_matrix.json`, `data/page_status.json`. | frontend-engineer |
| IP-10 | tests | Author every file in test-plan.md §Test File / Case Index; extend `tests/test_permissions.py` (add `can_edit_targets` cases, do not duplicate module). Add 6 endpoint response samples (+403 sample) to `tests/contract/response-samples.json`. | backend-engineer (backend/contract/integration), frontend-engineer (playwright) |

## Source Artifact Pointers
| source | relevant pointer | used for |
|---|---|---|
| business-rules.md | §Production-Achievement Rules PA-01..PA-07 | shift_code / output_date / PA-05 predicate / grouping / achievement-rate + null semantics (implement verbatim) |
| data-shape-contract.md | §3.25 (report row), §3.26 (targets table), §3.27 (permission table) | response shape, table columns, unique constraints, OPS-off degrade rules |
| api-contract.md | rows 256-261 + change-log entry (lines 466-473) | exact 6 endpoints, auth level, params, response schema names, error codes |
| env-contract.md | §MySQL OPS (lines 63-78) | `MYSQL_OPS_ENABLED` + connection vars (verify already present; no authoring) |
| design.md | §Key Decisions, §Per-endpoint MySQL-failure behavior, §Migration/Rollback, §Open Risks | permission fail-closed, direct-MySQL rationale, DDL ownership, identity form, per-endpoint 200/503/403 matrix |
| test-plan.md | §Test File / Case Index, §Acceptance Criteria → Test Mapping, §Test Update Contract, §Test Execution Ladder | which tests to write, AC mapping, ladder phases |
| ci-gates.md | §Required Gates table, §promotion policy | verification commands / merge-blocking gates |

## File-Level Plan
| path or glob | action | notes |
|---|---|---|
| `src/mes_dashboard/core/permissions.py` | edit | Add `can_edit_targets()` + `targets_edit_required`; import service; use `forbidden_error` (already imported). Do not touch `admin_required`/`login_required`. |
| `src/mes_dashboard/services/production_achievement_permission_service.py` | create | Direct-MySQL whitelist read/upsert; fail-closed on error (IP-2). |
| `src/mes_dashboard/services/production_achievement_target_service.py` | create | Direct-MySQL target read/upsert; validation; OPS-off degrade (IP-3). |
| `src/mes_dashboard/services/production_achievement_service.py` | create | Oracle read + grouping + achievement math + Python shift/output_date mirror (IP-4). |
| `src/mes_dashboard/sql/production_achievement.sql` | create | PA-05 predicate + shift/output_date CASE + GROUP BY (IP-4). |
| `src/mes_dashboard/routes/production_achievement_routes.py` | create | 6 endpoints (IP-5). |
| `src/mes_dashboard/app.py` | edit | Register new blueprint additively. |
| `scripts/sql/production_achievement_tables.sql` | create | Idempotent DDL, both tables (IP-6). |
| `frontend/src/production-achievement/**` | create | New report app, `.theme-production-achievement` scoped CSS (IP-7). |
| `frontend/src/admin-pages/**`, `frontend/src/admin-shared/**` | edit/create | Permission-management block (IP-8). |
| `frontend/src/portal-shell/navigationManifest.js` | edit | Add 生產達成率 under 生產輔助 drawer. |
| `frontend/src/portal-shell/nativeModuleRegistry.js` | edit | Add mount gate for new app. |
| `docs/migration/full-modernization-architecture-blueprint/asset_readiness_manifest.json` | edit | Register new page. |
| `docs/migration/full-modernization-architecture-blueprint/route_scope_matrix.json` | edit | Register new route scope. |
| `data/page_status.json` | edit | Add page entry (manual add per modernization-policy). |
| `tests/test_production_achievement_*.py`, `tests/integration/test_production_achievement_*.py` | create | Backend unit/contract/integration per test-plan.md index. |
| `tests/test_permissions.py` | edit | Add `can_edit_targets` cases (Test Update Contract — additive). |
| `tests/contract/response-samples.json` | edit | Add 6 endpoint samples incl. 403 targets path. |
| `frontend/tests/playwright/production-achievement.spec.js`, `frontend/tests/playwright/resilience/production-achievement-resilience.spec.js`, `frontend/tests/playwright/data-boundary/production-achievement-data-boundary.spec.js` | create | E2E/resilience/data-boundary (paths relative to `frontend/`; live under `frontend/tests/playwright/**` per test-plan.md §Notes). |

## Contract Updates
All authored/registered by the contract-reviewer stage — implementation agents conform, do not re-author. Only mechanical additions below.
- API: api-contract.md rows 256-261 + inventory + BOTH `contracts/openapi.json` and `contracts/api/openapi.json` are already current (contract-reviewer regen done). No further edits; if any endpoint table/schema changes, re-run `cdd-kit openapi export` and regen both files.
- CSS/UI: css-contract.md/inventory already registered `.theme-production-achievement`; enforce via `css:check` Rule 6. No contract edit.
- Env: env-contract.md §MySQL OPS + env.schema.json already document `MYSQL_OPS_*`. Verify presence only; no authoring.
- Data shape: §3.25/§3.26/§3.27 already authored. Conform exactly. Add response samples to `tests/contract/response-samples.json` (this is a test artifact, not a contract edit).
- Business logic: PA-01..PA-07 already in business-rules.md (AC-8 satisfied by contract-reviewer). Implement verbatim.
- CI/CD: ci-gate-contract.md already appended the new spec to `playwright-critical-journeys`; no new gate/tier/workflow.

## Test Execution Plan
Phases (required floor): collect, targeted, changed-area, then contract, then full (final/CI). Full ladder + max-1-failure Stop Rules in test-plan.md §Test Execution Ladder; generate evidence with `cdd-kit test run` (gate validates `test-evidence.yml`). Two-stack concurrency note (CLAUDE.md): if backend + frontend agents both run `cdd-kit test run`, the later agent must re-run collect/targeted/changed-area combining both stacks' commands into single `test-evidence.yml` rows before gate sign-off.

| acceptance criterion | test file / command | expected signal |
|---|---|---|
| AC-1 (page reachable, manifests wired) | frontend/tests/playwright/production-achievement.spec.js | navigate 生產輔助 → 生產達成率, page renders |
| AC-2 (shift_code PA-01/PA-02 boundaries) | tests/test_production_achievement_shift_code.py | boundary-second + date-cutoff assertions pass |
| AC-3 (output_date PA-03/PA-04, 4/26-4/27) | tests/test_production_achievement_output_date.py | cross-midnight attribution incl. confirmed case passes |
| AC-4 (PA-05 predicate + PA-06 formula) | tests/test_production_achievement_service.py | predicate branch coverage + grouping + achievement math pass |
| AC-5 (workcenter_group via filter_cache reuse) | tests/integration/test_production_achievement_filter_cache_reuse.py | service calls `get_spec_workcenter_mapping()`, no new cache/map |
| AC-6 (target CRUD, no date dim, direct MySQL) | tests/test_production_achievement_target_service.py | upsert on `(shift_code, workcenter_group)`, no date column |
| AC-6 (MySQL round-trip + OPS-disabled fallback) | tests/integration/test_production_achievement_mysql_roundtrip.py | write→read round-trip; OPS off → read null / write 503 |
| AC-7 (permission allow/deny/fail-closed) | tests/test_production_achievement_permissions.py | whitelisted allow, others deny, OPS-off/unreachable deny, distinct from admin |
| AC-7 (403 write path + admin endpoints) | tests/test_production_achievement_routes.py | PUT targets 403 unlisted / 503 OPS-off; GET targets ungated; admin PUT requires admin |
| AC-7 (permission-gated edit e2e) | frontend/tests/playwright/production-achievement.spec.js | authorized edits, unauthorized blocked |
| AC-8 (business-rules PA-01..PA-07) | contracts/business/business-rules.md (contract-reviewer check) | entries present incl. PA-04 unverified annotation — already satisfied |

## Handoff Constraints
- Implementation agents must not infer missing requirements from chat history.
- Do not re-copy full design, test strategy, CI policy, or contract prose into this plan; follow the source pointers above.
- Permission gate MUST fail closed: deny when no whitelist row, `MYSQL_OPS_ENABLED=false`, or any MySQL exception (design.md §Key Decisions). Never fail open.
- Reuse `filter_cache.get_spec_workcenter_mapping()` for 大站點/PACKAGE grouping; do NOT hardcode a new SPECNAME map.
- PA-05 predicate must be preserved verbatim (SPECNAME + processtypename/WORKFLOWNAME combos) — not simplifiable.
- Target/permission tables read/write MySQL directly via `get_mysql_connection()`; never via `sync_worker`.
- DDL script must be idempotent `CREATE TABLE IF NOT EXISTS`; applied manually pre-deploy; not wired to startup.
- Canonical edit-permission identity = session username verbatim (`session["user"]["username"]`) on both grant and check (design.md §Open Risks).
- If this plan omits a required file, behavior, contract, or test, stop and report `blocked`.
- Keep implementation within the file-level plan unless a Context Expansion Request is approved.

## Known Risks
- DDL-drift: manual table creation means a skipped deploy step surfaces as 503 on writes / null denominators on reads (degrades safely, no 500). The write-path 503 is the operator-visible signal (design.md §Open Risks). A startup health-log when OPS enabled but tables absent is optional/non-blocking — implement only if low-cost.
- `MYSQL_OPS_ENABLED` defaults `false`; feature is inert until prod enables it (deploy precondition, not gate-enforced — ci-gates.md).
- Identity-form mismatch between admin grant and session identity silently denies — pin the canonical form (above) in both service and admin endpoint.
- CLAUDE.md: full pytest run regenerates `tests/contract/samples/`; `git checkout` unrelated sample churn and re-stage only this change's samples before commit.
- CLAUDE.md: two concurrent CDD changes bumping the same contract file's schema-version fail `validate --versions` until the other commits — coordinate if a sibling change is live.
- New `.env.example.template` / env parity: `MYSQL_OPS_*` must be identical in gunicorn AND any worker service env if referenced there (env-contract.md §Worker Feature-Flag Env-Var Parity) — this feature has no RQ worker so low risk, but keep gunicorn env authoritative.
