# Change Classification

## Change Types
- primary: bug-fix
- secondary: business-logic-change

## Risk Level
- medium

## Impact Radius
- module-level

## Tier
- 2

## Architecture Review Required
- yes
- reason: The change-request carries an explicit open question for spec-architect — choice between (a) a single DuckDB `GROUP BY GROUPING SETS` query emitting `COUNT(DISTINCT CONTAINERNAME)` for all six grain combinations, (b) per-level distinct-count queries, or (c) raw-rows + Python distinct-set aggregation. This correctness/perf/maintainability tradeoff must be decided before implementation, and both code paths (DuckDB SQL + pandas fallback) must converge on identical results. The decision also constrains how the data-shape contract phrases the `COUNT(DISTINCT CONTAINERNAME)` semantics.

## Required Artifacts
Always required: change-request.md, change-classification.md, test-plan.md, ci-gates.md, tasks.yml

## Optional Artifacts (default: no — set yes only with explicit reason)
| artifact | create? | reason |
|---|---|---|
| current-behavior.md | yes | Correctness bug in shipped behavior; the incorrect SUM-up-hierarchy aggregation must be documented as the pre-change baseline to anchor regression scope and the failing-test reproduction. |
| proposal.md | yes | Open architectural question (GROUPING SETS vs per-level queries vs raw-rows+Python) requires a written decision with rationale before implementation; spec-architect output lands here. |
| spec.md | no | Node shape returned to frontend is unchanged; behavior fully captured by the data-shape contract update + business rule PH-02. |
| design.md | no | proposal.md covers the approach; the change is confined to two functions in one file. |
| qa-report.md | yes | Correctness bug fix with a precise success criterion and dual-code-path parity requirement — QA must record verified evidence for both DuckDB and pandas paths. |
| regression-report.md | yes | Existing shipped behavior is being changed; leaf-grain values, detail table, cross-filter cache, and matrix node shape must be confirmed unaffected. |

## Required Contracts
- API: none (no endpoint or payload-shape change)
- CSS/UI: none
- Env: none
- Data shape: `contracts/data/data-shape-contract.md` — make the matrix `COUNT(DISTINCT CONTAINERNAME)` semantics precise: parent-level (workcenter, spec) `count` and `month_counts` are distinct-counts re-evaluated at that grain, not sums of child counts.
- Business logic: `contracts/business/business-rules.md` — PH-02 lot-count semantics must state that distinct LOT-ID counts are non-additive across hierarchy levels.
- CI/CD: none

## Required Tests
- unit: yes — `compute_matrix_view` / `_build_matrix_tree` distinct-count assignment per grain; `_pandas_matrix_view` parity for the same fixture.
- contract: yes — data-shape contract assertion that parent `count`/`month_counts` equal independent distinct-counts; business-rule PH-02 assertion.
- integration: yes — DuckDB SQL path vs pandas fallback produce identical matrix trees for the same input rows.
- E2E: no — no UI/route behavior change; matrix node shape unchanged.
- visual: no — no UI change.
- data-boundary: yes — LOT spanning multiple specs/equipment, single-row input, empty input, overlapping month buckets.
- resilience: no
- fuzz/monkey: no
- stress: no — pure aggregation correctness fix.
- soak: no

## Required Agents
- spec-architect — resolve the open architectural question; author proposal.md.
- test-strategist — populate test-plan.md and the AC → test mapping, including the failing-test reproduction.
- backend-engineer — implement the fix in `production_history_sql_runtime.py` (`compute_matrix_view`, `_build_matrix_tree`, `_pandas_matrix_view`).
- contract-reviewer — review data-shape contract + business-rule PH-02 updates.
- qa-reviewer — verify success criterion and dual-code-path parity; author qa-report.md and regression-report.md.

## Inferred Acceptance Criteria
- AC-1: A LOT ID that passes through 3 SPECs under one workcenter shows `count = 1` at each of those 3 SPEC nodes and `count = 1` at the workcenter node (not 3).
- AC-2: A LOT ID that passes through 2 equipment under one SPEC shows `count = 1` at that SPEC node (not 2); equipment-level leaf counts remain unchanged and correct.
- AC-3: `month_counts` at every hierarchy level (equipment, spec, workcenter) is a `COUNT(DISTINCT CONTAINERNAME)` independently evaluated at that grain × month, not a sum of child month_counts.
- AC-4: The DuckDB SQL path (`compute_matrix_view`) and the pandas fallback (`_pandas_matrix_view`) produce identical matrix trees for the same input rows.
- AC-5: The matrix tree node shape returned to the frontend is unchanged — still `{label, level, count, month_counts, children}`; only the `count` / `month_counts` values change.
- AC-6: Leaf (equipment × month) grain counts are unchanged from current behavior (already correct).
- AC-7: The data-shape contract and business rule PH-02 are updated to state that parent-level distinct-counts are non-additive and re-evaluated per grain.

## Tasks Not Applicable
- not-applicable: 2.1, 2.2, 2.3, 2.6, 3.3, 3.5, 4.2, 4.3, 4.4, 5.1, 5.2, 6.4

## Clarifications or Assumptions
- CER-001 resolved by main Claude: `tests/test_production_history_sql_runtime.py` exists — it is the canonical test file for the matrix functions.
- CER-002 resolved by main Claude: `frontend/src/production-history/components/ProductionMatrix.vue` exists and consumes `count`/`month_counts` per node; node shape is unchanged so no frontend edit — regression-report asserts non-impact from the contract/test evidence, no frontend read required.
- The matrix SQL is built inline within `production_history_sql_runtime.py` (the `sql/production_history/` directory holds only `main_query.sql` / `count_query.sql`); the `sql/production_history/` allowed path is harmless if unused.
- "data-boundary tests" here means table-level aggregation correctness fixtures within pytest, not the frontend `tests/playwright/data-boundary/` suite.

## Context Manifest Draft

### Affected Surfaces
- Production History Workcenter × Equipment Matrix aggregation (backend service layer)
- Data-shape contract: matrix `COUNT(DISTINCT CONTAINERNAME)` semantics
- Business rule PH-02: lot-count semantics

### Allowed Paths
- specs/changes/fix-matrix-distinct-count/
- specs/context/project-map.md
- specs/context/contracts-index.md
- src/mes_dashboard/services/production_history_sql_runtime.py
- src/mes_dashboard/sql/production_history/
- contracts/data/data-shape-contract.md
- contracts/business/business-rules.md
- tests/test_production_history_sql_runtime.py
- tests/test_api_contract.py

### Agent Work Packets

#### change-classifier
- specs/changes/fix-matrix-distinct-count/
- specs/context/project-map.md
- specs/context/contracts-index.md

#### spec-architect
- specs/changes/fix-matrix-distinct-count/
- specs/context/project-map.md
- specs/context/contracts-index.md
- src/mes_dashboard/services/production_history_sql_runtime.py
- src/mes_dashboard/sql/production_history/
- contracts/data/data-shape-contract.md
- contracts/business/business-rules.md

#### test-strategist
- specs/changes/fix-matrix-distinct-count/
- src/mes_dashboard/services/production_history_sql_runtime.py
- tests/test_production_history_sql_runtime.py
- tests/test_api_contract.py
- contracts/data/data-shape-contract.md
- contracts/business/business-rules.md

#### backend-engineer
- specs/changes/fix-matrix-distinct-count/
- src/mes_dashboard/services/production_history_sql_runtime.py
- src/mes_dashboard/sql/production_history/
- tests/test_production_history_sql_runtime.py
- tests/test_api_contract.py
- contracts/data/data-shape-contract.md
- contracts/business/business-rules.md

#### contract-reviewer
- specs/changes/fix-matrix-distinct-count/
- contracts/data/data-shape-contract.md
- contracts/business/business-rules.md

#### ci-cd-gatekeeper
- specs/changes/fix-matrix-distinct-count/
- contracts/ci/

#### qa-reviewer
- specs/changes/fix-matrix-distinct-count/
- src/mes_dashboard/services/production_history_sql_runtime.py
- tests/test_production_history_sql_runtime.py
- contracts/data/data-shape-contract.md
- contracts/business/business-rules.md
