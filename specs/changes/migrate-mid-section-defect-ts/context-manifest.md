# Context Manifest

This manifest defines the approved context boundaries for agents working on
this change. The forbidden-paths baseline lives in `.cdd/context-policy.json`
and is automatically applied by `cdd-kit gate` — do not duplicate it here.

## Affected Surfaces
- `frontend/src/mid-section-defect/` — feature app JS→TS rename
- `frontend/tsconfig.json` — include scope expansion
- `contracts/ci/ci-gate-contract.md` + `contracts/CHANGELOG.md` — patch bump
- `frontend/tests/legacy/mid-section-defect-composables.test.js`, `frontend/tests/legacy/msd-completeness-warning.test.js` — audit/repair
- `tests/e2e/test_mid_section_defect_e2e.py` — audit for `.js` path references

## Allowed Paths
- specs/changes/migrate-mid-section-defect-ts/
- specs/context/project-map.md
- specs/context/contracts-index.md
- frontend/src/mid-section-defect/
- frontend/src/shared-ui/components/
- frontend/src/shared-composables/
- frontend/src/core/
- frontend/tsconfig.json
- frontend/vitest.config.js
- frontend/package.json
- frontend/tests/legacy/
- tests/e2e/test_mid_section_defect_e2e.py
- tests/stress/test_mid_section_defect_stress.py
- contracts/ci/ci-gate-contract.md
- contracts/CHANGELOG.md
- CLAUDE.md

## Required Contracts
- contracts/ci/ci-gate-contract.md
- contracts/CHANGELOG.md

## Required Tests
- frontend/tests/legacy/mid-section-defect-composables.test.js
- frontend/tests/legacy/msd-completeness-warning.test.js
- tests/e2e/test_mid_section_defect_e2e.py

## Agent Work Packets

### change-classifier
- specs/changes/migrate-mid-section-defect-ts/
- specs/context/project-map.md
- specs/context/contracts-index.md

### contract-reviewer
- specs/changes/migrate-mid-section-defect-ts/
- contracts/ci/ci-gate-contract.md
- contracts/CHANGELOG.md

### test-strategist
- specs/changes/migrate-mid-section-defect-ts/
- frontend/tests/legacy/
- tests/e2e/test_mid_section_defect_e2e.py

### ci-cd-gatekeeper
- specs/changes/migrate-mid-section-defect-ts/
- contracts/ci/ci-gate-contract.md

### implementation-planner
- specs/changes/migrate-mid-section-defect-ts/
- frontend/src/mid-section-defect/
- frontend/tsconfig.json
- CLAUDE.md

### frontend-engineer
- specs/changes/migrate-mid-section-defect-ts/
- frontend/src/mid-section-defect/
- frontend/src/shared-ui/components/
- frontend/src/shared-composables/
- frontend/src/core/
- frontend/tsconfig.json
- frontend/vitest.config.js
- frontend/package.json
- frontend/tests/legacy/
- tests/e2e/test_mid_section_defect_e2e.py
- contracts/ci/ci-gate-contract.md
- contracts/CHANGELOG.md

### qa-reviewer
- specs/changes/migrate-mid-section-defect-ts/
- frontend/src/mid-section-defect/
- frontend/tsconfig.json
- contracts/ci/ci-gate-contract.md

## Context Expansion Requests
-

## Approved Expansions
-
