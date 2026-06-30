# Change Classification

## Change Types
- primary: feature-enhancement, api-change
- secondary: business-logic-change, data-shape-change, ui-change

## Lane
- feature

## Risk Level
- medium

## Impact Radius
- cross-module

## Tier
- 2

## Architecture Review Required
- yes
- reason: Extends the EAP-alarm coarse spool key (schema_version 2→3, auto-invalidating old parquet) and adds an Oracle EXISTS semi-join across DWH.EAP_EVENT × DWH.DW_MES_CONTAINER. This is a cache-key + data-flow design decision with row-explosion and cache-poisoning risk, directly extending ADR 0008. The spool-key hash must provably cover all new dimensions, and the at-least-one-of-three NULL/empty validation matrix needs a decided contract before implementation. Requires spec-architect to write design.md before implementation-planner runs.

## Required Artifacts
Always required: change-request.md, change-classification.md, implementation-plan.md, test-plan.md, ci-gates.md, tasks.yml, context-manifest.md

## Optional Artifacts (default: no — set yes only with explicit reason)
| artifact | create? | reason |
|---|---|---|
| current-behavior.md | no | Current behavior is small enough to capture in design.md/implementation-plan |
| proposal.md | no | Capability already specified in the request |
| spec.md | no | Behavior fits in design.md + implementation-plan |
| design.md | yes | Architecture Review Required = yes: spool-key extension + schema_version bump + EXISTS semi-join + 3-way optional-filter validation matrix are non-obvious design decisions; records decision and amends/references ADR 0008 |
| qa-report.md | no | Routine pass/fail lives in agent-log/qa-reviewer.yml; promote only if blocking findings |
| regression-report.md | no | schema_version bump auto-invalidates old parquet; regression scope is bounded |
| visual-review-report.md | no | FilterBar additions reviewed via agent-log/visual-reviewer.yml |
| monkey-test-report.md | no | Not a high-fuzz surface |
| stress-soak-report.md | no | Coarse filter narrows query volume (reduces load); not a new high-load path |

## Required Contracts
- API: yes — contracts/api/api-contract.md + contracts/api/api-inventory.md (+ regen contracts/openapi.json AND contracts/api/openapi.json). New request body fields (lot_ids, pj_type/product_line/pj_bop), machines becomes optional, new/reused product-filter-options endpoint.
- CSS/UI: no — FilterBar adds existing shared components under existing .theme-eap-alarm scope; confirm via npm run css:check only
- Env: no — no new env var or feature flag (schema_version is in-code)
- Data shape: yes — contracts/data/data-shape-contract.md. Spool-key dimensions, schema_version 2→3 invalidation semantics, EXISTS-join column set (CONTAINERNAME↔LOT_ID, PJ_TYPE/PRODUCTLINENAME/PJ_BOP), product-filter-options payload shape.
- Business logic: yes — contracts/business/business-rules.md. "machines / lot_ids / product_dims — at least one required" validation rule and EXISTS semi-join attribution semantics.
- CI/CD: no — no new gate; existing eap-alarm gates cover it

## Required Tests
- unit: yes — make_eap_alarm_spool_key() covers all new dims; validation matrix for machines/lot_ids/product_dims NULL/empty/present combinations; route body parsing
- contract: yes — API contract test for new body fields + machines-optional + product-filter-options response; cdd-kit validate --contracts
- integration: yes — tests/integration/test_eap_alarm_rq_async.py (async coarse path with new dims); EXISTS semi-join correctness against fixture (no row explosion)
- E2E: yes — frontend/tests/playwright/eap-alarm-filters.spec.ts: LOT_ID + product-dim filter flow, machines-optional submission
- visual: no — covered by agent-log/visual-reviewer.yml
- data-boundary: yes — tests/integration/test_eap_alarm_data_boundary.py: empty/duplicate/whitespace LOT_IDs, no-match product dims, mixed CHAR-padded CONTAINERNAME
- resilience: yes — tests/integration/test_eap_alarm_resilience.py: Oracle error during semi-join fails over correctly; container_filter_cache miss path
- fuzz/monkey: no
- stress: no — coarse filter reduces query volume, not a new high-load path
- soak: no

## Required Agents
- spec-architect — write design.md (spool-key extension, EXISTS-join semantics, validation matrix; amend/reference ADR 0008) BEFORE implementation-planner
- implementation-planner — turn decisions/contracts/tests into execution packet BEFORE any implementation agent
- backend-engineer — eap_alarm_cache.py, eap_alarm_service.py, eap_alarm_worker.py, eap_alarm_routes.py
- frontend-engineer — FilterBar.vue + useEapAlarmFilter.js (LOT_ID textarea, TYPE/PKG/BOP MultiSelect, buildCoarseParams)
- contract-reviewer — API + data-shape + business-rules contract edits, openapi regen parity
- test-strategist — acceptance-criteria → test mapping
- ui-ux-reviewer — FilterBar interaction/copy (i18n sync for new labels), at-least-one-of-three error messaging
- qa-reviewer — release readiness

## Inferred Acceptance Criteria
- AC-1: A coarse-filter request with one or more lot_ids returns only EAP_EVENT rows whose LOT_ID exactly matches one of the supplied values (LOT_ID IN (...)), and the spool key reflects those lot_ids.
- AC-2: A coarse-filter request with product dimensions (pj_type and/or product_line and/or pj_bop) returns only EAP_EVENT rows whose LOT_ID has a matching DW_MES_CONTAINER.CONTAINERNAME satisfying the supplied dims via EXISTS semi-join, with no row duplication/explosion.
- AC-3: machines is optional; a request is accepted when at least one of {machines, lot_ids, product_dims} is non-empty, and rejected with a clear error when all three are empty.
- AC-4: make_eap_alarm_spool_key() produces an identical key for identical full param sets (incl. new dims) and a different key for any differing dim; schema_version is 3 so all pre-existing (v2) parquet is invalidated and not served.
- AC-5: Combinations of the three filter axes (e.g. lot_ids + product dims, machines + lot_ids) are ANDed correctly, and empty/whitespace/duplicate lot_id inputs are normalized (CHAR-padding stripped at both key-build and Oracle lookup).
- AC-6: The frontend FilterBar exposes a LOT_ID textarea and TYPE/PACKAGE/BOP MultiSelects whose options load from the product-filter-options source, and buildCoarseParams forwards every selected dim to the request (per-kwarg, non-default).
- AC-7: An Oracle error during the EXISTS semi-join fails over per the existing resilience contract (no 503 leak / correct error payload), and a container_filter_cache miss does not crash the options endpoint.

## Tasks Not Applicable
- not-applicable: 2.2, 2.3, 2.6, 3.4, 3.5, 4.3, 4.4, 5.2, 6.4

## Clarifications or Assumptions
- Open product decision: new dedicated endpoint /api/eap-alarm/product-filter-options vs reusing container_filter_cache. Default to REUSE the existing container-filter-options source; spec-architect to decide and record in design.md.
- Assumption: schema_version 2→3 cleanly invalidates old parquet with no migration/backfill.
- Assumption: PACKAGE/PKG maps to PRODUCTLINENAME; confirm user-facing label vs column mapping and sync i18n for all languages.
- Assumption: machines-optional is additive/backward-compatible for existing clients that always send machines.
- CER-001 resolved: tests/test_eap_alarm_service.py, src/mes_dashboard/services/container_filter_cache.py, and docs/adr/0008-eap-alarm-coarse-spool-detail-join.md all confirmed to exist.
