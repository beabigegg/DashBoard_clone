# CI/CD Gate Review — migrate-shared-composables-ts

## Required Gates for This Change

| gate | tier | required | trigger | command / workflow | artifact |
|---|---:|---:|---|---|---|
| contract-validate | 0 | yes | local pre-PR | `cdd-kit validate` | — |
| audit-static (AC-7) | 0 | yes | local pre-PR | `grep -r "shared-composables.*\.js" tests/**/*.py` — zero hits required | — |
| frontend-type-check | 0/1 | informational | local + PR (`frontend-tests.yml` — `Type check (vue-tsc --noEmit)`) | `cd frontend && npm run type-check` | — |
| frontend-unit | 1 | yes (blocks merge) | PR (`frontend-tests.yml` — `Run vitest suite`) | `cd frontend && npm run test` | vitest report |
| frontend-legacy | 1 | yes (blocks merge) | PR (`frontend-tests.yml` — `Run legacy node --test suite`) | `cd frontend && npm run test:legacy` | — |
| test-discovery | 1 | yes (blocks merge) | PR (`frontend-tests.yml` — `Verify test discovery`) | shell assertion: vitest file count > 0 and legacy file count > 0 | — |
| css-governance | 1 | yes (blocks merge) | PR (separate workflow) | `cd frontend && npm run css:check` | governance report |
| build-smoke (AC-8) | 1 | yes (blocks merge) | PR (triggered by `frontend/src/**` path filter) | `cd frontend && npm run build` | — |

Gates not listed above (playwright-resilience, playwright-data-boundary, playwright-critical-journeys, nightly-integration, stress-load, soak) are unaffected by this change — no runtime behavior change, no new routes, no new Python service paths.

---

## Affected Gates (scope expansion — no command or tier change)

### frontend-type-check (Tier 0/1, informational)

**What changed:** `frontend/tsconfig.json` `include` now contains `["src/core/**/*", "src/shared-composables/**/*"]`. The `npm run type-check` command (`vue-tsc --noEmit`) is identical; the gate now type-checks an additional 11 `.ts` modules under `strict: true`.

- Before Phase 1b: 21 modules covered (`src/core/**/*`).
- From Phase 1b onward: 32+ modules covered (`src/core/**/*` + `src/shared-composables/**/*`).
- Gate status: remains **informational** (`continue-on-error: true` in `.github/workflows/frontend-tests.yml` line 38). Promotion follows the Informational Gate Promotion Policy (see below).
- Documented in `contracts/ci/ci-gate-contract.md` §Gate Compatibility Notes — Phase 1b entry (schema-version 1.3.1, patch bump).
- No workflow YAML edit required.

### frontend-unit (Tier 1, required)

**What changed:** Vitest now resolves imports from `frontend/src/shared-composables/*.ts` (sources renamed from `.js`). Import specifiers in six test files were updated to `.ts` or extension-dropped. The gate command and GitHub Checks job name (`Run vitest suite`) are unchanged.

Affected test files whose import specifiers were updated:
- `frontend/tests/shared-composables/useAsyncJobPolling.test.js`
- `frontend/tests/shared-composables/useAutoRefresh.test.js`
- `frontend/tests/shared-composables/useRequestGuard.test.js`
- `frontend/tests/abort/production-history-abort.test.js` (lines 25, 31)
- `frontend/tests/abort/reject-history-abort.test.js` (lines 49, 70)
- `frontend/tests/abort/query-tool-abort.test.js` (lines 38, 53)

No workflow YAML edit required.

### frontend-legacy (Tier 1, required)

`npm run test:legacy` runs `tests/legacy/*.test.js` via Node `--experimental-strip-types`. These suites do not import `shared-composables` directly; no specifier changes required. Gate remains unchanged — listed for completeness.

No workflow YAML edit required.

---

## Local Pre-Merge Gate Command Sequence (Tier 0)

Run in this order before opening the PR:

```bash
# 1. Contract validate
cdd-kit validate

# 2. Python parity audit (AC-7) — must produce zero output
grep -r "shared-composables.*\.js" tests/**/*.py \
  && echo "FAIL: found stale .js refs" || echo "OK: no stale refs"

# 3. TypeScript compile contract (proves AC-1 through AC-4)
cd frontend && npm run type-check

# 4. Vitest unit + integration suites (proves AC-5, AC-6)
cd frontend && npm run test

# 5. Legacy node --test suite
cd frontend && npm run test:legacy

# 6. Build smoke (proves AC-8)
cd frontend && npm run build
```

All six steps must exit 0 before the PR is opened. Shorthand: `npm run type-check && npm run test && npm run build` (from `frontend/`).

---

## PR-Required Gates (Block Merge)

Jobs in `.github/workflows/frontend-tests.yml` that must be green:

| GitHub Checks job name | command | blocks merge |
|---|---|---|
| `Run vitest suite` | `npm test` | yes |
| `Run legacy node --test suite` | `npm run test:legacy` | yes |
| `Verify test discovery` | shell assertion | yes |

The `Type check (vue-tsc --noEmit)` step has `continue-on-error: true` — it is **informational** and does not block merge.

---

## PR-Informational Gates (Do Not Block Merge)

| gate | workflow step | rationale |
|---|---|---|
| `frontend-type-check` | `.github/workflows/frontend-tests.yml` lines 35-38 | Informational per `ci-gate-contract.md` §Gate Inventory; informational-gate promotion criteria not yet met for Phase 1b scope. |

---

## New Gates Introduced

None. This change expands the effective coverage scope of existing gates only. No new workflow jobs, no new required-check names, no new Makefile targets were added.

---

## Workflow Files Changed

None. The existing `.github/workflows/frontend-tests.yml` already satisfies all requirements:

- Path filter `frontend/src/**` triggers on the renamed `.ts` sources.
- `actions/setup-node@v4` with `node-version: "22"` satisfies the Node >=22.6 constraint (relevant to Python parity tests in other workflows; not directly relevant here since `shared-composables` has no Python parity tests).
- `npm run type-check` step with `continue-on-error: true` is already present.
- `npm test` (Vitest) and `npm run test:legacy` steps are already present.

No edits to any `.github/workflows/*.yml` file are required for this change.

---

## tsconfig.json Coverage Confirmation

`frontend/tsconfig.json` `include` is confirmed as `["src/core/**/*", "src/shared-composables/**/*"]` at line 19 (applied by frontend-engineer). Settings `allowJs: false` and `strict: true` apply to both paths uniformly. No further tsconfig edit is needed.

---

## New Workflow Changes Applied

No workflow file changes applied. Existing `frontend-tests.yml` is sufficient.

---

## Required Check Policy

Tier 1 gates that block merge for this change:

- `Run vitest suite` (frontend-unit)
- `Run legacy node --test suite` (frontend-legacy)
- `Verify test discovery` (discovery assertion)

These names match the `name:` fields in `frontend-tests.yml` and can be bound directly to branch-protection required-status-checks.

---

## Informational Gate Promotion Policy

`frontend-type-check` may be promoted from informational to required after all of:

1. 20 calendar days or 60 PR runs with the expanded `shared-composables` scope active.
2. Pass rate above the agreed threshold (platform-team to set once Phase 1c scope is also merged).
3. All type-check failures triaged and documented.
4. Runtime within the acceptable limit for a Tier 1 required gate.

Promotion requires a Contract Change PR that:
- Updates `contracts/ci/ci-gate-contract.md` gate table entry for `frontend-type-check` from `informational` to `yes`.
- Removes `continue-on-error: true` from `.github/workflows/frontend-tests.yml` line 38.

---

## Rollback Policy

This change is a pure compile-time migration (`.js` → `.ts` rename + `tsconfig.json` include expansion). There is no runtime behavior change, no DB migration, no feature flag.

Rollback procedure if post-merge CI regression is discovered:

1. Revert the PR commit on `main` — `.ts` sources and `tsconfig.json` change revert atomically.
2. No DB down-migration required.
3. No feature-flag toggle required.
4. Confirm the reverted state is clean: `cd frontend && npm run type-check && npm run test && npm run build`.

---

## Artifact Retention

No new artifact types introduced. Existing retention policy from `ci-gate-contract.md` applies:

| artifact | retention |
|---|---|
| vitest report | 30 days |
| Playwright traces | 7 days (longer on failure) |

---

## Merge Eligibility

**mergeable**

All Tier 1 required gates are covered by the existing `frontend-tests.yml` workflow without modification. The type-check gate remains informational and does not block. No new gates are required. The local pre-merge sequence (contract-validate, grep audit, type-check, test, build) must pass before PR open.
