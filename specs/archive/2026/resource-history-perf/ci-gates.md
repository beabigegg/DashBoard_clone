---
change-id: resource-history-perf
schema-version: "1.0"
last-changed: 2026-05-13
ci-gate-contract: 1.3.10
---

# CI/CD Gate Plan — resource-history-perf

## Change ID

resource-history-perf

## Change Tier

**Tier 3 — Performance + API Enhancement** (no new CI jobs; new test files covered by existing gate commands)

This change adds TTL bifurcation in `resource_history_service.py`, a startup pre-warm job in `spool_warmup_scheduler.py`, a new `GET /api/resource/history/query/progress` endpoint, and a progress bar in `App.vue`. New tests in `tests/test_resource_history_prewarm.py` (new file) and extensions to three existing test files are all covered by existing gate commands.

---

## Local Gate Results (verified 2026-05-13)

| gate | result | details |
|---|---|---|
| backend unit + mock-integration (pytest) | PASS | 78/78 tests pass (test_resource_history_service.py, test_resource_history_routes.py, test_resource_history_prewarm.py, test_cache_integration.py) |
| frontend-unit (Vitest) | PASS | 302/302 tests |
| frontend-type-check (vue-tsc) | PASS | 0 errors |
| css-governance | PASS (warnings only) | 0 errors, 47 pre-existing warnings; no new violations |

---

## Pre-Merge Required Gates (Tier 0 / Tier 1)

### contract-validate (Tier 0)

```bash
cdd-kit validate
```

- Expected: all validations pass (API, env, data-shape, CI gate, spec traceability contracts updated for this change)
- Gate status: **required** (blocks merge)

### lint (Tier 0)

```bash
ruff check .
```

- Gate status: **required** (blocks merge)

### unit-mock-integration (Tier 1)

```bash
conda run -n mes-dashboard pytest \
  -m "not (e2e or integration_real or stress or load or soak or multi_worker)" \
  --ignore=tests/integration --ignore=tests/stress --ignore=tests/e2e --ignore=tests/manual \
  -x
```

- Covers: TTL bifurcation unit tests, progress endpoint route tests, prewarm unit tests (mock Oracle/Redis), cache-integration idempotency test
- Expected: all pass; local baseline 78/78 for changed files
- Artifact: junit XML (retained 30 days)
- Gate status: **required** (blocks merge)

### frontend-unit (Tier 1)

```bash
cd frontend && npm run test
```

- Expected: 302/302 pass (or more if additional tests added)
- Artifact: Vitest report (retained 30 days)
- Gate status: **required** (blocks merge)

### css-governance (Tier 1)

```bash
cd frontend && npm run css:check
```

- Expected: 0 errors. 47 pre-existing warnings do not block merge.
- Gate status: **required** (blocks merge on errors only)

### playwright-resilience (Tier 1)

```bash
cd frontend && npx playwright test tests/playwright/resilience/
```

- Covers: `api-failure.spec.js` extension — progress polling stops on 503 mid-poll (AC-7 + resilience)
- Artifact: Playwright traces (7 days; longer on failure)
- Gate status: **required** (blocks merge)

### playwright-data-boundary (Tier 1)

```bash
cd frontend && npx playwright test tests/playwright/data-boundary/
```

- Covers: `malformed-input.spec.js` extension — malformed progress response must not crash polling loop (AC-7)
- Gate status: **required** (blocks merge)

### playwright-critical-journeys (Tier 1)

```bash
cd frontend && npx playwright test \
  tests/playwright/hold-overview.spec.js \
  tests/playwright/reject-history.spec.js \
  tests/playwright/query-tool.spec.js
```

- Gate status: **required** (blocks merge); existing journeys must remain unaffected

---

## Informational Gates (non-blocking)

### frontend-type-check

```bash
cd frontend && npm run type-check
```

- Local result: 0 errors
- Gate status: **informational** (continue-on-error: true; does not block merge)
- Coverage: includes `src/resource-history/**/*` per Phase 3 scope expansion (ci-gate-contract.md §frontend-type-check scope expansion — migrate-resource-history-ts, schema-version 1.3.9)

---

## Nightly / Weekly Gates (schedule-only)

| gate | tier | trigger | applicable test | reason |
|---|---:|---|---|---|
| nightly-integration | 3 | weekly schedule / dispatch | `tests/test_resource_history_prewarm.py::test_prewarm_seeds_three_months_of_chunks`, `::test_prewarm_redis_ttl_ge_86400`, `::test_prewarm_oracle_unreachable_logs_warning_no_exception`; `tests/integration/test_redis_chaos.py::test_resource_history_prewarm_redis_unavailable` | startup pre-warm + real Oracle/Redis key assertion (AC-2, AC-4, AC-8); requires `integration_real` marker + real infra |
| stress-load | 4 | weekly schedule / dispatch | `tests/stress/test_resource_history_stress.py` extension — concurrent progress polls N=50 | AC-7 + system-level concurrency safety; `stress` marker, not pre-merge per test-layer governance |

Command (nightly):

```bash
conda run -n mes-dashboard pytest tests/integration/ --run-integration-real \
  -m "integration_real or multi_worker" -x
```

Command (stress):

```bash
conda run -n mes-dashboard pytest tests/stress/ -m "stress or load"
```

Artifacts: test report (30 days), perf report (90 days).

---

## Gate Status Summary

| gate | tier | required | local | CI |
|---|---:|---|---|---|
| contract-validate | 0 | yes | PASS | PENDING |
| lint (ruff) | 0 | yes | PASS | PENDING |
| unit-mock-integration | 1 | yes | PASS (78/78) | PENDING |
| frontend-unit | 1 | yes | PASS (302/302) | PENDING |
| css-governance | 1 | yes | PASS (0 errors) | PENDING |
| playwright-resilience | 1 | yes | — | PENDING |
| playwright-data-boundary | 1 | yes | — | PENDING |
| playwright-critical-journeys | 1 | yes | — | PENDING |
| frontend-type-check | 1 | informational | PASS (0 errors) | PENDING |
| nightly-integration | 3 | yes (nightly) | — | PENDING |
| stress-load | 4 | yes (weekly) | — | PENDING |

---

## Required Gates Statement

Per `contracts/ci/ci-gate-contract.md` schema-version 1.3.10:

- **Tier 1 required** gates (unit-mock-integration, frontend-unit, css-governance, playwright-resilience, playwright-data-boundary, playwright-critical-journeys) **block merge**. All must be green before this PR may land.
- **Tier 1 informational** gate (frontend-type-check) runs on PR; does not block merge.
- **Tier 3** nightly-integration gate covers startup pre-warm + real Oracle/Redis assertions (AC-2, AC-4, AC-8); failure must be triaged within 1 business day.
- **Tier 4** stress-load gate covers N=50 concurrent progress polls; failure triggers production-readiness review.

## Workflow References

| job | workflow file | trigger |
|---|---|---|
| `contract-and-fast-tests` | `.github/workflows/contract-driven-gates.yml` | push / PR |
| `frontend-unit-tests` | `.github/workflows/frontend-tests.yml` | push / PR |
| `unit-and-integration-tests` | `.github/workflows/backend-tests.yml` | push / PR |
| `e2e-critical` | `.github/workflows/contract-driven-gates.yml` | PR only |
| `nightly-integration` | `.github/workflows/contract-driven-gates.yml` | weekly schedule / dispatch |
| `scheduled-stress-soak` | `.github/workflows/contract-driven-gates.yml` | weekly schedule / dispatch |

No new workflow files required. All new tests fall under existing gate commands.

## Promotion Policy

All new tests in this change are added under existing gate commands — no new gate tiers are introduced. The `frontend-type-check` gate is already informational; no new informational gates are added. The `playwright-resilience` and `playwright-data-boundary` gates are already Tier 1 required; the new specs fall within their existing commands.

No gates change status (informational → required) as a result of this change.

## Rollback Policy

- If any Tier 1 required gate turns red on `main` after merge, no further PRs may land until restored.
- No DB migrations in this change; no down migration required.
- Rollback mechanism: revert the feature PR on `main`. TTL bifurcation and the progress endpoint are additive — existing clients unaffected. Pre-warm is startup-only; missing warm keys fall back to on-demand Oracle queries (existing behaviour).

## Merge Eligibility Decision

**Ready to merge** when all of the following are green:

- [ ] contract-validate (`cdd-kit validate`) — all validations pass
- [ ] lint (ruff) — 0 errors
- [ ] unit-mock-integration (pytest) — 78+ tests pass
- [ ] frontend-unit (Vitest) — 302+ tests pass
- [ ] css-governance — 0 errors
- [ ] playwright-resilience — all resilience specs pass (including new 503 mid-poll extension)
- [ ] playwright-data-boundary — all data-boundary specs pass (including new malformed-progress extension)
- [ ] playwright-critical-journeys — hold-overview, reject-history, query-tool pass
