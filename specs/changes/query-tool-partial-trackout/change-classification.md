# Change Classification

## Change Types
- primary: business-logic-change
- secondary: bug-fix, data-correction

## Risk Level
- medium

## Impact Radius
- module-level (query-tool module only; isolated to 3 SQL files + service layer)

## Tier
- 2

## Architecture Review Required
- no
- reason: The architectural pattern (4-tuple GROUP BY + CTE strict guard + partial_count) is already established in `production_history_sql_runtime.py` (commit 49f5e48). This is a mechanical port of a proven pattern, not a new design decision.

## Required Artifacts
Always required: change-request.md, change-classification.md, implementation-plan.md, test-plan.md, ci-gates.md, tasks.yml, context-manifest.md

## Optional Artifacts (default: no — set yes only with explicit reason)
| artifact | create? | reason |
|---|---|---|
| current-behavior.md | no | broken behavior fully captured in change-request §"Current behavior (broken)" |
| proposal.md | no | desired behavior specified by reference implementation |
| spec.md | no | no new product behavior; behavior is contract-driven (PH-06/PH-07) |
| design.md | no | no architecture review; mechanical port of established pattern |
| qa-report.md | no | use agent-log/qa-reviewer.yml pointer; promote only if blocking findings |
| regression-report.md | no | regression scope captured in test-plan |
| visual-review-report.md | no | no UI change |
| monkey-test-report.md | no | not applicable |
| stress-soak-report.md | no | not applicable (query-tool is on-demand, not auto-refresh/queue) |

## Required Contracts
- API: contracts/api/api-contract.md — verify query-tool responses; partial_count is additive field
- CSS/UI: none
- Env: none
- Data shape: contracts/data/data-shape-contract.md — partial_count column addition; TRACKINQTY/TRACKOUTQTY semantic correction
- Business logic: contracts/business/business-rules.md — PH-06/PH-07 must enumerate query-tool surfaces
- CI/CD: none (existing gates inventory remains valid)

## Required Tests
- unit: yes — SQL runtime helper functions; aggregation guard logic
- contract: yes — verify PH-06/PH-07 apply to query-tool's three SQL paths; API/data-shape partial_count field
- integration: yes — full lot_history / equipment_lots / adjacent_lots paths with realistic partial-trackout fixtures (different TRACKINQTY per partial)
- E2E: no (no UI change; integration sufficient)
- visual: no
- data-boundary: yes — divergent-non-key-columns fixture must trigger raw-row fallback with partial_count=1
- resilience: no
- fuzz/monkey: no
- stress: no
- soak: no

## Required Agents
- contract-reviewer
- test-strategist
- backend-engineer
- ci-cd-gatekeeper
- implementation-planner
- qa-reviewer

## Inferred Acceptance Criteria
- AC-1: lot_history.sql aggregates same-TRACKINTIMESTAMP partials by 4-tuple (CONTAINERID, EQUIPMENTID, SPECNAME, TRACKINTIMESTAMP), returning TRACKINQTY=MAX, TRACKOUTQTY=SUM, TRACKOUTTIMESTAMP=MAX, and partial_count=COUNT(*).
- AC-2: equipment_lots.sql applies the identical 4-tuple aggregation with the same column semantics as AC-1.
- AC-3: adjacent_lots.sql applies 3-tuple aggregation (CONTAINERID, EQUIPMENTID, TRACKINTIMESTAMP) on the inner dedup layer while preserving the outer relative-position ROW_NUMBER's neighbor-selection behavior.
- AC-4: When any non-key column diverges within a group (e.g., EQUIPMENTNAME differs between partials of the same TRACKINTIMESTAMP), the strict guard (PH-07) falls back to raw rows with partial_count=1 for each affected partial; no merge occurs.
- AC-5: A fixture with TRACKINQTY decrementing across partials (e.g., 99424 → 26624 via TRACKOUTQTY=72800) yields TRACKINQTY=99424 and TRACKOUTQTY=72800 after aggregation across all three SQL paths.
- AC-6: At least one decrementing-TRACKINQTY fixture exists per SQL file, ensuring 4-tuple-vs-5-tuple discrimination (CLAUDE.md fixture-discipline).
- AC-7: API response shape from query-tool routes includes partial_count (additive); existing TRACKINQTY/TRACKOUTQTY field names unchanged.
- AC-8: business-rules.md (PH-06/PH-07) and data-shape-contract.md are updated to enumerate query-tool's three SQL paths alongside production-history.

## Tasks Not Applicable
- not-applicable: 1.3, 2.2, 2.3, 2.6, 3.3, 3.5, 4.2, 4.3, 5.1, 5.2

## Clarifications or Assumptions
1. Frontend partial_count display is out of scope by default. Backend exposes partial_count as additive field; frontend is no-op if it ignores it.
2. adjacent_lots.sql 3-tuple is intentional — dedup layer feeds a relative-position ROW_NUMBER; aggregation must occur inside dedup CTE without disturbing the outer ORDER/PARTITION.
3. Reference implementation in production_history_sql_runtime.py (commit 49f5e48) is the canonical pattern; backend-engineer should mirror its CTE structure, strict-guard column-list, and partial_count column.
4. No spool parquet schema break — query-tool runs SQL on Oracle on-demand with no persisted parquet. Confirm during implementation; if spool path exists, add post-deploy cleanup to ci-gates.md §Rollback.
5. PH-06/PH-07 in business-rules.md and partial_count in data-shape-contract.md must enumerate query-tool surfaces.

## Context Manifest Draft

### Affected Surfaces
- query-tool backend (SQL + service runtime)
- query-tool API response shape (additive partial_count)
- business-rules contract (PH-06/PH-07 scope extension to query-tool)
- data-shape contract (partial_count field)

### Allowed Paths
- specs/changes/query-tool-partial-trackout/
- specs/context/project-map.md
- specs/context/contracts-index.md
- src/mes_dashboard/sql/query_tool/
- src/mes_dashboard/services/query_tool_service.py
- src/mes_dashboard/services/query_tool_sql_runtime.py
- src/mes_dashboard/services/production_history_sql_runtime.py
- src/mes_dashboard/routes/query_tool_routes.py
- tests/
- contracts/api/api-contract.md
- contracts/business/business-rules.md
- contracts/data/data-shape-contract.md
- contracts/ci/ci-gate-contract.md
