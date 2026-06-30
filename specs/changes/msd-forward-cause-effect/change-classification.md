# Change Classification

## Change Types
- primary: feature-add, business-logic-change
- secondary: bug-fix (per-CONTAINERID attribution correctness hole), ui-only-change (Sankey/heatmap/KPI/detail-column), data-shape-change (new aggregations + lineage spool schema), refactor (in-memory forward → DuckDB migration)

## Risk Level
- high

## Impact Radius
- cross-module

## Tier
- 1

## Architecture Review Required
- yes
- reason: New DuckDB forward-lineage stage spool (schema + key-anchor decision: detection defect-lot vs seed root), RQ async worker spool orchestration on a concurrency-critical surface (`execute_trace_events_job`, package-independent trace cache), and retirement of the in-memory forward summary path (data-flow + module-boundary change) are non-obvious design decisions with rollback / parquet-schema-version implications. Amplification-KPI divide-by-zero semantics and Sankey/heatmap Top-N truncation are also design-level. Must be settled in `design.md` before implementation planning.

## Required Artifacts
Always required: change-request.md, change-classification.md, implementation-plan.md, test-plan.md, ci-gates.md, tasks.yml, context-manifest.md

## Optional Artifacts (default: no — set yes only with explicit reason)
| artifact | create? | reason |
|---|---|---|
| current-behavior.md | no | Current forward behavior captured in change-request + design.md; no separate investigation. |
| proposal.md | no | Scope already decided by user (single change, 3b dropped); open items are design-level. |
| spec.md | no | No separate user-facing spec beyond design + acceptance criteria. |
| design.md | yes | Architecture Review Required = yes. Lineage spool schema/anchor, DuckDB summary migration, RQ orchestration, amplification + Top-N decided here. Background design analysis (data model + DuckDB SQL draft + UX mockup) is input. |
| qa-report.md | no | Routine pass/fail → `agent-log/qa-reviewer.yml`; promote only on blocking/approved-with-risk. |
| regression-report.md | no | xfail-flip + re-keyed attribution regression scope → test-plan entries + agent-log unless a blocking regression appears. |
| visual-review-report.md | yes | Net-new ECharts Sankey hero + heatmap toggle + KPI cards with interaction; durable visual evidence bundle warranted. |
| monkey-test-report.md | no | Cross-filter fuzz covered by Playwright + agent-log notes. |
| stress-soak-report.md | yes | New DuckDB stage spool + RQ async worker orchestration is concurrency-critical (CLAUDE.md promoted learning). Scope = spool write + concurrency/cache surface, NOT enlarged-fetch (3b dropped). |

Artifact minimization: qa-report / regression-report / monkey-test-report → `agent-log/*.yml`. Only design / visual-review / stress-soak are `yes`.

## Required Contracts
- API: `contracts/api/api-contract.md` + `contracts/api/openapi.json` (+ `contracts/api/openapi.json` mirror) + `contracts/api/api-inventory.md` — forward analysis response gains new aggregation fields (`by_detection_loss_reason`, detection-loss-reason × workcenter-group cross-tab, downstream trend, amplification KPI); detail response gains "detection loss reason" column.
- CSS/UI: `contracts/css/css-contract.md` + `contracts/css/css-inventory.md` — new ECharts Sankey/Heatmap components scoped under `.theme-mid-section-defect`; new CSS source files added to css-inventory.
- Env: none — no new env var/flag (no enlarged-fetch flag; spool reuses existing trace-worker env). If a flag IS introduced for the DuckDB-forward cutover, promote env to required + add to `env.schema.json` (enum+default).
- Data shape: `contracts/data/data-shape-contract.md` — forward lineage spool schema (`SEED_ID, DESCENDANT_ID`), re-keyed downstream aggregations, cross-tab/trend payload shapes, amplification KPI field (incl. divide-by-zero representation).
- Business logic: `contracts/business/business-rules.md` — forward downstream attribution now follows lineage (split/merge/rename descendants re-keyed to seed detection lot) instead of per-CONTAINERID-only; amplification = downstream rate ÷ detection rate with defined divide-by-zero; Top-N truncation rule.
- CI/CD: none expected — reuses existing msd/trace worker + stress/soak gates. Revisit only if a new gate is added for the spool.

## Required Tests
- unit: forward `_attribute_forward_defects` lineage re-keying; amplification KPI math incl. divide-by-zero; new aggregation builders (`by_detection_loss_reason`, loss-reason × workcenter-group cross-tab, downstream trend).
- contract: MSD forward analysis + detail response-sample regeneration; openapi sync; lineage spool data-shape conformance.
- integration: `get_summary(direction="forward")` via DuckDB end-to-end (spool write → DuckDB summary → re-keyed attribution); forward lineage spool write/read; RQ async `execute_trace_events_job` orchestration with package-independent trace cache.
- E2E: Sankey click cross-filter, heatmap toggle, KPI render, detail "detection loss reason" column.
- visual: Sankey hero, heatmap, amplification KPI cards (visual-review bundle).
- data-boundary: empty/zero detection (divide-by-zero amplification), no-descendant lineage, Top-N truncation boundary, malformed lineage rows.
- resilience: spool-miss / Oracle fallback for forward path; RQ worker failure mid-orchestration.
- fuzz/monkey: Sankey/heatmap cross-filter interaction sequences (Playwright; no separate report).
- stress: spool concurrency + DuckDB forward summary under load.
- soak: spool + concurrency surface soak (NOT enlarged-fetch).

> Tripwire: the 2 currently `xfail(strict=True)` forward-summary spool tests MUST be flipped to passing (markers removed) when the DuckDB forward path lands. Removing the markers is an explicit task and AC-6.

## Required Agents
- spec-architect — `design.md` (lineage spool schema/anchor, DuckDB migration, RQ orchestration, amplification + Top-N) before planning.
- implementation-planner — execution packet from design + contracts + tests.
- backend-engineer — `mid_section_defect_service.py`, `msd_duckdb_runtime.py`, `trace_job_service.py`, routes; lineage spool, re-keying, DuckDB forward summary, aggregations.
- frontend-engineer — `frontend/src/mid-section-defect/` Sankey/Heatmap/KPI/detail-column.
- test-strategist — AC → test mapping; xfail flip, divide-by-zero, lineage re-keying, data-boundary.
- contract-reviewer — api/data/business/css diffs + openapi sync + response-sample regen.
- ui-ux-reviewer — Sankey click cross-filter, heatmap toggle, KPI (WAI-ARIA, i18n sync).
- visual-reviewer — Sankey/heatmap/KPI visual bundle.
- stress-soak-engineer — spool + concurrency stress/soak (scoped, no enlarged-fetch).
- e2e-resilience-engineer — DuckDB forward path + RQ orchestration resilience/fallback.
- ci-cd-gatekeeper — openapi-sync, css:check, contract validators, stress/soak gate wiring.
- qa-reviewer — release readiness, regression sign-off.

## Inferred Acceptance Criteria
- AC-1: Forward answers ① — `by_detection_loss_reason` aggregation/chart shows what was scrapped at the front (detection station) by `LOSSREASONNAME` (forward currently lacks it).
- AC-2: Forward answers ② — `[detection LOSSREASONNAME] × [downstream WORKCENTER_GROUP]` cross-tab links each front reject reason to downstream-station impact (reject count + rate).
- AC-3: Forward answers ③ — a downstream-reject trend shows how downstream scrap varies over time, WITHOUT any control/cohort/lift baseline (explicitly out of scope).
- AC-4: Lineage-correct attribution — downstream rejects of split/merge/rename descendant containers are re-keyed to the seed detection lot via a forward lineage stage spool (`SEED_ID, DESCENDANT_ID`); per-CONTAINERID-only attribution no longer drops descendant rejects. Failing test demonstrates the old drop, passes after the fix; regression test guards it.
- AC-5: `get_summary(direction="forward")` executes via DuckDB (in-memory forward summary path retired); output matches the new contract.
- AC-6: The 2 currently `xfail(strict=True)` forward-summary spool tests are flipped to passing and markers removed (CI green).
- AC-7: Amplification KPI = downstream reject rate ÷ detection reject rate, with explicitly defined and tested divide-by-zero semantics (detection rate = 0) for value and display.
- AC-8: Frontend renders Sankey hero (front reason → downstream station; click cross-filters) + heatmap toggle + amplification KPI + detail "detection loss reason" column; CSS scoped under `.theme-mid-section-defect`, charts via vue-echarts (`@click` on `<VChart>`), new user-visible text synced across all i18n locales, Top-N truncation keeps Sankey/heatmap readable.

## Tasks Not Applicable
- not-applicable: env-contract / `.env.example` authoring tasks (no new env var/flag — revisit only if a DuckDB-forward cutover flag is introduced); proposal.md / current-behavior.md / spec.md authoring tasks (those artifacts = no). Design task 1.3 IS applicable (Architecture Review = yes). Concrete IDs resolved against the scaffolded `tasks.yml`.

## Clarifications or Assumptions
- Assumption: no new env var/flag (DuckDB-forward replaces in-memory directly). If a cutover flag is used → env becomes a Required Contract, flag lands in `env.schema.json` (enum+default), and CLAUDE.md requires a `tier-floor-override` for the flag-off period.
- Assumption: Oracle fetch scope unchanged (3b dropped) — stress/soak scoped to spool concurrency + DuckDB forward summary + cache reuse, not enlarged-fetch.
- Open (→ design.md): (1) lineage spool `SEED_ID` anchor = detection defect-lot vs seed root; (2) amplification divide-by-zero display/semantics; (3) Sankey/heatmap Top-N truncation threshold.
- Implementer reminders (CLAUDE.md): regen BOTH `contracts/openapi.json` AND `contracts/api/openapi.json` after any endpoint/schema/schema-version edit; `git checkout tests/contract/samples/` to revert unrelated sample churn; new `register_job_type()` for the lineage spool job updates `tests/test_job_registry.py` count + `_APPROVED_CALLERS` in `tests/test_query_cost_policy.py`; spool/DuckDB paths must work in host AND Docker.

## Context Manifest Draft

### Affected Surfaces
- MSD forward-direction analysis (backend service + DuckDB runtime + trace spool orchestration)
- MSD API surface (forward analysis + detail responses)
- MSD frontend (mid-section-defect Vue app: Sankey/Heatmap/KPI/DetailTable)
- Trace async worker / spool layer (forward lineage stage spool, package-independent trace cache)
- Contracts: api, data, business, css

### Allowed Paths
- specs/changes/msd-forward-cause-effect/
- specs/context/project-map.md
- specs/context/contracts-index.md
- src/mes_dashboard/services/mid_section_defect_service.py
- src/mes_dashboard/services/msd_duckdb_runtime.py
- src/mes_dashboard/services/msd_lineage_job_service.py
- src/mes_dashboard/services/msd_seed_job_service.py
- src/mes_dashboard/services/trace_job_service.py
- src/mes_dashboard/services/event_fetcher.py
- src/mes_dashboard/services/lineage_engine.py
- src/mes_dashboard/routes/mid_section_defect_routes.py
- src/mes_dashboard/routes/trace_routes.py
- src/mes_dashboard/sql/mid_section_defect/
- src/mes_dashboard/sql/lineage/
- frontend/src/mid-section-defect/
- contracts/api/api-contract.md
- contracts/api/api-inventory.md
- contracts/api/openapi.json
- contracts/data/data-shape-contract.md
- contracts/business/business-rules.md
- contracts/css/css-contract.md
- contracts/css/css-inventory.md
- contracts/CHANGELOG.md
- tests/test_mid_section_defect_service.py
- tests/integration/test_material_trace_rq_async.py
- tests/stress/test_mid_section_defect_stress.py
- tests/e2e/test_mid_section_defect_e2e.py
- tests/contract/samples/
- frontend/tests/legacy/mid-section-defect-composables.test.js
- frontend/tests/legacy/msd-completeness-warning.test.js
- frontend/tests/playwright/mid-section-defect.spec.ts

### Agent Work Packets

#### change-classifier
- specs/changes/msd-forward-cause-effect/
- specs/context/project-map.md
- specs/context/contracts-index.md

#### spec-architect
- specs/changes/msd-forward-cause-effect/
- specs/context/project-map.md
- specs/context/contracts-index.md
- contracts/data/data-shape-contract.md
- contracts/business/business-rules.md
- contracts/api/api-contract.md
- src/mes_dashboard/services/mid_section_defect_service.py
- src/mes_dashboard/services/msd_duckdb_runtime.py
- src/mes_dashboard/services/trace_job_service.py

#### implementation-planner
- specs/changes/msd-forward-cause-effect/
- contracts/api/api-contract.md
- contracts/data/data-shape-contract.md
- contracts/business/business-rules.md
- contracts/css/css-contract.md

#### backend-engineer
- specs/changes/msd-forward-cause-effect/
- src/mes_dashboard/services/mid_section_defect_service.py
- src/mes_dashboard/services/msd_duckdb_runtime.py
- src/mes_dashboard/services/msd_lineage_job_service.py
- src/mes_dashboard/services/msd_seed_job_service.py
- src/mes_dashboard/services/trace_job_service.py
- src/mes_dashboard/services/event_fetcher.py
- src/mes_dashboard/services/lineage_engine.py
- src/mes_dashboard/routes/mid_section_defect_routes.py
- src/mes_dashboard/routes/trace_routes.py
- src/mes_dashboard/sql/mid_section_defect/
- src/mes_dashboard/sql/lineage/
- tests/test_mid_section_defect_service.py
- tests/integration/test_material_trace_rq_async.py
- tests/contract/samples/
- contracts/api/
- contracts/data/
- contracts/business/

#### frontend-engineer
- specs/changes/msd-forward-cause-effect/
- frontend/src/mid-section-defect/
- frontend/tests/legacy/mid-section-defect-composables.test.js
- frontend/tests/playwright/mid-section-defect.spec.ts
- contracts/css/css-contract.md
- contracts/css/css-inventory.md

#### test-strategist
- specs/changes/msd-forward-cause-effect/
- tests/test_mid_section_defect_service.py
- tests/integration/test_material_trace_rq_async.py
- tests/stress/test_mid_section_defect_stress.py
- tests/e2e/test_mid_section_defect_e2e.py
- frontend/tests/playwright/mid-section-defect.spec.ts

#### stress-soak-engineer
- specs/changes/msd-forward-cause-effect/
- tests/stress/test_mid_section_defect_stress.py
- tests/integration/test_soak_workload.py

#### e2e-resilience-engineer
- specs/changes/msd-forward-cause-effect/
- tests/e2e/test_mid_section_defect_e2e.py
- frontend/tests/playwright/mid-section-defect.spec.ts

#### contract-reviewer
- specs/changes/msd-forward-cause-effect/
- contracts/

#### ui-ux-reviewer
- specs/changes/msd-forward-cause-effect/
- frontend/src/mid-section-defect/
- contracts/css/

#### visual-reviewer
- specs/changes/msd-forward-cause-effect/
- frontend/src/mid-section-defect/
- contracts/css/

#### ci-cd-gatekeeper
- specs/changes/msd-forward-cause-effect/
- contracts/

#### qa-reviewer
- specs/changes/msd-forward-cause-effect/
- contracts/

### Context Expansion Requests
- request-id: CER-001
  requested_paths:
    - src/mes_dashboard/services/trace_job_service.py
  reason: Named in change-request as the spool-write/orchestration owner, but the project-map services listing is truncated. Confirm exact path before backend work. (Granted via Allowed Paths.)
  status: approved
- request-id: CER-002
  requested_paths:
    - src/mes_dashboard/services/mid_section_defect_service.py
  reason: Core correctness fix at `_attribute_forward_defects` (~:2606); design + lineage re-keying need read access beyond the indexes. (Granted via Allowed Paths.)
  status: approved
