# CI/CD Gate Review

## Change ID: fix-equipment-lots-trim

All gates below are **pre-existing** and already scoped by path filters onto this
change's surface. No new gate tier, workflow file, or command is introduced —
confirmed by reading `.github/workflows/*.yml` triggers against the paths this
change touches (`src/mes_dashboard/sql/query_tool/equipment_lots.sql`,
`src/mes_dashboard/services/`, `src/mes_dashboard/routes/`, `tests/`,
`tests/integration/`, `frontend/src/query-tool/`, `frontend/tests/query-tool/`,
`contracts/api/api-contract.md`).

## Required Gates for This Change

| gate | tier | required | trigger | command/workflow | artifact |
|---|---:|:---:|---|---|---|
| contract-validate | 1 | yes | push/PR/schedule (no path filter) | `contract-driven-gates.yml` → `cdd-kit validate` | — |
| contract-validate-subset | 1 | yes | push/PR/schedule (no path filter) | `contract-driven-gates.yml` → `cdd-kit validate --contracts` | — |
| openapi-sync | 1 | yes | push/PR to `contracts/api/api-contract.md`, `contracts/openapi.json`, `contracts/api/openapi.json` | `openapi-sync.yml` → `cdd-kit openapi export --check --out contracts/openapi.json` (+ `--out contracts/api/openapi.json` mirror) | — |
| backend-unit-and-integration | 1 | yes | push/PR touching `src/mes_dashboard/{services,routes,sql,workers}/**`, `tests/**` | `backend-tests.yml` job `unit-and-integration-tests` → `pytest tests/ --ignore=tests/e2e --ignore=tests/stress` | pytest console log |
| frontend-unit (vitest) | 0/1 | yes | push/PR touching `frontend/src/**`, `frontend/tests/**` | `frontend-tests.yml` → `npm test` | vitest report |
| frontend-css-governance | 1 | yes | push/PR touching `frontend/src/**` | `frontend-tests.yml` → `npm run css:check` | governance report |
| frontend-type-check | 2 | no (informational) | push/PR touching `frontend/src/**` | `frontend-tests.yml` → `npm run type-check` (`continue-on-error: true`, pre-existing repo-wide policy, unrelated to this change) | tsc log |

### Tests added per test-plan.md that land in existing gates

| gate | new test rows (see test-plan.md) |
|---|---|
| backend-unit-and-integration | AC-1 (`test_equipment_lots_containername_trimmed_char_padded`, `test_equipment_lots_sql_trims_containername_like_productlinename`); AC-2 (`test_equipment_lots_char_padded_fixture_returns_nonempty_rows`); AC-4 (`test_equipment_lots_container_names_filters_via_upper_trim_in`, `test_equipment_lots_forwards_container_names_kwarg`); AC-5 (`test_equipment_lots_container_names_applied_in_sql_where_not_python_postfilter`); AC-6 (`test_equipment_lots_omitted_container_names_unchanged_behavior`, `test_equipment_lots_forwards_pagination` extended); sync/async parity (`TestEquipmentPeriodLotsParity::test_async_job_forwards_container_names_same_as_sync_route`, `test_execute_query_tool_job_lots_branch_binds_container_names_kwarg`) |
| frontend-unit (vitest) | AC-3/AC-7 in `frontend/tests/query-tool/useLotEquipmentQuery.test.js` (already DONE per test-plan.md Notes — vitest+vue-tsc green, recorded in test-evidence.yml) |
| openapi-sync | Not a test row — regenerates `contracts/openapi.json`/`contracts/api/openapi.json` to match `contracts/api/api-contract.md` schema-version 1.38.3 |

## openapi-sync-gate trigger verification (explicit finding, per task instruction)

Read `.github/workflows/openapi-sync.yml` directly (not assumed). Its `paths:` filter
(both `push` and `pull_request` triggers) is:
```
- 'contracts/api/api-contract.md'
- 'contracts/openapi.json'
- 'contracts/api/openapi.json'
- '.github/workflows/openapi-sync.yml'
```
GitHub Actions path filters are **file-level**, not section/line-level. The
contract-reviewer's note that "the endpoint table row itself needed no edit,
only a Compatibility Notes prose entry + schema-version bump" describes *what
changed inside* `contracts/api/api-contract.md` — it does not change the fact
that the file itself is modified. `git diff --stat contracts/api/api-contract.md`
confirms a working-tree change (schema-version `1.38.2` → `1.38.3` +
Compatibility Notes entry). **Conclusion: openapi-sync-gate WILL trigger** on
this change's PR/push.

**Blocking finding**: as of this review, `contracts/openapi.json` and
`contracts/api/openapi.json` both still report `info.version: "1.38.2"` (checked
directly), while `contracts/api/api-contract.md` is now at `schema-version:
1.38.3`. The `--check` step in `openapi-sync.yml` will **fail** against the
current tree. This is not a gap in gate coverage — the gate is correctly
positioned to catch it — but it is a required pre-merge action:
run `cdd-kit openapi export --out contracts/openapi.json` and
`cdd-kit openapi export --out contracts/api/openapi.json`, then commit both,
before opening/updating the PR.

## Workflow

No workflow file changes required. `backend-tests.yml`, `frontend-tests.yml`,
`contract-driven-gates.yml`, and `openapi-sync.yml` already cover every path this
change touches (verified above); no new gate tier, job, or trigger path is added.
CI/CD contract classification: `no` (see `change-classification.md`; tasks.yml
2.6/4.4 both `skipped`, "no CI/CD contract/workflow affected" — confirmed correct).

## Promotion Policy

Additive, backward-compatible change (bug fix + one new optional request field;
`deprecate-2-minors` policy not triggered — no field removed/renamed).

1. All Tier 1 required gates (`contract-validate`, `contract-validate-subset`,
   `openapi-sync`, `backend-unit-and-integration`, `frontend-unit`,
   `frontend-css-governance`) must pass green on the PR.
2. No nightly/weekly/Tier-3+ promotion needed — `test-plan.md` Out of Scope
   explicitly excludes E2E/visual/resilience/fuzz/stress/soak for this change,
   and `tasks.yml` 6.4 is expected to resolve `skipped` (no new nightly/weekly
   surface).
3. `frontend-type-check` stays Tier 2 informational — pre-existing repo policy
   (`continue-on-error: true`), unrelated to this change; no promotion proposed.
4. Merge eligible once Tier 1 gates are green **and** both `contracts/openapi.json`
   and `contracts/api/openapi.json` carry `info.version: "1.38.3"` (see blocking
   finding above).

## Rollback Policy

Value-only SQL fix + one new optional server-side filter param — no schema
migration, no spool namespace, no new RQ queue.

- **Flag-off rollback (preferred)**: none applicable — no feature flag gates
  this change (not a `*_USE_RQ`/`*_USE_UNIFIED_JOB` toggle). Revert is the only
  rollback path.
- **Hard rollback**: `git revert <merge-commit>`. Reverts `equipment_lots.sql`
  TRIM, the `container_names` param on `get_equipment_lots()` (sync route +
  async RQ job), the frontend `.trim()` defensive fix in
  `useLotEquipmentQuery.ts`, and the `contracts/api/api-contract.md`
  schema-version/Compatibility-Notes edit in one atomic commit.
- **No data/spool cleanup needed**: `query-tool` has no persistent spool
  (per `docs/architecture/cache-spool-patterns.md` — "query-tool has no
  persistent spool — skip parquet cleanup in its rollbacks"); no parquet
  schema version to bump or roll back.
- **No worker ops needed**: no new RQ queue, no new systemd unit, no env-var
  flag flip required to disable.
- **openapi mirrors**: reverting the merge commit also reverts
  `contracts/openapi.json`/`contracts/api/openapi.json` back to `1.38.2`
  (git-tracked, regenerated files are part of the same commit).

## Merge Eligibility

**mergeable** — all previously-blocking items closed:
- 4.1 (Backend implementation: SQL TRIM + `container_names` wiring) — `done`
- 3.1/3.2/3.4 (backend unit/contract/integration/data-boundary tests) — `done`, all green (5386 passed, 809 skipped, 1 xfailed full-suite; targeted files independently re-verified)
- 5.4 (QA review) — `done`, verdict: APPROVED
- `contracts/openapi.json` + `contracts/api/openapi.json` regeneration — done; both mirrors confirmed at `1.38.3`, matching `api-contract.md`

All Tier 1 required gates (`contract-validate`, `contract-validate-subset`,
`openapi-sync`, `backend-unit-and-integration`, `frontend-unit`,
`frontend-css-governance`) are expected green on the PR — existing workflows
fully cover the surface; `frontend-type-check` remains **informational-risk
only**.
