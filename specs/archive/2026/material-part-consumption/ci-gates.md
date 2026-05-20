# CI/CD Gate Review

change-id: material-part-consumption
risk: high
tier: 1
last-changed: 2026-05-20

## Required Gates for This Change

| gate | tier | required | trigger | command/workflow | artifact |
|---|---:|:---:|---|---|---|
| contract-validate | 0 | yes | local / PR | `cdd-kit validate` | — |
| lint | 0 | yes | local / PR | `ruff check .` | — |
| unit-mock-integration | 1 | yes | PR | `pytest tests/test_material_consumption_service.py tests/test_material_consumption_routes.py tests/routes/ -x` (via `backend-tests.yml` `unit-and-integration-tests`) | junit XML |
| frontend-unit | 1 | yes | PR | `cd frontend && npm test` (via `frontend-tests.yml`) | vitest report |
| css-governance | 1 | yes | PR | `cd frontend && npm run css:check` — enforces `.theme-material-consumption` scope isolation (CSS Rule 6) | governance report |
| frontend-type-check | 1 | informational | PR | `cd frontend && npm run type-check` (via `frontend-tests.yml`, continue-on-error) | — |
| playwright-critical-journeys | 1 | yes | PR | `cd frontend && npx playwright test tests/playwright/material-consumption.spec.ts` (extend existing `e2e-critical` job) | playwright trace, 7 days |
| playwright-data-boundary | 1 | yes | PR | `cd frontend && npx playwright test tests/playwright/material-consumption-data-boundary.spec.ts` | playwright trace, 7 days |
| playwright-resilience | 1 | yes | PR | `cd frontend && npx playwright test tests/playwright/material-consumption-resilience.spec.ts` | playwright trace, 7 days |
| fuzz | 1 | yes | PR | `pytest tests/routes/test_fuzz_routes.py -x` (extend existing file; covered by `unit-and-integration-tests`) | junit XML |
| nightly-integration | 3 | yes (nightly) | schedule / dispatch | `pytest tests/integration/ --run-integration-real -m "integration_real or multi_worker" -x` (existing `backend-tests.yml` `nightly-integration-real` job) | test report, 30 days |
| stress-summary-aggregate | 3 | yes (nightly) | schedule / dispatch | `pytest tests/stress/test_material_consumption_stress.py -m stress --run-stress -x` — target: 17.8M-row multi-part wildcard summary ≤ 5 s (test-plan.md rows `test_summary_aggregate_large_table_under_5s`, `test_concurrent_granularity_switches_cache_only`) | perf report, 90 days |
| soak-cache-hit | 4 | yes (weekly) | schedule (Sunday 18:00 UTC) / dispatch | extend `soak-tests.yml` soak job to include material-consumption granularity-switch path — target: cache hit ≤ 2 s (SYS-02) over 8 h | soak metrics JSON, 30 days |
| worker-deploy-verify | 5 | yes (manual pre-deploy) | workflow_dispatch | verify `material-consumption` queue in Admin Dashboard `/admin/api/worker/status` shows ≥ 1 worker; see deploy checklist below | — |

## CI/CD Workflow

No new workflow files are required. All gates fit within existing workflows with the following additions:

**`backend-tests.yml` (`unit-and-integration-tests` job) — path filter addition**

Add `src/mes_dashboard/workers/**` and `src/mes_dashboard/sql/**` to the existing `pull_request.paths` filter so changes to the new SQL and worker files trigger the job.

**`backend-tests.yml` (`stress-tests` nightly scope) — new stress test file**

`tests/stress/test_material_consumption_stress.py` is picked up automatically by the existing `stress-load` gate command (`pytest tests/stress/ -m stress --run-stress`). No job change needed; the file registers itself.

**`frontend-tests.yml` — no change needed**

New Vitest files under `frontend/src/material-consumption/__tests__/` and new Playwright specs under `frontend/tests/playwright/` are discovered automatically by existing glob patterns.

**`stress-tests.yml` — no change needed**

Nightly stress run for `test_material_consumption_stress.py` is covered by the existing `scheduled-stress-soak` gate in `contract-driven-gates.yml` and by the `stress-tests.yml` `workflow_dispatch` path.

**`soak-tests.yml` — no change needed for scheduling**

Material-consumption granularity-switch soak assertions extend `tests/integration/test_soak_workload.py`. The existing weekly Sunday 18:00 UTC schedule picks them up. A `soak` pytest marker is required on the new assertions.

### Worker Deploy Gate (Tier 5 — manual dispatch)

Before serving traffic to `/material-consumption`, a manual deploy verification step is required. Add the following dispatch input to `.github/workflows/e2e-tests.yml` or run locally against staging:

```bash
# Verify material-consumption RQ worker is live
curl -s http://<host>/admin/api/worker/status | \
  python3 -c "import sys,json; q=[w for w in json.load(sys.stdin)['data'] if 'material-consumption' in w.get('queues',[])]; print('OK' if q else 'FAIL')"

# Verify asset_readiness_manifest.json entry exists (no gunicorn crash on startup)
python3 -c "
import json
m = json.load(open('docs/migration/full-modernization-architecture-blueprint/asset_readiness_manifest.json'))
assert '/material-consumption' in m, 'MISSING entry — gunicorn will crash'
print('asset_readiness_manifest: OK')
"
```

## Promotion Policy

All of the following must be true before merge to `main` is allowed:

1. All Tier 1 required gates are green: `unit-mock-integration`, `frontend-unit`, `css-governance`, `playwright-critical-journeys`, `playwright-data-boundary`, `playwright-resilience`, `fuzz`.
2. `contract-validate` and `lint` pass locally (Tier 0).
3. `qa-reviewer` agent has approved in `specs/changes/material-part-consumption/agent-log/qa-reviewer.yml`.
4. `frontend-type-check` (informational) failure, if any, is documented and triaged before merge.
5. `nightly-integration` green run logged within the preceding 24 h OR gate waived by platform-team with written justification in the PR.
6. Worker deploy verification (Tier 5) completed against staging before production traffic cutover.

Stress (Tier 3 nightly) and soak (Tier 4 weekly) gate failures after merge must be triaged within 1 business day (Tier 3) or trigger a production-readiness review (Tier 4).

## Rollback Policy

Execute ALL steps below BEFORE restarting gunicorn. Partial rollback is not safe.

1. **Remove `asset_readiness_manifest.json` entry first.**
   `_validate_in_scope_asset_readiness()` in `app.py` runs at gunicorn startup via `lru_cache`. A stale `/material-consumption` entry with no corresponding dist asset crashes all workers immediately.
   ```bash
   # Edit docs/migration/full-modernization-architecture-blueprint/asset_readiness_manifest.json
   # Remove the "/material-consumption" key, then:
   python3 -c "import json; m=json.load(open('docs/migration/full-modernization-architecture-blueprint/asset_readiness_manifest.json')); assert '/material-consumption' not in m"
   ```

2. **Remove `data/page_status.json` entry.**
   Stale entry causes the sidebar to emit "缺少 route contract: /material-consumption" on every page load.
   ```bash
   # Remove the /material-consumption object from the "pages" array in data/page_status.json
   ```

3. **Clean spool parquet files.**
   Orphaned files become schema-mismatched if the spool schema was written by the rolled-back version.
   ```bash
   rm -f tmp/query_spool/material_consumption/*.parquet
   ```

4. **Disable and stop the `material-consumption` worker systemd unit and its watchdog.**
   ```bash
   systemctl disable --now material-consumption-worker.service
   systemctl disable --now material-consumption-worker-watchdog.service
   ```

5. Restart gunicorn. Verify startup logs contain no `RuntimeError` from `_validate_in_scope_asset_readiness`.

**Parquet schema gate**: any future PR that renames, adds, or removes a column in the `material_consumption_service.py` spool write path MUST add `rm -f tmp/query_spool/material_consumption/*.parquet` to both its deploy and rollback steps and update `contracts/data/data-shape-contract.md §3.9`.

## Merge Eligibility

blocked — all Tier 1 required gates must be green and `qa-reviewer` approval recorded before this change is mergeable.
