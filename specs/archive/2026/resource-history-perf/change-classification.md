# Change Classification

## Change Types
- primary: backend performance optimization (Redis TTL strategy + cache pre-warming on startup)
- secondary: new API endpoint + frontend UX enhancement (progress polling for long batch queries)

## Risk Level
- medium

## Impact Radius
- moderate (resource_history_service.py, resource_history_routes.py, App.vue, core cache layer; no cross-module structural coupling change)

## Tier
- 3

## Architecture Review Required
- yes
- reason: startup pre-warming introduces a new Oracle dependency in the gunicorn boot path — needs design review for async vs sync approach, Redis memory budget for 3 months of data, and query_id lifecycle for the progress endpoint

## Required Artifacts
Always required: change-request.md, change-classification.md, test-plan.md, ci-gates.md, tasks.yml

## Optional Artifacts (default: no — set yes only with explicit reason)
| artifact | create? | reason |
|---|---|---|
| current-behavior.md | yes | documents current TTL=2h, no progress feedback, and startup sequence as QA regression baseline |
| proposal.md | yes | spec-architect captures chosen approach (async vs sync pre-warm, query_id lifecycle, Redis memory budget) before implementation |
| spec.md | no | proposal.md covers scope adequately |
| design.md | no | no visual design work; progress bar uses existing shared-composables patterns |
| qa-report.md | yes | startup pre-warm and progress polling require measured verification |
| regression-report.md | no | additive only; no existing behavior changed |

## Required Contracts
- API: contracts/api/api-contract.md, contracts/api/api-inventory.md — new endpoint `GET /api/resource/history/query/progress`
- CSS/UI: none
- Env: contracts/env/env-contract.md — if RESOURCE_HISTORY_HISTORICAL_TTL or RESOURCE_HISTORY_PREWARM_MONTHS are added
- Data shape: contracts/data/data-shape-contract.md — progress response payload shape
- Business logic: none
- CI/CD: contracts/ci/ci-gate-contract.md — new integration test for startup pre-warm

## Required Tests
- unit: tests/test_resource_history_service.py (prewarm_last_n_months(), TTL assignment, historical-key classification); tests/test_resource_history_routes.py (progress endpoint: 200/404/400)
- contract: tests/test_api_contract.py (new endpoint in inventory + response shape matches data-shape-contract)
- integration: tests/test_cache_integration.py (historical-TTL idempotency); tests/integration/ (startup pre-warm + Redis key assertion)
- E2E: tests/e2e/test_resource_history_e2e.py; tests/e2e/test_resource_history_browser_e2e.py
- visual: none
- data-boundary: frontend/tests/playwright/data-boundary/ (malformed progress response must not crash polling loop)
- resilience: frontend/tests/playwright/resilience/ (503 mid-poll); tests/integration/test_redis_chaos.py (Redis unavailable during pre-warm)
- fuzz/monkey: none
- stress: tests/stress/test_resource_history_stress.py (extend — concurrent progress polls N=50)
- soak: none

## Required Agents
- contract-reviewer
- spec-architect
- test-strategist
- backend-engineer
- frontend-engineer
- ci-cd-gatekeeper
- qa-reviewer

## Inferred Acceptance Criteria
- AC-1: `GET /api/resource/history/query/progress` returns 404 for unknown query_id and 400 for missing query_id parameter.
- AC-2: After service startup, Redis contains cache keys covering each 31-day chunk in the last ~3 months; each historical key's TTL ≥ 86 400 seconds.
- AC-3: Queries where `end_date < today − 2 days` receive TTL = 86 400s; queries where `end_date ≥ today − 2 days` retain the existing shorter TTL.
- AC-4: Service startup completes (gunicorn workers become ready) even if Oracle is unreachable during pre-warm; pre-warm failure logs a warning and does not raise an exception that terminates the process.
- AC-5: The progress endpoint returns `{ query_id, total_chunks, completed_chunks, percent, status }` with HTTP 200 for an active or completed query_id; `status` is one of `running | done | error`.
- AC-6: The resource-history frontend displays a percentage progress bar while a batch query (date range > 10 days) is in flight; the bar disappears and results render when `status = done`.
- AC-7: Frontend polling loop does not fire after `status = done` or `status = error` (no zombie polling).
- AC-8: Pre-warm does not overwrite existing Redis keys that already have a longer TTL (idempotent re-warm on restart).

## Tasks Not Applicable
- not-applicable: 2.2, 2.5, 5.2

## Clarifications or Assumptions
- Pre-warm runs as a background thread (or deferred RQ job) launched after gunicorn workers start — NOT in create_app() — to avoid gunicorn worker timeout.
- `query_id` for the progress endpoint is a UUID generated at batch dispatch; progress state stored in Redis as `resource:history:progress:<query_id>`.
- "Last ~3 months" = 92 days prior to today (approximately 3 × 31-day chunks).
- Immutable-historical cutoff `end_date < today − 2 days` is configurable (not hardcoded).
- Open: Redis memory footprint for 3 months of data — spec-architect must answer before backend implementation.
- Open: progress endpoint auth requirement (same LDAP guard as other resource-history routes?).
