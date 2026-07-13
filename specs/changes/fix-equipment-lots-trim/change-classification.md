# Change Classification

## Change Types
- primary: bug-fix (data), feature-enhancement (additive optional `container_names` request field on an existing endpoint)
- secondary: refactor (server-side push-down filter wired through sync route + async RQ job for parity)

Note: this is symptom-driven, so `## Lane` is `bug-fix`. Because part 3 requires an additive API contract change, `feature-enhancement` is co-listed as a primary change-type to force the contract path without discarding the bug-fix lane routing.

## Lane
- bug-fix

## Bug Symptom Type
- data

## Diagnostic Only
- no

## Bug Evidence Required
- symptom: 生產紀錄 (production-records) sub-tab of query-tool "批次追蹤生產設備" renders correct columns with zero rows after equipment resolves successfully ("找到 25 台設備")
- expected behavior: production records for the resolved equipment/containers render as non-empty rows
- actual behavior: every row is filtered out client-side; zero rows displayed
- reproduction status: root cause already confirmed by prior investigation; this is confirmation-of-fix, not re-diagnosis
- hypotheses: already resolved — untrimmed Oracle CHAR-padded `c.CONTAINERNAME` in `equipment_lots.sql` fails the exact-match `Set.has()` client filter against already-trimmed lot names
- root cause pointer: `src/mes_dashboard/sql/query_tool/equipment_lots.sql` selects `c.CONTAINERNAME` without `TRIM()`; compounded by exact-match filter in `frontend/src/query-tool/composables/useLotEquipmentQuery.ts` (`queryLots()`/`queryRejects()`)
- regression evidence: backend + frontend regression tests proving CHAR-padded / case-variant `CONTAINERNAME` values match after the fix (part 4)

## Risk Level
- medium

## Impact Radius
- cross-module (SQL + Python service/route + async RQ job path + Vue/TS composable + API contract)

## Tier
- 2

## Architecture Review Required
- no
- reason: n/a — the push-down design, sync/async parity requirement, and pagination-clamp mitigation are already decided and documented in the approved four-part fix scope; no open module-boundary or data-flow decision remains

## Required Artifacts
Always required: change-request.md, change-classification.md, implementation-plan.md, test-plan.md, ci-gates.md, tasks.yml, context-manifest.md

## Optional Artifacts (default: no — set yes only with explicit reason)
| artifact | create? | reason |
|---|---|---|
| current-behavior.md | no | root cause already documented in change-request.md; no separate investigation needed |
| proposal.md | no | fix scope already approved by user ("四個都做") |
| spec.md | no | no separate product/behavior decision |
| design.md | no | no architecture review required |
| qa-report.md | no | routine pass/fail belongs in agent-log/qa-reviewer.yml; promote only on blocking/approved-with-risk findings |
| regression-report.md | no | regression tests are in-scope; record evidence via test-evidence.yml unless a blocking regression is found |
| visual-review-report.md | no | data fix, no visual/layout change |
| monkey-test-report.md | no | not applicable |
| stress-soak-report.md | no | existing async path; no new load surface |

## Required Contracts
- API: contracts/api/api-contract.md — additive optional `container_names: List[str]` on `POST /api/query-tool/equipment-period` (`query_type='lots'`); Compatibility Notes entry + schema-version bump; contracts/CHANGELOG.md entry
- CSS/UI: none
- Env: none
- Data shape: none (TRIM cleans the value of an existing column; no schema/row-shape change)
- Business logic: none (read-only reference to QT-05/QT-06 semantics in contracts/business/business-rules.md)
- CI/CD: none

## Required Tests
- unit: yes — service-level TRIM correctness + `container_names` `UPPER(TRIM(...)) IN (...)` filter in tests/test_query_tool_service.py; route forwarding (per-kwarg, non-default) in tests/test_query_tool_routes.py
- contract: yes — new optional request field on `POST /api/query-tool/equipment-period`
- integration: yes — sync route ↔ async RQ job parity for the new filter (tests/integration/test_query_tool_rq_async.py); mocked-enqueue tests must also `inspect.signature(worker_fn).bind(**kwargs)` per test-discipline
- E2E: no
- visual: no
- data-boundary: yes — CHAR-padded / case-variant CONTAINERNAME boundary matching (backend + new frontend test under frontend/tests/query-tool/)
- resilience: no
- fuzz/monkey: no
- stress: no
- soak: no

## Required Agents
- bug-fix-engineer — first implementation agent (records confirmation evidence; treats root cause as already documented, not re-diagnosed)
- implementation-planner — turns the four-part fix into the execution packet before backend/frontend agents run
- backend-engineer — SQL TRIM fix, get_equipment_lots() container_names push-down, sync route + async RQ job wiring
- frontend-engineer — defensive .trim() in queryLots()/queryRejects() + new composable test
- test-strategist — acceptance-criteria to test mapping, regression coverage on both stacks
- contract-reviewer — additive API contract change review (optional field, schema-version bump, CHANGELOG)
- qa-reviewer — release readiness

## Inferred Acceptance Criteria
- AC-1: After the SQL fix, equipment_lots.sql returns CONTAINERNAME trimmed of Oracle CHAR blank-padding (matching the sibling TRIM(c.PRODUCTLINENAME) treatment).
- AC-2: The production-records (生產紀錄) sub-tab renders non-empty rows for equipment/containers that previously resolved but showed zero rows, using the reported 21-work-order / 6-workcenter-group scenario shape.
- AC-3: queryLots()/queryRejects() in useLotEquipmentQuery.ts apply .trim() before .toUpperCase() so CHAR-padded values still match even if an upstream source is untrimmed.
- AC-4: get_equipment_lots() accepts an optional container_names: List[str] and, when provided, narrows via UPPER(TRIM(c.CONTAINERNAME)) IN (...); the filter is applied identically on the sync route and the async RQ job path.
- AC-5: Server-side narrowing occurs before the QUERY_TOOL_DETAIL_MAX_PER_PAGE (500) pagination clamp, so relevant rows are not silently dropped when the frontend requests per_page=9999.
- AC-6: The endpoint remains backward-compatible — omitting container_names yields identical behavior to before (no breaking change, no new endpoint).
- AC-7: Backend and frontend regression tests assert CHAR-padded and case-variant CONTAINERNAME values match correctly after the fix.

## Tasks Not Applicable
- not-applicable: 1.3, 2.2, 2.3, 2.4, 2.5, 2.6, 3.3, 3.5, 4.3, 4.4, 5.1, 5.2

(1.3 no design review; 2.2/2.3/2.6 no CSS/env/CI contract; 2.4 no data-shape change; 2.5 business-rules is read-only reference; 3.3 E2E/resilience not required; 3.5 no stress/soak; 4.3/4.4 no env/deploy or CI-workflow change; 5.1/5.2 no UI/visual change — data-only fix.)

## Clarifications or Assumptions
- Assumption: POST /api/query-tool/equipment-period with query_type='lots' is the endpoint backing this tab (per change-request); contract-reviewer should confirm the exact endpoint row in api-contract.md when editing.
- Assumption: no data-shape contract entry is needed because only the value (trimmed) changes, not columns/row shape. If contract-reviewer finds CONTAINERNAME value formatting is pinned in data-shape-contract.md, add 2.4 back and include a data-shape review note.
- Assumption: existing tests/integration/test_query_tool_rq_async.py is the correct home for sync/async parity coverage of the new filter; if a dedicated file is preferred, keep it under tests/integration/.
- The bug-fix lane is retained per the task directive; the co-listed feature-enhancement primary type exists solely to force the additive API contract path and does not downgrade the bug-fix routing (bug-fix-engineer remains the first implementation agent).

## Context Manifest Draft

### Affected Surfaces
- query-tool Equipment Lot Tracking (SQL + Python service/route + async RQ job)
- query-tool frontend composable (useLotEquipmentQuery.ts)
- API contract (POST /api/query-tool/equipment-period)

### Allowed Paths
<!-- directory-level only, no globs, per docs/cdd-kit-patterns.md convention -->
- specs/changes/fix-equipment-lots-trim/
- specs/context/project-map.md
- specs/context/contracts-index.md
- src/mes_dashboard/sql/
- src/mes_dashboard/services/
- src/mes_dashboard/routes/
- tests/
- tests/integration/
- frontend/src/query-tool/
- frontend/tests/query-tool/
- contracts/

### Agent Work Packets

#### bug-fix-engineer
- specs/changes/fix-equipment-lots-trim/
- src/mes_dashboard/sql/
- src/mes_dashboard/services/
- src/mes_dashboard/routes/
- frontend/src/query-tool/
- contracts/

#### implementation-planner
- specs/changes/fix-equipment-lots-trim/
- specs/context/project-map.md
- specs/context/contracts-index.md

#### backend-engineer
- specs/changes/fix-equipment-lots-trim/
- src/mes_dashboard/sql/
- src/mes_dashboard/services/
- src/mes_dashboard/routes/
- tests/
- tests/integration/
- contracts/

#### frontend-engineer
- specs/changes/fix-equipment-lots-trim/
- frontend/src/query-tool/
- frontend/tests/query-tool/

#### test-strategist
- specs/changes/fix-equipment-lots-trim/
- tests/
- tests/integration/
- frontend/tests/query-tool/

#### contract-reviewer
- specs/changes/fix-equipment-lots-trim/
- contracts/

#### qa-reviewer
- specs/changes/fix-equipment-lots-trim/
- contracts/

### Context Expansion Requests
- none at classification time — the project-map and contracts-index resolve every candidate path above
