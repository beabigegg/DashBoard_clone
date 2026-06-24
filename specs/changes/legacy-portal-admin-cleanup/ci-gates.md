# CI/CD Gate Review

change-id: legacy-portal-admin-cleanup

## Required Gates for This Change

| gate | tier | required | trigger | command/workflow | artifact |
|---|---:|---:|---|---|---|
| unit-and-integration-tests | 1 | yes | pull_request | `backend-tests.yml` / `python -m pytest tests/ --ignore=tests/e2e --ignore=tests/stress` | pytest exit-0 |
| frontend-unit-tests | 1 | yes | pull_request | `frontend-tests.yml` / `npm test` (vitest) | vitest exit-0 |
| css:check | 1 | yes | pull_request | `frontend-tests.yml` / `npm run css:check` | css:check exit-0 |
| openapi-sync | 1 | yes | pull_request (paths: contracts/api/\*\*, contracts/openapi.json) | `openapi-sync.yml` / `cdd-kit openapi export --check` | sync exit-0 |
| e2e-critical | 1 | yes | pull_request | `contract-driven-gates.yml` job `e2e-critical` | exit-0 |
| released-pages-hardening | 1 | yes | pull_request | `released-pages-hardening-gates.yml` | exit-0 |
| nightly-integration | 3 | informational | schedule (02:00 UTC) | `backend-tests.yml` jobs `nightly-integration-real`, `oracle-fault-injection`, `multi-worker-concurrency` | nightly run log |

**Gate rationale.**
- `unit-and-integration-tests`: exercises the deleted `portal.html` render tests (now absent — collection count must remain non-zero), the new `portal_index`-always-SPA assertions, and the `portal_index` route-name pin in `test_app_factory.py` (AC-1, AC-2, AC-6, AC-7). Backend path filter in `backend-tests.yml` covers `src/mes_dashboard/app.py`, `src/mes_dashboard/templates/`, and `tests/`.
- `frontend-unit-tests`: exercises the new vitest a11y assertions for `aria-pressed` on the status toggle and `role="alert"` on the load-error panel in `frontend/src/admin-pages/` (AC-4). Frontend path filter covers `frontend/src/`.
- `css:check`: Rule 6 scoping enforcement. Removing orphaned drawer-era rules from `admin-pages/style.css` must leave the remaining rules correctly scoped under `.theme-admin-pages`; no new unscoped rule may be introduced (AC-3).
- `openapi-sync`: no API contract change is expected for this cleanup; gate must remain green to confirm no accidental drift. Trigger is path-scoped so it skips PRs that do not touch `contracts/api/` or `contracts/openapi.json`.
- `e2e-critical` / `released-pages-hardening`: default SPA path is unchanged; these gates confirm no regression to live pages.
- `nightly-integration` (Tier 3): real-subprocess / real-Redis / Oracle-XE jobs that cannot run in the PR sandbox. No new nightly gate is added; existing schedule is sufficient.

**Gates not applicable to this change.**
- `data-boundary`, `resilience`, `fuzz/monkey`, `stress`, `soak`: no new async path, no Oracle query, no chunking, no concurrency surface. Explicitly out of scope per change-classification.md §Tasks Not Applicable.
- `visual`: a11y attrs are non-visual DOM semantics; no pixel change (change-classification.md §Optional Artifacts).

## Workflow section

No new workflow files are added or modified. This change rides the existing gates in full:

| workflow file | job name | change to this file? |
|---|---|---|
| `.github/workflows/backend-tests.yml` | `unit-and-integration-tests` | none |
| `.github/workflows/frontend-tests.yml` | `frontend-unit-tests` | none |
| `.github/workflows/openapi-sync.yml` | `openapi-sync` | none |
| `.github/workflows/contract-driven-gates.yml` | `e2e-critical` | none |
| `.github/workflows/released-pages-hardening-gates.yml` | (existing jobs) | none |

The `backend-tests.yml` `pull_request` path filter already includes `src/mes_dashboard/app.py` (via `src/mes_dashboard/routes/**` is not the right subtree, but `src/mes_dashboard/core/**` covers `core/`; `app.py` is at the root of `src/mes_dashboard/` — covered by the `push: branches: [main]` trigger and the explicit `src/mes_dashboard/services/**` + `tests/**` filters. The deleted `templates/portal.html` is not under a filtered path, so PR trigger fires on `tests/**` changes which are present). The `frontend-tests.yml` `pull_request` path filter covers `frontend/src/**` which includes `frontend/src/admin-pages/`.

Note: `openapi-sync.yml` is path-scoped to `contracts/api/api-contract.md` and `contracts/openapi.json`. Because this PR does not touch those paths, the `openapi-sync` job will not be triggered on the PR itself. The gate is listed as required to confirm intent: if any accidental contract file appears in the diff, it must stay green.

## Promotion policy

Standard Tier-3 promotion policy applies:

1. All Tier-1 gates (`unit-and-integration-tests`, `frontend-unit-tests`, `css:check`, `e2e-critical`, `released-pages-hardening`) must be green on the PR before merge.
2. `openapi-sync` must be green if triggered (i.e., if `contracts/api/` or `contracts/openapi.json` appear in the diff — expected: they do not).
3. Per CLAUDE.md CDD patterns: tasks 6.2 and 6.3 are `done` when Tier-1 gates pass locally; task 6.4 is `skipped` (no new nightly or weekly gate defined for this change).
4. No gate promotion is required. Existing gates cover all surfaces; no new gate moves between tiers.

## Rollback policy

Pure code revert. No data migration, no queue change, no cache key change, no env-contract change.

Rollback procedure:

1. `git revert <merge-commit-sha>` — restores `templates/portal.html`, the `portal_index` else-branch, and the deleted render tests as an atomic unit (template and its only caller must never diverge).
2. Re-run `unit-and-integration-tests` to confirm the reverted render tests pass.
3. Re-run `css:check` to confirm the restored CSS rules pass Rule 6.
4. No env-var change is required: `PORTAL_SPA_ENABLED` is untouched throughout, so the flag's default (`True`) and its non-portal consumers (`modernization_policy.should_apply_canonical_redirect()`, status payload `portal_spa_enabled` key) are unaffected in both forward and rollback directions.
5. No `contracts/env/env-contract.md`, `env.schema.json`, or `.env.example` edits are needed in either direction.

## Merge Eligibility

mergeable when: `unit-and-integration-tests` green + `frontend-unit-tests` green + `css:check` green + `e2e-critical` green + `released-pages-hardening` green. `nightly-integration` is informational only and does not block merge.
