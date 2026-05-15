# Change Classification

## Change Types
- primary: feature (enhancement)
- secondary: behavior-change (pagination math, CSV export rows), api-additive (new `partial_count` field)

## Risk Level
- medium

## Impact Radius
- module-level (production-history report module; shared DataTable change is additive-only)

## Tier
- 2

Reasoning: Touches production-data reporting surface and changes pagination math + CSV export, but no Oracle/spool schema change, no parquet rewrite, no concurrency/queue/auth/payment surface. Raw rows remain intact in spool, so the worst-case regression is "row count display wrong, recoverable by hotfix" — not a data-corruption class. Not Tier 3 because behavior is user-observable and needs real test coverage.

## Architecture Review Required
- no
- reason: All design decisions (5-key aggregation, strict guard on non-key columns, new `partial_count` field) are locked in change-request.md. No new module boundary, no cross-service impact.

## Required Artifacts
Always required: change-request.md, change-classification.md, implementation-plan.md, test-plan.md, ci-gates.md, tasks.yml, context-manifest.md

## Optional Artifacts (default: no — set yes only with explicit reason)
| artifact | create? | reason |
|---|---|---|
| current-behavior.md | no | Raw-rows baseline documented in archived `prod-history-detail-raw-rows`; change-request references it. |
| proposal.md | no | change-request.md captures user proposal verbatim plus discussion outcome. |
| spec.md | no | No spec-level behavior shift beyond what api-contract + business-rules cover. |
| design.md | no | All design decisions locked in change-request.md. |
| qa-report.md | no | Create only if qa-reviewer reports approved-with-risk or blocked. |
| regression-report.md | no | Create only on regression finding. |
| visual-review-report.md | no | Create only on blocking visual finding. |
| monkey-test-report.md | no | Tier 2; not required. |
| stress-soak-report.md | no | Tier 2; not required. |

Artifact minimization: optional agent-log pointers used for routine review evidence.

## Required Contracts
- API: yes — add `partial_count` field to detail row schema in `contracts/api/api-contract.md`
- CSS/UI: no — badge uses existing design tokens
- Env: no
- Data shape: maybe — update `contracts/data/data-shape-contract.md` only if it enumerates detail row fields; otherwise leave as-is
- Business logic: yes — document 5-key aggregation rule + strict guard fallback in `contracts/business/business-rules.md`
- CI/CD: no — no new gate added

## Required Tests
- unit: yes — aggregation key correctness, MAX(trackout_time)/SUM(trackout_qty) math, strict-guard fallback path, partial_count = group size
- contract: yes — API response includes `partial_count`, pagination.total_rows = post-aggregation count
- integration: yes — DuckDB SQL path vs pandas fallback parity; CSV export rows match API rows 1:1
- E2E: informational — existing prod-history e2e specs run as regression; do not author new e2e unless gap discovered
- visual: yes — DataTable badge rendering snapshot (visual-reviewer)
- data-boundary: no — 5-key combination space already covered by unit fixtures
- resilience: no
- fuzz/monkey: no
- stress: no
- soak: no

## Required Agents
1. contract-reviewer — read-only; update contracts listed above
2. test-strategist — write test-plan.md mapping AC-1..AC-6 to test files
3. ci-cd-gatekeeper — write ci-gates.md
4. implementation-planner — write implementation-plan.md after the above
5. backend-engineer — DuckDB SQL path + pandas fallback + CSV export
6. frontend-engineer — DataTable partial_count badge in production-history app
7. ui-ux-reviewer — badge accessibility/contrast/placement
8. visual-reviewer — snapshot diff of detail table with mixed partial_count rows
9. qa-reviewer — release readiness verdict (always last)

## Inferred Acceptance Criteria

- AC-1: Given a single lot with multiple partial trackouts sharing `(lot_id, spec, equipment_id, trackin_time, trackin_qty)` and non-key columns all matching, the detail page returns a single row with `trackout_qty = SUM(individual partial qty)` and `trackout_time = MAX(individual trackout times)`.
- AC-2: Given an A-B-A interleaved sequence (lot A trackin at T1, partial trackout, lot B trackin/trackout, lot A trackin again at T2 with same equipment/spec), aggregation MUST NOT merge T1 and T2 rows — they remain distinct rows in the detail page.
- AC-3: Given a group with matching key columns but inconsistent non-key columns (e.g., `pj_function` differs between two partial trackouts of the same trackin), the group falls back to raw rows (no merge); the divergence is logged at INFO level with the group key.
- AC-4: `pagination.total_rows` reflects the post-aggregation row count, not the raw spool row count. Sum of `len(rows)` across all pages equals `total_rows`.
- AC-5: CSV export rows match the detail-page rows 1:1 — same aggregation key, same strict guard, same `partial_count` value.
- AC-6: Detail rows include a `partial_count` integer field (≥1). Frontend DataTable in the production-history app displays a visible badge when `partial_count > 1`.

## Tasks Not Applicable
- not-applicable: 1.3, 2.2, 2.3, 2.4, 2.6, 3.3, 3.4, 3.5, 4.3, 4.4, 6.4

Reasoning per item:
- 1.3 — no design.md required
- 2.2 — no CSS/UI contract change (badge reuses tokens)
- 2.3 — no env contract change
- 2.4 — data-shape contract likely unchanged (confirm during contract-reviewer; flip to "pending" if updates needed)
- 2.6 — no CI/CD contract change
- 3.3 — Tier 2; existing e2e runs informational regression only
- 3.4 — Tier 2; not required
- 3.5 — Tier 2; not required
- 4.3 — no env/deploy change
- 4.4 — no CI workflow changes
- 6.4 — Tier 2; no nightly/weekly/manual gates

## Clarifications or Assumptions

1. CSV export entry location TBD — backend-engineer will locate in `production_history_routes.py` / `production_history_service.py` / `production_history_job_service.py` (all in Allowed Paths).
2. `partial_count` is API-contract additive (existing consumers ignore it). Frontend DataTable change in `frontend/src/production-history/` is the primary visual touchpoint; shared DataTable component is touched only if a badge slot/prop must be added — and must remain backward-compatible (per CLAUDE.md: 9+ apps use it).
3. Strict-guard divergence logged at INFO level (not WARNING) — these are MES data quirks, not application bugs.

## Context Manifest Draft

### Affected Surfaces
- Backend: production-history report module (service + sql_runtime + routes + job_service)
- Frontend: production-history app + DataTable (additive only)
- Contracts: api / business / (data-shape if enumerated)
- Tests: unit (Python + Vitest), integration, e2e (informational)

### Allowed Paths
- specs/changes/prod-history-detail-partial-merge/
- specs/archive/2025/prod-history-detail-raw-rows/
- specs/context/
- contracts/api/
- contracts/business/
- contracts/data/
- contracts/ci/
- src/mes_dashboard/services/
- src/mes_dashboard/routes/
- src/mes_dashboard/sql/production_history/
- src/mes_dashboard/core/
- frontend/src/production-history/
- frontend/src/shared-ui/components/
- frontend/tests/
- tests/
- .github/workflows/

### Agent Work Packets

#### contract-reviewer
- specs/changes/prod-history-detail-partial-merge/
- specs/archive/2025/prod-history-detail-raw-rows/
- contracts/api/
- contracts/business/
- contracts/data/

#### test-strategist
- specs/changes/prod-history-detail-partial-merge/
- contracts/api/
- contracts/business/
- tests/
- frontend/tests/

#### ci-cd-gatekeeper
- specs/changes/prod-history-detail-partial-merge/
- contracts/ci/
- .github/workflows/

#### implementation-planner
- specs/changes/prod-history-detail-partial-merge/
- contracts/api/
- contracts/business/
- src/mes_dashboard/services/
- src/mes_dashboard/routes/
- src/mes_dashboard/sql/production_history/
- frontend/src/production-history/
- frontend/src/shared-ui/components/

#### backend-engineer
- specs/changes/prod-history-detail-partial-merge/
- contracts/api/
- contracts/business/
- contracts/data/
- src/mes_dashboard/services/
- src/mes_dashboard/routes/
- src/mes_dashboard/sql/production_history/
- src/mes_dashboard/core/
- tests/

#### frontend-engineer
- specs/changes/prod-history-detail-partial-merge/
- contracts/api/
- contracts/css/
- frontend/src/production-history/
- frontend/src/shared-ui/components/
- frontend/tests/

#### ui-ux-reviewer
- specs/changes/prod-history-detail-partial-merge/
- contracts/css/
- frontend/src/production-history/
- frontend/src/shared-ui/components/

#### visual-reviewer
- specs/changes/prod-history-detail-partial-merge/
- frontend/src/production-history/
- frontend/tests/

#### qa-reviewer
- specs/changes/prod-history-detail-partial-merge/
- contracts/
- tests/
- frontend/tests/

### Required Contracts
- contracts/api/api-contract.md (update — add partial_count field)
- contracts/business/business-rules.md (update — document 5-key aggregation + strict guard)
- contracts/data/data-shape-contract.md (read; update only if it enumerates detail row fields)

### Required Tests
- Unit: aggregation key correctness, MAX/SUM math, strict-guard fallback, partial_count count
- Integration: SQL ↔ pandas fallback parity; CSV ↔ API parity
- e2e (informational): existing production-history specs run as regression

### Context Expansion Requests
None at classification time. Allowed Paths cover all anticipated reads.
