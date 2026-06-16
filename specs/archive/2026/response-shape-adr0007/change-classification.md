# Change Classification

## Change Types
- primary: `contract-annotation`, `test-infrastructure`
- secondary: `data-shape-conformance`, `ci-cd-change`

## Risk Level
- medium

## Impact Radius
- cross-module

## Tier
- 2

## Architecture Review Required
- no

## Required Artifacts
Always required: change-request.md, change-classification.md, implementation-plan.md, test-plan.md, ci-gates.md, tasks.yml, context-manifest.md

## Optional Artifacts (default: no — set yes only with explicit reason)
| artifact | create? | reason |
|---|---|---|
| current-behavior.md | no | |
| proposal.md | no | |
| spec.md | no | |
| design.md | no | |
| qa-report.md | no | |
| regression-report.md | no | |
| visual-review-report.md | no | |
| monkey-test-report.md | no | |
| stress-soak-report.md | no | |

## Required Contracts
- API: yes — add `## Schemas` typed schema per endpoint; regenerate `contracts/openapi.json`
- CSS/UI: none
- Env: none
- Data shape: yes — confirm conformance rules in `contracts/data/data-shape-contract.md`
- Business logic: none
- CI/CD: yes — wire `cdd-kit validate --contracts` into contract gate

## Required Tests
- unit: capture-script helpers
- contract: yes — `cdd-kit validate --contracts` against all 158 samples
- integration: none
- E2E: none
- visual: none
- data-boundary: yes — schema-vs-real-response conformance
- resilience: none
- fuzz/monkey: none
- stress: none
- soak: none

## Required Agents
- `contract-reviewer`
- `test-strategist`
- `ci-cd-gatekeeper`
- `implementation-planner`
- `backend-engineer`
- `qa-reviewer`

## Inferred Acceptance Criteria
- AC-1: Every one of the 158 endpoints in `contracts/api/api-contract.md` has a named typed response schema declared under `## Schemas` (Tier-A field table or Tier-B json-schema block).
- AC-2: `contracts/openapi.json` is regenerated via `cdd-kit openapi export` and carries resolved schemas for all 158 endpoints.
- AC-3: `tests/contract/capture_samples.py` captures a real response body for each endpoint using the Flask test-client (no live DB/Redis), handling `login_required` endpoints by authenticating first.
- AC-4: `tests/contract/response-samples.json` maps every endpoint to its sample; `tests/contract/samples/*.json` contains all captured bodies.
- AC-5: `cdd-kit validate --contracts` passes with every captured sample validated against its declared schema.
- AC-6: `cdd-kit doctor` reports 0 warnings on Response-shape.
- AC-7: No production source under `src/` is modified.
- AC-8: `cdd-kit validate --contracts` is wired into the contract gate as a merge-blocking check.

## Tasks Not Applicable
- not-applicable: 1.3, 2.2, 2.3, 2.5, 3.2, 3.3, 3.4, 3.5, 4.2, 4.3, 5.1, 5.2, 5.3

## Clarifications or Assumptions
- Endpoints requiring auth are satisfied via in-process Flask test-client login.
- Endpoints returning empty data for invalid params capture the error/empty shape, not live Oracle rows.
- `cdd-kit openapi export` is the canonical regen command; `contracts/openapi.json` is the target.

## Context Manifest Draft

### Affected Surfaces
- API response-shape contract (all 158 endpoints)
- Contract-test harness (`tests/contract/`)
- Data-shape conformance gate
- CI contract gate

### Allowed Paths
- specs/changes/response-shape-adr0007/
- specs/context/project-map.md
- specs/context/contracts-index.md
- contracts/api/
- contracts/data/
- contracts/ci/
- contracts/openapi.json
- contracts/CHANGELOG.md
- docs/adr/
- tests/contract/
- tests/test_api_contract.py
- src/mes_dashboard/routes/
- src/mes_dashboard/core/response.py
- src/mes_dashboard/services/auth_service.py
- src/mes_dashboard/app.py
- .github/workflows/contract-driven-gates.yml

### Agent Work Packets

#### change-classifier
- specs/changes/response-shape-adr0007/
- specs/context/project-map.md
- specs/context/contracts-index.md
