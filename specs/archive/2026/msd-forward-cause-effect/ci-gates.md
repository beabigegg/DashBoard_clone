# CI/CD Gate Review — msd-forward-cause-effect

## Required Gates for This Change

| gate | tier | required | trigger | command / workflow | artifact |
|---|---:|:---:|---|---|---|
| ruff lint | 0 | yes | local / PR | `ruff check .` | — |
| vue-tsc type-check | 0 | yes | local / PR | `cd frontend && npm run type-check` | — |
| frontend build | 1 | yes | PR | `cd frontend && npm run build` | — |
| css governance | 1 | yes | PR — `frontend-tests.yml` `frontend-unit-tests` | `cd frontend && npm run css:check` | — |
| contract validators | 1 | yes | PR — `contract-driven-gates.yml` | `pip install jsonschema && cdd-kit validate --contracts` | — |
| openapi-sync (both files) | 1 | yes | PR — `openapi-sync.yml` (see Workflow Changes) | `cdd-kit openapi export --check` × 2 | — |
| unit-and-integration-tests | 1 | yes | PR — `backend-tests.yml` | `pytest tests/ --ignore=tests/e2e --ignore=tests/stress` | — |
| xfail-flip (AC-6) | 1 | yes | subsumed by unit-and-integration-tests | 2 `xfail(strict=True)` forward-summary spool tests green (markers removed); `strict=True` makes them loud failures if DuckDB path is incomplete | — |
| vitest + legacy tests | 1 | yes | PR — `frontend-tests.yml` | `npm test && npm run test:legacy` | — |
| playwright msd e2e | 1 | yes | PR — `frontend-tests.yml` `Run mid-section-defect e2e spec` | `npx playwright test tests/playwright/mid-section-defect.spec.ts` (chromium install already present) | — |
| visual-review evidence bundle | 2 | informational | PR — manual capture | Screenshots of Sankey hero, heatmap toggle, amplification KPI; stored as `specs/changes/msd-forward-cause-effect/visual-review-report.md` | `visual-review-report.md` |
| nightly real-infra integration | 3 | informational | schedule `0 2 * * *` — `backend-tests.yml` `nightly-integration-real` | `pytest tests/integration/test_material_trace_rq_async.py --run-integration-real` | — |
| stress — spool concurrency + DuckDB forward | 5 | informational | `workflow_dispatch` — `stress-tests.yml` | `pytest tests/stress/test_mid_section_defect_stress.py -m stress --run-stress` | `stress-soak-report.md` |
| soak — spool + RQ concurrency surface | 4 | informational | schedule `0 18 * * 0` — `soak-tests.yml` | `pytest tests/integration/test_soak_workload.py --run-integration-real -m soak` | `stress-soak-report.md` |

> test-plan.md rows covered: unit (`_attribute_forward_defects` re-keying, amplification math incl. divide-by-zero, aggregation builders), integration (DuckDB forward summary spool-write/read, RQ orchestration), contract (response-sample regen, openapi mirrors), E2E (Sankey click cross-filter, heatmap toggle, KPI render, detail "detection loss reason" column), data-boundary (empty/zero detection, no-descendant lineage, Top-N truncation).

## Workflow Changes Applied

### `openapi-sync.yml` — extend path trigger and add mirror check

This change edits forward-analysis endpoint fields and the forward detail schema. Per CLAUDE.md: _"regen BOTH `contracts/openapi.json` AND `contracts/api/openapi.json` after every endpoint-table, schema, or schema-version edit."_ The existing workflow only watches and checks `contracts/openapi.json`.

Applied changes to `.github/workflows/openapi-sync.yml`:
1. Added `contracts/api/openapi.json` to the `paths:` filter on both `push` and `pull_request` triggers.
2. Added a second step: `cdd-kit openapi export --check --out contracts/api/openapi.json` to verify the mirror is in sync.

### `frontend-tests.yml` — no change needed

The `Run mid-section-defect e2e spec` step already runs `mid-section-defect.spec.ts`, and `npx playwright install --with-deps chromium` already precedes it. New Sankey/heatmap/detail assertions in that spec file are automatically exercised by the existing step.

### No other workflow files modified

No new env var or feature flag (3b dropped; DuckDB-forward is a direct replace). The spool reuses the existing `msd-events` namespace. Stress/soak files need no path changes — new test files land under `tests/stress/` and `tests/integration/` already covered by those workflows.

## Promotion Policy

- Tier 2 informational (visual-review) → Tier 1 required: two consecutive PRs produce passing visual evidence with no reviewer-flagged regressions.
- Tier 3 informational (nightly real-infra) → Tier 1 required: 20-day / 60-run 100% pass rate and p95 wall time < 180 s (matches the `real-infra-smoke` threshold in `backend-tests.yml`). Requires a dedicated PR updating `ci-gates.md` and adding the job name to branch protection.
- Tier 5 manual (stress) → Tier 4 weekly scheduled: `stress-soak-report.md` filed, no p99 latency regression over DuckDB forward path. Requires a dedicated PR updating `ci-gates.md` and `stress-tests.yml` schedule trigger.
- Gate demotions (required → informational): flake rate > 5% over 20 runs, tracking issue open, owner and exit date both set before the demotion PR merges.

## Rollback Policy

Reference `design.md §Migration / Rollback` for the authoritative sequence. CI-visible tripwires:

1. **Lineage spool schema rollback**: `_SCHEMA_VERSION` bump in `msd_duckdb_runtime.py` must be accompanied by an `rm msd-events/*_lineage.parquet` step in the rollback runbook; execute on all deployed instances before restarting. `unit-and-integration-tests` catches a schema mismatch on stale parquet at the next PR.
2. **DuckDB-forward cutover rollback**: revert the `get_summary` forward branch to `return None` (restores in-memory `build_trace_aggregation_from_events`). The in-memory builder must NOT be removed until the DuckDB path is proven stable for one release cycle; removal is a follow-up PR.
3. **xfail tripwire on partial rollback**: do not re-add `xfail(strict=True)` markers; use plain `xfail` (no `strict`) and file a task — `strict=True` would permanently fail CI if the in-memory builder is also absent.
4. **Response-sample churn**: before committing, `git checkout tests/contract/samples/` to revert unrelated sample churn; re-stage only the samples this change altered.

## Merge Eligibility

Mergeable when all Tier 1 required gates are green:
- `unit-and-integration-tests` (includes xfail-flip AC-6 and data-boundary / resilience tests)
- `openapi-sync` (both `contracts/openapi.json` and `contracts/api/openapi.json`)
- `contract-and-fast-tests` (`cdd-kit validate --contracts`)
- `frontend-unit-tests` (vitest, vue-tsc, css:check, build, Playwright msd spec)

Visual-review bundle is **informational-risk**: merge is not blocked, but a reviewer must acknowledge the evidence before approving.

