# CI/CD Gate Plan — wip-hold-drilldown-filters

## Change ID

wip-hold-drilldown-filters

## Change Tier

**Tier 3 — Feature Enhancement** (no new CI jobs; no new CI contract entries required)

This change adds three new backend filter params (`workflow`, `bops`, `pjFunction`), a `pjType` lot-row field to the WIP detail endpoint, and frontend MatrixTable cell drilldown + FilterPanel 3×3 reorder. No new infrastructure, no new schema gates, no migration scripts.

---

## Local Gate Results (verified 2026-05-13)

| gate | result | details |
|---|---|---|
| frontend-unit (Vitest) | PASS | 295/295 tests, 29 test files |
| frontend-type-check (vue-tsc) | PASS | 0 errors |
| backend-unit (pytest test_wip_routes.py) | PASS | 40/40 tests |
| css-governance | PASS (warnings only) | 0 errors, 47 warnings — all pre-existing; no new violations introduced by this change |
| contract-validate (cdd-kit validate) | PASS | 141 endpoints, 41 env vars, all validations passed |

---

## Pre-Merge Required Gates (Tier 1)

### frontend-unit

```bash
cd frontend && npm run test
```

- Expected: 295/295 pass (or more if new tests were added)
- Artifact: Vitest report (retained 30 days)
- Gate status: **required** (blocks merge)

### css-governance

```bash
cd frontend && npm run css:check
```

- Expected: 0 errors. Warnings are allowed and do not block merge.
- Artifact: governance report
- Gate status: **required** (blocks merge on errors only)
- Note: The 47 warnings present in this run are all pre-existing across unrelated modules (admin-dashboard, shared-ui, anomaly-overview, etc.). No new violations were introduced by this change.

### contract-validate

```bash
cdd-kit validate
```

- Expected: all validations pass (contracts present, API semantic, env semantic, CI gates, spec traceability, contract versions)
- Gate status: **required** (blocks merge)

### backend-unit (pytest — wip routes)

```bash
conda run -n mes-dashboard pytest tests/test_wip_routes.py -x -q
```

Full pre-merge backend suite (excludes real-infra and stress):

```bash
conda run -n mes-dashboard pytest \
  -m "not (e2e or integration_real or stress or load or soak or multi_worker)" \
  --ignore=tests/integration --ignore=tests/stress --ignore=tests/e2e --ignore=tests/manual \
  -x
```

- Expected: all tests pass (40/40 for wip_routes specifically)
- Artifact: junit XML (retained 30 days)
- Gate status: **required** (blocks merge)

### playwright-critical-journeys

```bash
cd frontend && npx playwright test \
  tests/playwright/hold-overview.spec.js \
  tests/playwright/reject-history.spec.js \
  tests/playwright/query-tool.spec.js
```

- Expected: all critical-journey specs pass; hold-overview.spec.js specifically validates that existing Hold Matrix drilldown behaviour is unchanged by this change
- Artifact: Playwright traces (retained 7 days; longer on failure)
- Gate status: **required** (blocks merge)

### playwright-resilience

```bash
cd frontend && npx playwright test tests/playwright/resilience/
```

- Gate status: **required** (blocks merge)

### playwright-data-boundary

```bash
cd frontend && npx playwright test tests/playwright/data-boundary/
```

- Gate status: **required** (blocks merge)

---

## Informational Gates (Tier 1 — non-blocking)

### frontend-type-check

```bash
cd frontend && npm run type-check
```

- Result: 0 errors (verified locally)
- Gate status: **informational** (continue-on-error: true in CI; does not block merge)
- Coverage: includes `wip-overview/`, `wip-detail/`, `hold-overview/`, `hold-detail/` per Phase 3 scope expansion (ci-gate-contract.md §frontend-type-check scope expansion — migrate-wip-hold-ts, schema-version 1.3.7)

---

## Gates Not Applicable to This Change

| gate | reason not applicable |
|---|---|
| lint (ruff) | Python linter; applicable gate for Python changes. Run if backend files are modified, but no new Python lint rules introduced. |
| visual-regression | Tier 2 informational; not triggered for Tier 3 feature enhancements without explicit visual regression contract update. |
| nightly-integration | Tier 3; not a pre-merge gate. Runs on weekly schedule against real Oracle/Redis. |
| stress-load | Tier 4; weekly schedule only. Not applicable to filter-param additions. |
| soak | Tier 4; weekly schedule only. |
| DB migration rollback | No schema migration involved in this change. |

---

## New Workflow Changes

None. This change is Tier 3 — no new CI jobs, no new `.github/workflows/` files, and no new gate entries in `contracts/ci/ci-gate-contract.md`. The existing gate inventory in ci-gate-contract.md schema-version 1.3.7 fully covers this change.

---

## CI Contract Coverage Confirmation

Reviewed `contracts/ci/ci-gate-contract.md` (schema-version 1.3.7, last-changed 2026-05-13):

- All gates exercised by this change (frontend-unit, css-governance, contract-validate, backend pytest, playwright-critical-journeys, frontend-type-check) are present in the gate inventory table.
- **No schema-version bump required**: no new gates introduced, no gate tier or command changes.
- The `wip-overview/`, `wip-detail/`, `hold-overview/`, `hold-detail/` TypeScript scope is already recorded under the `migrate-wip-hold-ts` compatibility note (§ frontend-type-check scope expansion, Phase 3).

---

## Promotion policy

Informational gates follow the standard Informational Gate Promotion Policy documented in `contracts/ci/ci-gate-contract.md`. Promotion requires 20 calendar days or 60 runs, pass rate above agreed threshold, failures triaged, runtime within acceptable limit, and an assigned owner.

No gate introduced in this change is a candidate for immediate promotion — `frontend-type-check` was already informational before this change and remains so. All other gates listed here were already `required` before this change.

---

## Required Check Policy

Per `contracts/ci/ci-gate-contract.md`:

- **Tier 1** required gates (frontend-unit, css-governance, backend-unit, playwright-critical-journeys, playwright-resilience, playwright-data-boundary) **block merge**. All must be green before this PR may land.
- **Tier 1** informational gates (frontend-type-check) run on PR but do not block merge.
- **Tier 3/4** gates (nightly-integration, stress-load, soak) run on schedule; failure must be triaged within 1 business day for Tier 3, and triggers production-readiness review for Tier 4.

---

## Rollback Policy

- If any Tier 1 required gate turns red on `main` after merge, no further PRs may land until the gate is restored to green.
- This change introduces no DB migrations; no down migration is required for rollback.
- Rollback mechanism: revert the feature PR on `main`. The new filter params are additive and backward-compatible — existing clients that do not send the new params receive the same response as before.

---

## Artifact Retention

| artifact | retention |
|---|---|
| pytest / vitest report | 30 days |
| Playwright traces | 7 days (longer on failure) |
| Screenshot diffs | 30 days |
| Soak/stress reports | 90 days |

---

## Merge Eligibility Decision

**Ready to merge** when all of the following are green:

- [ ] frontend-unit (Vitest) — 295+ tests pass
- [ ] css-governance — 0 errors
- [ ] contract-validate (`cdd-kit validate`) — all validations pass
- [ ] backend-unit (pytest) — all pre-merge tests pass
- [ ] playwright-critical-journeys — hold-overview, reject-history, query-tool pass
- [ ] playwright-resilience — all resilience specs pass
- [ ] playwright-data-boundary — all data-boundary specs pass
