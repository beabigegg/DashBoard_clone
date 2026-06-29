# CI/CD Gate Plan — msd-type-package-filter

Change: new `GET /api/mid-section-defect/container-filter-options` endpoint; `pj_types[]`/`packages[]`
params on analysis endpoint; FilterBar MultiSelects.  Tier 2 feature-add, medium risk.

## Required Gates (PR-blocking)

| gate | tier | required | trigger | command / workflow | artifact |
|---|---:|:---:|---|---|---|
| unit-and-integration-tests | 1 | yes | pull_request | `backend-tests.yml` → `pytest tests/ --ignore=tests/e2e --ignore=tests/stress` | none |
| openapi-sync | 1 | yes | pull_request (paths: api-contract.md, openapi.json) | `openapi-sync.yml` → `cdd-kit openapi export --check` | none |
| contract-and-fast-tests | 1 | yes | pull_request | `contract-driven-gates.yml` → `pip install jsonschema && cdd-kit validate --contracts` | none |
| frontend-unit-tests | 1 | yes | pull_request | `frontend-tests.yml` → vitest + css:check + legacy node --test | none |
| e2e-mid-section-defect | 1 | yes | pull_request | `frontend-tests.yml` step (added) → `npx playwright test tests/playwright/mid-section-defect.spec.ts` | none |

Test-plan rows covered per gate:
- `unit-and-integration-tests`: test-plan.md AC-1 through AC-7 unit + integration rows (all Tier-0/1 pytest rows)
- `openapi-sync`: enforces dual-export requirement — both `contracts/openapi.json` and `contracts/api/openapi.json` must be regenerated after api-contract.md edits
- `contract-and-fast-tests`: targeted sample capture for `get_mid_section_defect_container_filter_options`; `jsonschema` installed before `cdd-kit validate --contracts`
- `frontend-unit-tests`: test-plan.md AC-3 composable unit rows; CSS governance (Rule 6 scoping)
- `e2e-mid-section-defect`: test-plan.md AC-3 (MultiSelect render), AC-4 (Type narrows Package) E2E rows

## Informational Gates (advisory)

| gate | tier | trigger | command / workflow | note |
|---|---:|---|---|---|
| type-check | 2 | pull_request | `frontend-tests.yml` → `npm run type-check` (`continue-on-error: true`) | Promote to required after TS migration stabilises |
| real-infra-smoke | 2 | pull_request | `backend-tests.yml` → bounded 3-file redis/concurrency smoke | Non-blocking; see `docs/ci_real_infra_gate_policy.md` for promotion thresholds |

## Nightly/Weekly/Manual Gates

No new nightly or weekly gates added for this change (task 6.4 = skipped).
In-memory post-query filtering introduces no new load surface; existing nightly
`oracle-fault-injection` and `multi-worker-concurrency` jobs are unchanged.

## Workflow

One step added to `.github/workflows/frontend-tests.yml` in the `frontend-unit-tests` job:

```yaml
- name: Run mid-section-defect e2e spec (msd-type-package-filter, Tier 1)
  working-directory: frontend
  # ci-gates.md gate: e2e-mid-section-defect (Tier 1, required)
  # Covers: AC-3 MultiSelect render, AC-4 Type-narrows-Package (test-plan.md E2E rows)
  # npx playwright install --with-deps chromium already executed in "Install Playwright browsers"
  run: npx playwright test tests/playwright/mid-section-defect.spec.ts
```

No new workflow files. No new nightly/weekly schedule entries. No new secrets or OIDC changes.
`pip install jsonschema` is already present in `contract-driven-gates.yml` before `cdd-kit validate --contracts`.

## Promotion Policy

Merge is eligible when all five required gates pass on the PR head SHA:
`unit-and-integration-tests`, `openapi-sync`, `contract-and-fast-tests`,
`frontend-unit-tests`, `e2e-mid-section-defect`.

The `type-check` and `real-infra-smoke` informational gates must not be broken
at merge time; a persistent red on either gates requires a follow-up ticket
before the next PR in this module lands.

## Rollback Policy

Revert the merge commit with `git revert <sha>`. No DB migration and no new
Redis cache namespace to undo. The existing `container_filter_cache` 24h TTL
will naturally expire stale filter-options data. No feature flag is gating
this change; rollback is the only off switch.
