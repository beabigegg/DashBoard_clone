# Context Manifest

This manifest defines the approved context boundaries for agents working on
this change. The forbidden-paths baseline lives in `.cdd/context-policy.json`
and is automatically applied by `cdd-kit gate` — do not duplicate it here.

## Affected Surfaces
- downtime-analysis frontend module (`frontend/src/downtime-analysis/`)
- downtime-analysis backend (`src/mes_dashboard/routes/downtime_analysis_routes.py`, `src/mes_dashboard/services/downtime_analysis_service.py`, `downtime_analysis_cache.py`)
- shared-ui (`frontend/src/shared-ui/components/`) — read-only, verify additive non-breaking impact only
- downtime-analysis SQL spool directory (`src/mes_dashboard/sql/downtime_analysis/`) — read-only, confirm no new query is added

## Allowed Paths
- specs/changes/downtime-analysis-page-redesign/
- specs/context/project-map.md
- specs/context/contracts-index.md
- contracts/
- contracts/api/api-contract.md
- contracts/api/api-inventory.md
- contracts/css/css-contract.md
- contracts/css/css-inventory.md
- contracts/data/data-shape-contract.md
- contracts/CHANGELOG.md
- docs/adr/0002-downtime-analysis-spool-namespace.md
- docs/adr/0003-downtime-rowcount-chunking-exclusion.md
- frontend/src/downtime-analysis/
- frontend/src/shared-ui/components/
- frontend/src/core/
- frontend/tests/playwright/
- frontend/tests/components/
- src/mes_dashboard/routes/downtime_analysis_routes.py
- src/mes_dashboard/services/downtime_analysis_service.py
- src/mes_dashboard/services/downtime_analysis_cache.py
- src/mes_dashboard/services/event_fetcher.py
- src/mes_dashboard/sql/downtime_analysis/
- .github/workflows/frontend-tests.yml

## Required Contracts
- contracts/api/api-contract.md
- contracts/api/api-inventory.md
- contracts/css/css-contract.md
- contracts/css/css-inventory.md
- contracts/data/data-shape-contract.md
- contracts/CHANGELOG.md

## Required Tests
- frontend/tests/playwright/downtime-analysis.spec.js (extend or new)
- frontend/tests/components/ (new SFC-paired tests for StatusMachineJobTable / MachineEventRows)
- backend downtime-analysis service/route unit tests (paths confirmed via CER-001 below)

## Agent Work Packets

### spec-architect
- specs/changes/downtime-analysis-page-redesign/
- specs/context/project-map.md
- specs/context/contracts-index.md
- docs/adr/0002-downtime-analysis-spool-namespace.md
- docs/adr/0003-downtime-rowcount-chunking-exclusion.md
- contracts/api/api-contract.md
- contracts/data/data-shape-contract.md
- frontend/src/downtime-analysis/
- src/mes_dashboard/routes/downtime_analysis_routes.py
- src/mes_dashboard/services/downtime_analysis_service.py

### contract-reviewer
- specs/changes/downtime-analysis-page-redesign/
- contracts/

### test-strategist
- specs/changes/downtime-analysis-page-redesign/
- frontend/tests/playwright/
- frontend/tests/components/

### ci-cd-gatekeeper
- specs/changes/downtime-analysis-page-redesign/
- contracts/
- .github/workflows/frontend-tests.yml

### implementation-planner
- specs/changes/downtime-analysis-page-redesign/
- specs/context/project-map.md
- specs/context/contracts-index.md
- contracts/api/api-contract.md
- contracts/css/css-contract.md
- contracts/data/data-shape-contract.md

### backend-engineer
- specs/changes/downtime-analysis-page-redesign/
- contracts/api/api-contract.md
- contracts/api/api-inventory.md
- contracts/data/data-shape-contract.md
- contracts/CHANGELOG.md
- src/mes_dashboard/routes/downtime_analysis_routes.py
- src/mes_dashboard/services/downtime_analysis_service.py
- src/mes_dashboard/services/downtime_analysis_cache.py
- src/mes_dashboard/services/event_fetcher.py
- src/mes_dashboard/sql/downtime_analysis/

### frontend-engineer
- specs/changes/downtime-analysis-page-redesign/
- contracts/css/css-contract.md
- contracts/css/css-inventory.md
- frontend/src/downtime-analysis/
- frontend/src/shared-ui/components/
- frontend/src/core/
- frontend/tests/components/
- frontend/tests/playwright/

### ui-ux-reviewer
- specs/changes/downtime-analysis-page-redesign/
- contracts/css/css-contract.md
- frontend/src/downtime-analysis/
- frontend/src/shared-ui/components/

### qa-reviewer
- specs/changes/downtime-analysis-page-redesign/
- contracts/

## Context Expansion Requests

- request-id: CER-001
  requested_paths:
    - tests/test_downtime_analysis_routes.py
    - tests/test_downtime_analysis_service.py
  reason: The project-map tests/ listing is truncated. The exact backend test file names for downtime-analysis must be confirmed before backend-engineer / test-strategist add per-kwarg forwarding and dual-path tests. If these files do not exist, new test files in tests/ are required.
  status: approved

## Approved Expansions
- CER-001 approved: both files confirmed to exist (tests/test_downtime_analysis_routes.py, tests/test_downtime_analysis_service.py); backend-engineer extended them in place.
