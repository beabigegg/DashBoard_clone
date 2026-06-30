# Context Manifest

This manifest defines the approved context boundaries for agents working on
this change. The forbidden-paths baseline lives in `.cdd/context-policy.json`
and is automatically applied by `cdd-kit gate` — do not duplicate it here.

## Affected Surfaces
- MSD forward-direction analysis (backend service + DuckDB runtime + trace spool orchestration)
- MSD API surface (forward analysis + detail responses)
- MSD frontend (mid-section-defect Vue app: Sankey/Heatmap/KPI/DetailTable)
- Trace async worker / spool layer (forward lineage stage spool, package-independent trace cache)
- Contracts: api, data, business, css

## Allowed Paths
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

## Required Contracts
- contracts/api/api-contract.md
- contracts/api/api-inventory.md
- contracts/api/openapi.json
- contracts/data/data-shape-contract.md
- contracts/business/business-rules.md
- contracts/css/css-contract.md
- contracts/css/css-inventory.md

## Required Tests
- tests/test_mid_section_defect_service.py
- tests/integration/test_material_trace_rq_async.py
- tests/stress/test_mid_section_defect_stress.py
- tests/e2e/test_mid_section_defect_e2e.py
- tests/contract/samples/
- frontend/tests/legacy/mid-section-defect-composables.test.js
- frontend/tests/playwright/mid-section-defect.spec.ts

## Agent Work Packets

### change-classifier
- specs/changes/msd-forward-cause-effect/
- specs/context/project-map.md
- specs/context/contracts-index.md

### spec-architect
- specs/changes/msd-forward-cause-effect/
- specs/context/project-map.md
- specs/context/contracts-index.md
- contracts/data/data-shape-contract.md
- contracts/business/business-rules.md
- contracts/api/api-contract.md
- src/mes_dashboard/services/mid_section_defect_service.py
- src/mes_dashboard/services/msd_duckdb_runtime.py
- src/mes_dashboard/services/trace_job_service.py

### implementation-planner
- specs/changes/msd-forward-cause-effect/
- contracts/api/api-contract.md
- contracts/data/data-shape-contract.md
- contracts/business/business-rules.md
- contracts/css/css-contract.md

### backend-engineer
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

### frontend-engineer
- specs/changes/msd-forward-cause-effect/
- frontend/src/mid-section-defect/
- frontend/tests/legacy/mid-section-defect-composables.test.js
- frontend/tests/playwright/mid-section-defect.spec.ts
- contracts/css/css-contract.md
- contracts/css/css-inventory.md

### test-strategist
- specs/changes/msd-forward-cause-effect/
- tests/test_mid_section_defect_service.py
- tests/integration/test_material_trace_rq_async.py
- tests/stress/test_mid_section_defect_stress.py
- tests/e2e/test_mid_section_defect_e2e.py
- frontend/tests/playwright/mid-section-defect.spec.ts

### stress-soak-engineer
- specs/changes/msd-forward-cause-effect/
- tests/stress/test_mid_section_defect_stress.py
- tests/integration/test_material_trace_rq_async.py

### e2e-resilience-engineer
- specs/changes/msd-forward-cause-effect/
- tests/e2e/test_mid_section_defect_e2e.py
- frontend/tests/playwright/mid-section-defect.spec.ts

### contract-reviewer
- specs/changes/msd-forward-cause-effect/
- contracts/

### ui-ux-reviewer
- specs/changes/msd-forward-cause-effect/
- frontend/src/mid-section-defect/
- contracts/css/

### visual-reviewer
- specs/changes/msd-forward-cause-effect/
- frontend/src/mid-section-defect/
- contracts/css/

### ci-cd-gatekeeper
- specs/changes/msd-forward-cause-effect/
- contracts/

### qa-reviewer
- specs/changes/msd-forward-cause-effect/
- contracts/

## Context Expansion Requests

- request-id: CER-001
  requested_paths:
    - src/mes_dashboard/services/trace_job_service.py
  reason: Spool-write/orchestration owner named in change-request; project-map services listing is truncated. Confirm exact path before backend work.
  status: approved

- request-id: CER-002
  requested_paths:
    - src/mes_dashboard/services/mid_section_defect_service.py
  reason: Core correctness fix at `_attribute_forward_defects` (~:2606); design + lineage re-keying need read access beyond the indexes.
  status: approved

## Approved Expansions
- CER-001 — trace_job_service.py (spool orchestration)
- CER-002 — mid_section_defect_service.py (forward attribution core)
