# CI/CD Gate Review

change-id: downtime-browser-duckdb
ci-gate-contract: 1.3.20 (bump from 1.3.19 — new Playwright spec confirmed by contract-reviewer)

## Required Gates for This Change

| gate | tier | required | trigger | command/workflow | artifact |
|---|---:|:---:|---|---|---|
| lint | 0 | yes | local/PR | `ruff check .` | — |
| contract-validate | 0 | yes | local/PR | `cdd-kit validate` | — |
| frontend-type-check | 0 | yes | local/PR | `cd frontend && npm run type-check` | — |
| unit-mock-integration | 1 | yes | pull_request | `pytest -m "not (e2e or integration_real or stress or load or soak or multi_worker)" --ignore=tests/integration --ignore=tests/stress --ignore=tests/e2e --ignore=tests/manual -x` | junit XML |
| frontend-unit | 1 | yes | pull_request | `cd frontend && npm run test` | vitest report |
| css-governance | 1 | yes | pull_request | `cd frontend && npm run css:check` | governance report |
| downtime-playwright-e2e | 1 | yes | pull_request | `cd frontend && npx playwright test tests/playwright/downtime-analysis.spec.ts` | playwright trace |
| playwright-resilience | 1 | yes | pull_request | `cd frontend && npx playwright test tests/playwright/resilience/` | playwright trace |
| playwright-data-boundary | 1 | yes | pull_request | `cd frontend && npx playwright test tests/playwright/data-boundary/` | playwright trace |
| integration-mock-oracle | 2 | informational | pull_request | `pytest tests/e2e/ -m local_e2e -x` | test report |
| nightly-integration | 3 | yes (nightly) | schedule/dispatch | `pytest tests/integration/ --run-integration-real -m "integration_real or multi_worker" -x` | test report |
| nightly-parity-regression | 3 | yes (nightly) | schedule/dispatch | `pytest tests/integration/test_downtime_parity_regression.py --run-integration-real` | parity report |
| stress-oom-elimination | 4 | yes (weekly) | schedule/dispatch | `pytest tests/stress/test_downtime_analysis_stress.py -m stress` | perf report |
| soak-memory-stable | 4 | yes (weekly) | schedule/dispatch | `pytest tests/integration/test_soak_workload.py --run-integration-real -m soak` | soak report |
| manual-flag-rollback | 5 | yes (pre-prod) | manual dispatch | set `DOWNTIME_BROWSER_DUCKDB=false`; run smoke; verify prior response shape | smoke log |

## CI/CD Workflow

### New/modified workflow steps

**`frontend-tests.yml`** — add before `npx playwright test tests/playwright/downtime-analysis.spec.ts`:

```yaml
- name: Install Playwright browsers
  run: npx playwright install --with-deps chromium
  working-directory: frontend
```

This step is required by CLAUDE.md ("New Playwright specs require a browser install step") because CI runners have no pre-installed Chromium. Without it the runner exits with "Executable doesn't exist."

**Concurrency** — `downtime-playwright-e2e` job must carry:

```yaml
concurrency:
  group: ${{ github.ref }}-downtime-e2e
  cancel-in-progress: true
```

**Artifact retention** — playwright trace for the new spec: `retention-days: 7` (30 on failure); stress/soak report: `retention-days: 90`.

No new workflow file is required. All gates fall into existing job shells (`contract-and-fast-tests`, `e2e-critical`, `frontend-unit-tests`, `nightly-integration`, `scheduled-stress-soak`).

## Promotion Policy

- `frontend-type-check` is already `required` for `downtime-analysis/` once `"src/downtime-analysis/**/*"` is added to `tsconfig.json` `include` (consistent with resource-history, reject-history precedents at ci 1.3.9 / 1.3.5).
- `integration-mock-oracle` starts informational (Tier 2). Promote to Tier 1 required after 20 days / 60 runs / pass rate > 98% / runtime < 3 min, per the Informational Gate Promotion Policy in `ci-gate-contract.md`.
- `nightly-parity-regression` (Python pandas vs DuckDB-WASM on 184k-row reference fixture) is Tier 3 required from day one — parity is a release-blocker per AC-3 (test-plan.md rows: `test_cross_shift_merge_parity_vs_reference_fixture` … `test_event_detail_table_parity_vs_reference_fixture`).
- No gate may be promoted to required until it has passed 20 consecutive runs with no flaky result; flaky tests are quarantined in an informational job with a named owner and a 30-day exit date.

## Rollback Policy

1. **Feature-flag rollback (preferred, no redeploy required)**: Set `DOWNTIME_BROWSER_DUCKDB=false` in the gunicorn environment and reload workers. The deprecated server-side enriched-spool path (`apply_view` + `downtime_analysis_events` parquets + `export_*_csv` streamers) is restored immediately; the `/query` response reverts to the prior `{query_id, summary, daily_trend, big_category, top_reasons}` shape.

2. **OOM risk caveat**: Rolling back to the server-side path (`flag=false`) without reinstating `_MAX_ORACLE_DAYS` accepts gunicorn worker OOM risk on queries wider than 90 days under the 6 GB/no-swap host profile. The flag-off path must only be used for short rollback windows. If the rollback window exceeds 24 hours, re-introduce the 90-day guard or migrate to a host with more RAM before re-enabling wide-range queries.

3. **Parquet cleanup (schema-breaking rollback)**: If the raw-spool schema shipped and must be abandoned, run:
   `rm -f tmp/query_spool/downtime_analysis_base_events/*.parquet tmp/query_spool/downtime_analysis_job_bridge/*.parquet`
   Per design.md D4, bumping `SCHEMA_VERSION` in `downtime_analysis_cache.py` also orphans live raw parquets by key without a manual `rm`.

4. **Enriched spool retention**: The old `downtime_analysis_events` namespace parquets do not need cleanup on cutover — they expire naturally via TTL (20h per ci-gate-contract §unify-duckdb-prewarm-rq note).

5. **Any Tier 1 gate failure blocks merge**; no new PR may land on `main` until the gate is green. Tier 3/4 failure opens an incident ticket; triage within 1 business day (Tier 3) or triggers production-readiness review (Tier 4).

## Merge Eligibility

**Blocked until all Tier 1 gates pass:**
- `unit-mock-integration` (covers AC-1, AC-2, AC-4, AC-6, AC-7 atomicity — test-plan.md §TestQueryRoute, §TestRawSpoolWriter, §TestTaxonomyBuilder, §TestMaxOracleDaysRemoved, §TestTwoParquetAtomicity)
- `frontend-unit` (covers AC-3, AC-4, AC-8 — test-plan.md §useDowntimeDuckDB.test.ts parity suite, all 7 view assertions)
- `css-governance` (no unscoped rules may be introduced; design confirms no new CSS)
- `frontend-type-check` (useDowntimeDuckDB.ts must compile under strict mode; `src/downtime-analysis/**/*` must be in tsconfig include)
- `downtime-playwright-e2e` (covers AC-5 zero-round-trip, AC-6 180d E2E, AC-7 error banners, AC-8 CSV blob — test-plan.md §playwright/downtime-analysis.spec.ts)
- `contract-validate` (verifies 5 CHANGELOG entries: api 1.15.0, data 1.13.0, business 1.17.0, env 1.0.7, ci 1.3.20)

**Informational risk (non-blocking):**
- `integration-mock-oracle` — both Oracle-fallback and prewarm-feed paths write raw parquets; per-kwarg filter forwarding (test-plan.md §TestPrewarmFeedRawWriter)

**Pre-production manual gate required before serving production traffic:**
- `manual-flag-rollback` (Tier 5): verify `DOWNTIME_BROWSER_DUCKDB=false` restores prior response shape and that the OOM-risk caveat is acknowledged by the operator.
