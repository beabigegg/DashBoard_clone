# Change Classification

## Change Types
- primary: feature-add (new async report page `/uph-performance`)
- secondary: api-change, ui-add, env-change, data-shape-change, business-logic-change, ci-cd-change

## Lane
- feature

## Risk Level
- high

## Impact Radius
- cross-module

Rationale: the page itself is additive, but it loads a genuinely heavy new workload onto shared infrastructure — the global heavy-query semaphore (`acquire_heavy_query_slot`), the shared Oracle connection pool, the RQ queue, `spool_routes._ALLOWED_NAMESPACES`, `BaseChunkedDuckDBJob`, and the deploy/launcher wiring. It queries a ~12M-row/24h table (`EAP_EVENT`) whose detail JOIN has previously timed out at >180s. That operational risk radiates to every other async report sharing those resources.

## Tier
- 1

Tier reasoning: high risk (production Oracle large-table queries with prior timeouts, new async worker on a shared concurrency-gated queue, new spool namespace, new env flag) combined with cross-module operational impact maps to Tier 0–1. Not Tier 0 because the change is purely additive, closely modeled on two existing shipped features (`eap-alarm`, `production-achievement`), reuses the established safe async pattern (`max_parallel=3`, single RQ worker, no concurrency-knob changes), and does not alter existing behavior or system-wide critical paths (auth/payments/migration).

## Atomic-split note
The contract-heavy trigger technically trips (all 6 contract facets touched), but this is a single indivisible vertical feature slice — UI needs the API, API needs the worker, worker needs the env flag and spool namespace. Splitting would manufacture artificial serial dependencies with no independently shippable value, exactly as `eap-alarm` and `production-achievement` were each delivered as one change. Proceeding as a single Tier 1 change. The only defensible seam — a preliminary read-only SQL-feasibility spike to validate `BondUPH`/`fHCM_UPH` return data — is folded into backend-engineer's task rather than split into its own tracked change.

## Architecture Review Required
- yes
- reason: non-obvious data-flow and query-cost decisions must be made before implementation — the `EAP_EVENT`/`EAP_EVENT_DETAIL` chunking strategy against a 12M-row table with prior >180s timeouts, a new spool-namespace key design, the DB/WB classification approach via `workcenter_groups` (a prior prefix-enumeration approach was retired per business rule EA-07), and adding a new heavy worker onto the shared global concurrency semaphore.

## Required Artifacts
Always required: change-request.md, change-classification.md, implementation-plan.md, test-plan.md, ci-gates.md, tasks.yml, context-manifest.md

## Optional Artifacts (default: no — set yes only with explicit reason)
| artifact | create? | reason |
|---|---|---|
| current-behavior.md | no | new page; no existing behavior to characterize |
| proposal.md | no | goal is clear in change-request |
| spec.md | no | design.md + interaction-design.md cover product/behavior detail |
| design.md | yes | architecture review required (query-cost/chunking, spool-namespace, shared-semaphore worker, DB/WB grouping decisions) |
| qa-report.md | yes | Tier 1 high-risk; production Oracle load risk + open data-availability question likely yields approved-with-risk durable evidence |
| regression-report.md | no | additive; shared-infra regression covered by stress/soak + integration tests, logged via agent-log |
| visual-review-report.md | yes | new UI page with charts; durable visual evidence bundle |
| monkey-test-report.md | no | prefer agent-log pointer; escalate to yes only on blocking findings |
| stress-soak-report.md | yes | new heavy Oracle worker on shared concurrency semaphore + large table with prior timeouts warrants durable load/soak evidence |

Note: `interaction-design.md` is also required (new UI page/route with an independent-filter ranking block) — tracked via its own artifact, not this optional table.

Artifact minimization:
- Prefer optional `agent-log/*.yml` pointers for routine review evidence.
- Create report markdown only for blocking findings, approved-with-risk, visual evidence bundles, or high-risk load/soak results.
- Later artifacts should reference earlier artifacts by path/section/id instead of duplicating full content.

## Required Contracts
- API: yes — new endpoints (view/trend, per-event detail, filter-options); update `contracts/api/api-contract.md`, `api-inventory.md`, and re-export both `contracts/openapi.json` and `contracts/api/openapi.json`
- CSS/UI: yes — new `.theme-uph-performance` scope; register authored CSS in `contracts/css/css-inventory.md`
- Env: yes — new `*_USE_UNIFIED_JOB` flag in `contracts/env/env-contract.md`, `contracts/env/env.schema.json` (enum + default), and `.env.example`; worker/gunicorn parity per env-contract §Worker Feature-Flag Env-Var Parity
- Data shape: yes — new trend/detail row shapes (LOT_ID, EQUIPMENT_ID, timestamp, raw UPH value, Package, Type, WorkcenterName, DB/WB label) in `contracts/data/data-shape-contract.md`, including empty/invalid-data behavior
- Business logic: yes — UPH parameter-mapping rules (GDBA→`BondUPH`, GWBA→`fHCM_UPH`), no-scale-conversion rule, GDBA/GWBA-only family scope, DB/WB grouping via `workcenter_groups` (consistent with EA-07) in `contracts/business/business-rules.md`
- CI/CD: yes — new RQ worker deploy checklist per `contracts/ci/ci-gate-contract.md` §New RQ Worker Deploy Checklist (wire `deploy/*.service` AND `scripts/start_server.sh`, no `--job-execution-timeout`)

## Required Tests
- unit: yes — SQL builder (window chunking, family→parameter mapping, both bridges, DB/WB grouping), route per-kwarg forwarding, async route↔worker `inspect.signature().bind()` shape
- contract: yes — new endpoint response samples + OpenAPI schema resolution
- integration: yes — RQ async job tests, semaphore/heavy-slot wiring, chunk-boundary, coarse-filter, data-boundary
- E2E: yes — Playwright `uph-performance` spec + portal-shell navigation registration assertion
- visual: yes — new page visual review
- data-boundary: yes — empty-result handling when `BondUPH`/`fHCM_UPH` return no rows; malformed-data spec
- resilience: yes — Oracle fault-injection / Redis chaos on the new async path
- fuzz/monkey: optional — operation-sequence monkey spec; log via agent-log unless blocking
- stress: yes — new heavy Oracle worker on shared semaphore against large table
- soak: yes — long-running job/queue soak consideration (mirror base-job semaphore soak)

## Required Agents
- spec-architect (design.md + likely new ADR)
- interaction-designer (interaction-design.md)
- implementation-planner
- backend-engineer (SQL, service, worker, routes, spool namespace, env flag, deploy/launcher wiring)
- frontend-engineer (new Vue app under `frontend/src/uph-performance/`, navigation/build wiring)
- test-strategist
- contract-reviewer (api / env / data / business / ci / css)
- ui-ux-reviewer (new page interaction, filters, accessibility)
- visual-reviewer (new page visuals)
- e2e-resilience-engineer (resilience specs)
- stress-soak-engineer (stress + soak for the new heavy worker)
- ci-cd-gatekeeper (new RQ worker deploy checklist, gates)
- qa-reviewer (release readiness / approved-with-risk)

## Inferred Acceptance Criteria
- AC-1: `/uph-performance` is registered in the production-assist drawer at order 3 with displayName「UPH表現」across all four required registration points (navigationManifest.js, routeContracts.js, vite.config.ts INPUT_MAP, route_scope_matrix.json) and the app boots.
- AC-2: The UPH source query reads `EAP_EVENT` with `EVENT_TYPE LIKE '%_M[60]'`, `LOT_ID IS NOT NULL`, `EQUIPMENT_ID` restricted to `GDBA%`/`GWBA%` only, filtered on `LAST_UPDATE_TIME`, and is always time-chunked (≤6h windows) — never a full-table scan.
- AC-3: The `EAP_EVENT_DETAIL` join on `SEQ_ID` selects `PARAMETER_NAME` by family (GDBA→`BondUPH`, GWBA→`fHCM_UPH`) and uses `PARAMETER_VALUE` as the raw UPH value with no scale conversion.
- AC-4: `LOT_ID`→`DW_MES_CONTAINER` bridge yields PRODUCTLINENAME (Package) and PJ_TYPE (Type); `EQUIPMENT_ID`→`DW_MES_RESOURCE` bridge yields WORKCENTERNAME mapped to `workcenter_groups` 焊接_DB/焊接_WB DB/WB labels (per EA-07, not prefix enumeration).
- AC-5: The page runs purely async via `BaseChunkedDuckDBJob` (no sync fallback) through a new RQ worker that acquires `acquire_heavy_query_slot`, registers a new namespace in `spool_routes._ALLOWED_NAMESPACES`, and is gated by a new `*_USE_UNIFIED_JOB` env flag with matching gunicorn/worker parity.
- AC-6: The frontend exposes global filters (date range required, family GDBA/GWBA, WORKCENTERNAME, Package, Type, equipment search), a group-able trend chart, an equipment-ranking block grouped by Type with its own independent Type multiselect sorted ascending (no threshold/alert), and a per-event detail table.
- AC-7: The new RQ worker is wired into both `deploy/*.service` and `scripts/start_server.sh` (no `--job-execution-timeout`); the env flag is added to env-contract.md, env.schema.json (enum+default), and .env.example; new endpoints are added to api-contract, api-inventory, and both openapi.json copies.
- AC-8: When `BondUPH`/`fHCM_UPH` return no rows for a selected window, the UI shows a graceful empty state rather than erroring (validated by a data-boundary test).

## Tasks Not Applicable
- not-applicable: (none) — this is a net-new additive page and design.md IS required, so no tasks.yml items are skipped at classification time.

## Clarifications or Assumptions
- This is delivered as a single Tier 1 vertical feature (not atomically split), consistent with how `eap-alarm` and `production-achievement` shipped, despite the contract-heavy heuristic tripping — the surfaces are cohesive, not independent risk domains.
- Open risk carried from the request: `BondUPH`/`fHCM_UPH` are recently-configured parameter names and may return no data. `backend-engineer` must run a narrow-window (≤6h) read-only exploratory query to confirm data before full build (per `docs/architecture/eap-event-uph-collection-investigation.md`). This gates AC-2/AC-3.
- Concurrency knobs (`max_parallel`, `HEAVY_QUERY_MAX_CONCURRENT`, RQ worker count) are explicitly out of scope; the new worker reuses the existing safe mode.

## Context Manifest Draft
See `specs/changes/add-uph-performance-page/context-manifest.md` (copied verbatim from this classification).
