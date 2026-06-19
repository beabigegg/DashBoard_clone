# Change Classification

## Change Types
- primary: refactor (service migration to BaseChunkedDuckDBJob), performance (pandas hot-path removal / OOM-guard shift to pre-emptive DuckDB spill)
- secondary: env-change (2 new feature flags), business-logic-change (ASYNC-07/ASYNC-08 rules), ci-cd-change (new gate compatibility note)

## Risk Level
- high

## Impact Radius
- cross-module

## Tier
- 1

## Architecture Review Required
- no
- reason: The architectural pattern — `BaseChunkedDuckDBJob` subclass per domain, flag-gated route dispatch, `always_async=False`, row-level `TIME` chunking — is already established and ratified by P1 (`eap-alarm-unified-job-poc`) under ADR-0009. This P2 applies that exact pattern to two more domains with no new module boundary, data-flow, or migration/rollback decision. The single open question ("does Production History already have a `merge_chunks_to_spool()` path?") is an implementation investigation for the planner/backend-engineer, not an architectural decision. No new ADR is needed; `design.md` is not required and task 1.3 is not-applicable.
<!-- If yes, Optional Artifacts must set design.md to yes and Required Agents must include spec-architect. -->

## Required Artifacts
Always required: change-request.md, change-classification.md, implementation-plan.md, test-plan.md, ci-gates.md, tasks.yml, context-manifest.md

## Optional Artifacts (default: no — set yes only with explicit reason)
| artifact | create? | reason |
|---|---|---|
| current-behavior.md | no | Legacy pandas behavior is the parity baseline; capture it as parity fixtures/assertions in test-plan + agent-log, not a separate prose artifact. |
| proposal.md | no | Decision already made in query-dataflow-unification.md §3 + P1 ADR-0009; no separate product decision needed. |
| spec.md | no | No user-facing behavior change (explicit non-goal: frontend/spool schema unchanged). |
| design.md | no | Architecture established by P1/ADR-0009; no new ADR. (1.3 not-applicable.) |
| qa-report.md | no | Routine pass/fail goes to agent-log/qa-reviewer.yml; promote to yes only if QA returns blocking findings or approved-with-risk. |
| regression-report.md | no | Parity is the core acceptance evidence; record in test-plan + agent-log. Promote to yes only if a parity gap is found and shipped with mitigation. |
| visual-review-report.md | no | No UI surface touched. |
| monkey-test-report.md | no | No interactive UI flow added. |
| stress-soak-report.md | no | Existing tests/stress/test_{production,reject}_history_stress.py cover load; no new high-load surface. Promote to yes only if stress reveals OOM/regression under the new DuckDB-spill path. |

## Required Contracts
- API: none (explicit non-goal — /summary /pareto /trend /detail endpoints unchanged; spool schema unchanged; 503 already added in P1)
- CSS/UI: none (no frontend change)
- Env: contracts/env/env-contract.md — add `PRODUCTION_HISTORY_USE_UNIFIED_JOB` and `REJECT_HISTORY_USE_UNIFIED_JOB` (default `off`), with `.env.example` + config validation + default-value pin
- Data shape: contracts/data/data-shape-contract.md — assert spool schema UNCHANGED (explicit non-goal note; row-level parity still verified by data-boundary tests)
- Business logic: contracts/business/business-rules.md — add ASYNC-07 + ASYNC-08 (unified-job dispatch + per-domain flag-gated rollback semantics; OOM guard shifts from post-hoc to pre-emptive DuckDB spill)
- CI/CD: contracts/ci/ci-gate-contract.md — new gate compatibility note for the two new job workers / flag-off legacy-path coverage

## Required Tests
- unit: ProductionHistoryJob + RejectHistoryJob subclass behavior; flag-off legacy-path dispatch; query_cost_policy _APPROVED_CALLERS membership; job_registry registration with always_async=False; ast/grep test proving 6 post-hoc OOM guards removed and RSS sync-fallback pandas path removed
- contract: env-contract default-value pin for both flags (monkeypatch.setattr, not setenv — module-level constants); business-rules ASYNC-07/08 presence; data-shape spool-schema-unchanged assertion
- integration: RQ-async parity per domain (model on test_resource_history_rq_async.py / test_eap_alarm_rq_async.py) — flag-on unified-job vs flag-off legacy spool-parity (row equality + numerical parity for groupby/pareto/trend)
- E2E: existing test_production_history_e2e.py / test_reject_history_e2e.py must stay green under both flag states
- visual: (none — no UI change)
- data-boundary: spool row-level parity + DuckDB SQL vs pandas numerical parity (groupby/pareto/trend); malformed/empty-chunk handling on the new DuckDB read path
- resilience: DuckDB on-disk spill behavior under memory pressure (pre-emptive guard replaces post-hoc); chunk-to-spool failure/retry
- fuzz/monkey: (none required)
- stress: confirm existing tests/stress/test_{production,reject}_history_stress.py pass under flag-on unified path (nightly/weekly per test-layer governance)
- soak: consider only (weekly lane); flag default-off makes production rollout safe without pre-merge soak

## Required Agents
- implementation-planner
- backend-engineer
- test-strategist
- contract-reviewer
- ci-cd-gatekeeper
- qa-reviewer

## Inferred Acceptance Criteria
- AC-1: ProductionHistoryJob(BaseChunkedDuckDBJob) produces spool-parity results vs the legacy path (row-level equality on the unchanged spool schema).
- AC-2: RejectHistoryJob(BaseChunkedDuckDBJob) DuckDB SQL groupby/pareto/trend output matches legacy pandas output (numerical parity within agreed tolerance).
- AC-3: Both feature flags (`PRODUCTION_HISTORY_USE_UNIFIED_JOB`, `REJECT_HISTORY_USE_UNIFIED_JOB`) default `off`; the legacy path executes verbatim when flag=off (safe per-domain rollback).
- AC-4: The 6 post-hoc OOM guards in reject_history_service.py / reject_dataset_cache.py are removed and replaced by pre-emptive DuckDB on-disk spill (proven by ast/grep absence test).
- AC-5: The RSS sync-fallback pandas SELECT path is removed from production_history_routes; the degraded path goes through chunk-to-spool with no large-range pandas SELECT.
- AC-6: Both job types are registered in job_registry with `always_async=False` (domain policy may permit SYNC for small L0–L1 queries).
- AC-7: query_cost_policy `_APPROVED_CALLERS` is extended to include both new job workers (the no-callers-outside-tests rule established in P1).
- AC-8: View endpoints (/summary, /pareto, /trend, /detail) and the spool data shape are unchanged; existing E2E specs pass under both flag states.

## Tasks Not Applicable
- not-applicable: 1.3, 2.2, 4.2, 5.1, 5.2

## Clarifications or Assumptions
- Assumption: P2 is a single change (not atomic-split). The two domains share one change-type (BaseChunkedDuckDBJob migration), one pattern (P1/ADR-0009), one surface family (backend query-dataflow plane), and 3-of-6 contracts — below all split triggers. Per-domain feature flags already provide independent rollback.
- Assumption: Tier 1 because the surface is a high-risk async/job/OOM/worker pipeline touching shared core across two domains. Flag-gated safety justification preserved, but shared-core blast radius classifies upward from Tier 2.
- Assumption: No new ADR; follow P1/ADR-0009 exactly. If the backend investigation finds Production History needs a new merge/aggregation strategy, re-escalate to Architecture Review (set design.md=yes, add spec-architect, un-skip 1.3).
- Assumption: spool schema and view endpoints are genuinely unchanged; data-shape contract change is an explicit "unchanged" assertion. If parity work reveals any spool column drift, this becomes a data-shape-contract change.
- Open: confirm whether a dedicated production-history worker systemd unit is needed (only reject worker unit exists in deploy/). May need a new unit file.

## Context Manifest Draft

### Affected Surfaces
- Production History query/job pipeline (service + job + route + sql_runtime)
- Reject History query/job pipeline (service + dataset cache + route)
- Shared async-job core (base_chunked_duckdb_job, query_cost_policy, job_registry, async_query_job_service, oracle_arrow_reader)
- Worker deployment (reject worker service unit; production worker if added)
- Contracts: env, business, ci, data-shape

### Allowed Paths
- specs/changes/production-reject-history-migration/
- specs/context/project-map.md
- specs/context/contracts-index.md
- contracts/env/env-contract.md
- contracts/business/business-rules.md
- contracts/ci/ci-gate-contract.md
- contracts/data/data-shape-contract.md
- src/mes_dashboard/core/base_chunked_duckdb_job.py
- src/mes_dashboard/core/query_cost_policy.py
- src/mes_dashboard/core/oracle_arrow_reader.py
- src/mes_dashboard/core/query_spool_store.py
- src/mes_dashboard/core/spool_pipeline.py
- src/mes_dashboard/core/feature_flags.py
- src/mes_dashboard/services/production_history_service.py
- src/mes_dashboard/services/production_history_job_service.py
- src/mes_dashboard/services/production_history_sql_runtime.py
- src/mes_dashboard/services/reject_history_service.py
- src/mes_dashboard/services/reject_dataset_cache.py
- src/mes_dashboard/services/job_registry.py
- src/mes_dashboard/services/async_query_job_service.py
- src/mes_dashboard/routes/production_history_routes.py
- src/mes_dashboard/routes/reject_history_routes.py
- src/mes_dashboard/workers/
- src/mes_dashboard/sql/production_history/
- src/mes_dashboard/sql/reject_history/
- deploy/mes-dashboard-reject-worker.service
- tests/
- docs/architecture/query-dataflow-unification.md
- docs/architecture/cache-spool-patterns.md
- docs/adr/
