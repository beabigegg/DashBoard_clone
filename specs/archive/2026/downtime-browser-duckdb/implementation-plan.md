---
change-id: downtime-browser-duckdb
schema-version: 0.1.0
last-changed: 2026-06-12
---

# Implementation Plan: downtime-browser-duckdb

## Objective
Relocate the downtime-analysis compute path from server-side pandas to browser-side DuckDB-WASM. The server stops running `_merge_cross_shift_events`, `_bridge_jobid`, and `_enrich_events_df` on the request path; it writes two raw spool parquets (`downtime_analysis_base_events`, `downtime_analysis_job_bridge`) as one whole-dataset BQE chunk and returns `{base_spool_url, jobs_spool_url, query_id, taxonomy}`. The browser downloads both parquets once and runs the cross-shift merge, job-overlap bridge, category mapping, and all five view aggregations as local SQL, making filter changes zero-round-trip. This eliminates the gunicorn worker OOM and removes the 90-day Oracle band-aid (`_MAX_ORACLE_DAYS`). The whole change is gated by the `DOWNTIME_BROWSER_DUCKDB` feature flag; flag-off preserves the prior server-side path as the rollback target. Behavior parity with the prior server output (current-behavior.md) on the 184k-row reference fixture is the release blocker.

## Execution Scope

### In Scope
- `/query` route response cutover to `{base_spool_url, jobs_spool_url, query_id, taxonomy}` (design.md API Response Contract).
- Raw-parquet spool writer in `downtime_analysis_service.py` (no pandas reduction on request path); two raw namespaces with `SCHEMA_VERSION` cache-key participation (design.md D4, D7).
- Server-authoritative taxonomy JSON builder from `_map_big_category` (design.md D5; AC-4).
- Removal of `_MAX_ORACLE_DAYS` and its check in `_validate_dates` (AC-6); 730-day SYS-04 cap retained.
- `DOWNTIME_BROWSER_DUCKDB` feature flag governing the two code paths (design.md Migration/Rollback).
- New browser composable `frontend/src/downtime-analysis/useDowntimeDuckDB.ts`: cross-shift merge SQL, job-overlap bridge SQL, five view aggregations, taxonomy-driven BigCategory, browser-blob CSV export (design.md D2, D3).
- Six contract updates + 5 CHANGELOG entries (contract-reviewer.yml).
- E2E, data-boundary, resilience, stress, soak tests per test-plan.md.

### Out of Scope
- `/view`, `/equipment-detail`, `/event-detail` route behavior — deprecated-in-place (design.md D1); existing route tests stay as-is until api 1.17.0 removal.
- `downtime_analysis_duckdb_cache.py` (3-month prewarm cache) — unchanged, confirm only (design.md D6).
- Server-side `export_*_csv` streamers — kept as deprecated flag-off fallback; no new tests.
- Resource-history DuckDB composable — read as pattern reference only; no new tests.
- CSS / portal-shell theming — no change; css:check gate unchanged.
- The 730-day SYS-04/VAL-03 hard cap in `_validate_dates` — stays; only `_MAX_ORACLE_DAYS` removed.

## Non-Goals (do not produce / do not touch)
- Do NOT write `monkey-test-report.md`, `visual-review-report.md`, `spec.md`, or `proposal.md` (change-classification.md Optional Artifacts = no).
- Do NOT change CSS tokens or components; the four views must render pixel-unchanged.
- Do NOT modify the prewarm cache logic, the enriched `downtime_analysis_events` namespace (retain for fallback), or the deprecated endpoints' behavior.
- Do NOT opportunistically refactor `downtime_analysis_service.py` reductions — they are retained verbatim as the Python parity reference and the flag-off fallback.
- Do NOT enable `USE_ROW_COUNT_CHUNKING` for this service (ADR-0003).

## Sequence (mandatory order)
| # | agent | why this order |
|---|---|---|
| 1 | backend-engineer | Contracts (api/data/business/env/ci/CHANGELOG) and the new `/query` response must exist before any other agent consumes them. TDD: write failing route/service tests first, then implement raw-spool writer, taxonomy builder, flag guard, `_MAX_ORACLE_DAYS` removal. Frontend cannot start until `{base_spool_url, jobs_spool_url, query_id, taxonomy}` is confirmed working. |
| 2 | frontend-engineer | Needs the final API contract + live response from step 1. TDD: failing composable parity tests first, then implement merge/bridge SQL, five views, taxonomy join, browser-blob CSV, wire to new response keys. Must NOT start until backend confirms the response shape. |
| 3 | e2e-resilience-engineer | Needs both implementation paths complete. Writes/updates `frontend/tests/playwright/downtime-analysis.spec.ts` (full browser flow, zero-round-trip, error banners, >90-day acceptance, CSV blob) + data-boundary (malformed parquet, CHAR trailing-space, cross-midnight merge). |
| 4 | stress-soak-engineer | Needs the full stack to load-test. Writes `tests/stress/test_downtime_analysis_stress.py` (concurrent wide-range queries under 6 GB/no-swap, OOM-elimination, memory stability). |
| 5 | ui-ux-reviewer | Read-only; after frontend complete. Confirm four views render unchanged. Route evidence to agent-log, NOT visual-review-report. |
| 6 | visual-reviewer | Read-only; after ui-ux-reviewer. Pixel-level view parity. Route to agent-log. |
| 7 | qa-reviewer | Read-only, always last. Parity sign-off, OOM-elimination verification. Writes `qa-report.md` and `regression-report.md`. |

## Required Changes
| id | area | required action | owner agent |
|---|---|---|---|
| IP-1 | contracts | Update api (1.15.0), api-inventory (1.2.0), data-shape (1.13.0), business-rules (1.17.0), env (1.0.7), ci-gate (1.3.20) + 5 CHANGELOG entries | backend-engineer |
| IP-2 | route | `/query` returns `{base_spool_url, jobs_spool_url, query_id, taxonomy}`; remove `_MAX_ORACLE_DAYS` + its `_validate_dates` check; keep 730d cap; flag-guard legacy shape | backend-engineer |
| IP-3 | service | New raw-parquet spool writer (two namespaces, one whole-dataset BQE chunk); reductions NOT called on request path; retain reductions for flag-off fallback | backend-engineer |
| IP-4 | service | Taxonomy JSON builder from `_map_big_category` (`{map, prefixes, egt_category, fallback}`) | backend-engineer |
| IP-5 | events cache | Add `downtime_analysis_base_events` + `downtime_analysis_job_bridge` namespaces + `SCHEMA_VERSION` constant folded into raw-spool query_id; retain enriched namespace | backend-engineer |
| IP-6 | feature flag | `DOWNTIME_BROWSER_DUCKDB` env flag + module-level `_BROWSER_DUCKDB_ENABLED` constant governing both paths | backend-engineer |
| IP-7 | frontend composable | New `useDowntimeDuckDB.ts`: cross-shift merge SQL, job-overlap bridge SQL, five view aggregations, taxonomy-driven BigCategory, browser-blob CSV, error-banner gating (never silent empty) | frontend-engineer |
| IP-8 | frontend wiring | Wire feature views to new response keys; two-parquet atomicity loud-fail; add `src/downtime-analysis/**/*` to tsconfig include | frontend-engineer |
| IP-9 | e2e/data-boundary | Migrate `downtime-analysis.spec.js` → `.spec.ts`; add browser-flow, zero-round-trip, error-banner, >90d, CSV, data-boundary specs | e2e-resilience-engineer |
| IP-10 | stress/soak | `tests/stress/test_downtime_analysis_stress.py` + soak workload (OOM elimination, memory stability) | stress-soak-engineer |
| IP-11 | CI workflow | Add `npx playwright install --with-deps chromium` step + concurrency + retention in `frontend-tests.yml` | backend-engineer (with ci-gate update) |
| IP-12 | review + sign-off | View-parity confirmation; parity + OOM sign-off; qa-report.md + regression-report.md | ui-ux-reviewer, visual-reviewer, qa-reviewer |

## Source Artifact Pointers
| source | relevant pointer | used for |
|---|---|---|
| test-plan.md | AC→Test Mapping table; §Existing Tests to Extend; §Parity Fixture Note; §Notes | tests to write/run, patch targets, fixture discipline |
| ci-gates.md | Required Gates table; §CI/CD Workflow; §Promotion; §Rollback; §Merge Eligibility | verification commands, gate names, CI steps |
| design.md | API Response Contract; Parquet Schema; D1–D8; Migration/Rollback | response shape, raw-spool columns, key decisions |
| current-behavior.md | §`/query` (current), §OOM root cause, §90-day band-aid | regression/parity baseline |
| change-classification.md | §Inferred Acceptance Criteria AC-1..AC-8 | scope + acceptance |
| agent-log/contract-reviewer.yml | version-bumps; blocking-items (1)-(6) | exact contract version bumps + CHANGELOG entries + ordering |
| docs/adr/0003 | whole-dataset chunking exclusion | spool write = one whole-dataset chunk; browser loads full parquet before reductions |

## File-Level Plan
| path or glob | action | notes (owner) |
|---|---|---|
| `contracts/api/api-contract.md` | modify | `/query` response shape (1.15.0); deprecate 3 endpoints (backend-engineer) |
| `contracts/api/api-inventory.md` | modify | mark 3 endpoints deprecated, removal target api 1.17.0 (1.2.0) (backend-engineer) |
| `contracts/data/data-shape-contract.md` | modify | raw-parquet schemas §3.13 + taxonomy JSON + schema-versioning/cleanup (1.13.0) (backend-engineer) |
| `contracts/business/business-rules.md` | modify | DA-01..DA-04 locus→browser; 90d-removal; browser-ceiling; atomicity (1.17.0) (backend-engineer) |
| `contracts/env/env-contract.md` | modify | `DOWNTIME_BROWSER_DUCKDB` + default (1.0.7) (backend-engineer) |
| `contracts/ci/ci-gate-contract.md` | modify | new Playwright gate + OOM-risk caveat (1.3.20) (backend-engineer) |
| `contracts/CHANGELOG.md` | modify | 5 entries: api 1.15.0, data 1.13.0, business 1.17.0, env 1.0.7, ci 1.3.20 (backend-engineer) |
| `src/mes_dashboard/routes/downtime_analysis_routes.py` | modify | new `/query` response; remove `_MAX_ORACLE_DAYS` + check; flag-guard legacy; keep 730d cap (backend-engineer) |
| `src/mes_dashboard/services/downtime_analysis_service.py` | modify | raw-spool writer; taxonomy builder; `_BROWSER_DUCKDB_ENABLED`; reductions retained as fallback (backend-engineer) |
| `src/mes_dashboard/services/downtime_analysis_cache.py` | modify | two raw namespaces + `SCHEMA_VERSION`; enriched namespace retained (backend-engineer) |
| `src/mes_dashboard/sql/downtime_analysis/base_events.sql`, `job_bridge.sql` | modify (if needed) | reconcile ORDER BY per ADR-0003; columns match data-shape §3.13 (backend-engineer) |
| `.github/workflows/frontend-tests.yml` | modify | add `npx playwright install --with-deps chromium`; concurrency; retention (backend-engineer) |
| `tests/test_downtime_analysis_routes.py` | modify | `TestSummaryRoute`→`TestQueryRoute`; new shape + 90d; retain per-kwarg forwarding verbatim (backend-engineer) |
| `tests/test_downtime_analysis_service.py` | modify | `TestRawSpoolWriter`/`TestTaxonomyBuilder`/`TestMaxOracleDaysRemoved`/`TestTwoParquetAtomicity`/`TestPrewarmFeedRawWriter`; `_flag_on` variants (backend-engineer) |
| `tests/e2e/test_downtime_analysis_e2e.py` | modify | extend for new shape; preserve deprecated-endpoint regression tests (backend-engineer) |
| `frontend/src/downtime-analysis/useDowntimeDuckDB.ts` | create | merge/bridge SQL, 5 views, taxonomy join, browser-blob CSV, error-banner gating (frontend-engineer) |
| `frontend/src/downtime-analysis/` view/composable wiring | modify | wire to new response keys; two-parquet loud-fail; error banner (frontend-engineer) |
| `frontend/src/downtime-analysis/__tests__/useDowntimeDuckDB.test.ts` | create | 7 parity + taxonomy + CSV-blob tests (frontend-engineer) |
| `frontend/tsconfig.json` | modify | add `src/downtime-analysis/**/*` to include (frontend-engineer) |
| `frontend/tests/playwright/downtime-analysis.spec.js` → `.spec.ts` | modify/rename | browser flow, zero-round-trip, error banners, >90d, CSV blob (e2e-resilience-engineer) |
| `frontend/tests/playwright/data-boundary/`, `frontend/tests/playwright/resilience/` | create/modify | malformed parquet, CHAR trailing-space, cross-midnight, atomicity (e2e-resilience-engineer) |
| `tests/stress/test_downtime_analysis_stress.py` | create | concurrent wide-range, OOM-elimination, memory stability (stress-soak-engineer) |
| `tests/integration/test_soak_workload.py` | create/modify | repeated 90d+ queries; memory stable after 50 runs (stress-soak-engineer) |
| `tests/integration/test_downtime_parity_regression.py` | create | nightly Python-vs-DuckDB parity on 184k fixture (stress-soak-engineer) |
| `specs/changes/downtime-browser-duckdb/qa-report.md`, `regression-report.md` | create | parity sign-off, OOM-elimination evidence (qa-reviewer) |

## Contract Updates
Owner: backend-engineer. Complete BEFORE writing route/composable code (contract-reviewer.yml blocking-items 1-4). Write all version entries to `contracts/CHANGELOG.md` only — entries inside individual contract files are never scanned by `cdd-kit validate --versions` (CLAUDE.md). Decide `DOWNTIME_BROWSER_DUCKDB` initial default and pin it with a companion test before setting the code default (contract-reviewer.yml blocking-item 5; CLAUDE.md env-var-default discipline).

- API: `contracts/api/api-contract.md` 1.14.0→1.15.0 (`/query` returns `{base_spool_url, jobs_spool_url, query_id, taxonomy}`; removes summary/daily_trend/big_category/top_reasons from live path) + `contracts/api/api-inventory.md` 1.1.13→1.2.0 (deprecate `/view`,`/equipment-detail`,`/event-detail`; removal target api 1.17.0). CHANGELOG header `## [api 1.15.0]`.
- CSS/UI: no change (contract-reviewer.yml css-ui-confirmation; task 2.2 skipped).
- Env: `contracts/env/env-contract.md` 1.0.6→1.0.7 (`DOWNTIME_BROWSER_DUCKDB` flag + default). CHANGELOG header `## [env 1.0.7]`.
- Data shape: `contracts/data/data-shape-contract.md` 1.12.3→1.13.0 (raw-parquet schemas §3.13 per design.md Parquet Schema; taxonomy JSON shape; schema-versioning + post-deploy parquet-cleanup). CHANGELOG header `## [data 1.13.0]`.
- Business logic: `contracts/business/business-rules.md` 1.16.0→1.17.0 (DA-01..DA-04 locus→browser SQL; 90-day-limit removal; browser-memory-ceiling; two-parquet atomicity). CHANGELOG header `## [business 1.17.0]`.
- CI/CD: `contracts/ci/ci-gate-contract.md` 1.3.19→1.3.20 (new `downtime-playwright-e2e` gate; OOM-risk rollback caveat). CHANGELOG header `## [ci 1.3.20]`.

`cdd-kit validate` (contract-validate gate) expects exactly these 5 CHANGELOG entries (ci-gates.md §Merge Eligibility).

## Test Execution Plan
TDD red-first: write the failing test, then implement to green. Verification commands are the gate commands from ci-gates.md. Toggle the flag with `monkeypatch.setattr("mes_dashboard.services.downtime_analysis_service._BROWSER_DUCKDB_ENABLED", True/False)` — never `os.environ` (test-plan.md §Notes; CLAUDE.md). Patch `load_downtime_events` at `mes_dashboard.services.downtime_analysis_cache.load_downtime_events`.

| acceptance criterion | test file / command | expected signal |
|---|---|---|
| AC-1 | `tests/test_downtime_analysis_routes.py::TestQueryRoute` (4 keys non-null, legacy keys absent when flag on) + `TestQueryRouteContract`; cmd `pytest -m "not (e2e or integration_real or stress or load or soak or multi_worker)" --ignore=tests/integration --ignore=tests/stress --ignore=tests/e2e --ignore=tests/manual -x` | unit-mock-integration green |
| AC-2 | `tests/test_downtime_analysis_service.py::TestRawSpoolWriter` (raw base/job parquet, merge NOT called, SCHEMA_VERSION in key) + `TestPrewarmFeedRawWriter`; same cmd | unit-mock-integration green |
| AC-3 | `frontend/src/downtime-analysis/__tests__/useDowntimeDuckDB.test.ts` (7 parity tests vs 184k fixture); cmd `cd frontend && npm run test` | frontend-unit green |
| AC-4 | `tests/test_downtime_analysis_service.py::TestTaxonomyBuilder` + composable `test_taxonomy_driven_big_category_identical_to_prior_server_map`; unit + `npm run test` | both green |
| AC-5 | `frontend/tests/playwright/downtime-analysis.spec.ts::test_filter_change_issues_zero_api_round_trips`; cmd `cd frontend && npx playwright test tests/playwright/downtime-analysis.spec.ts` | zero new API round-trips on filter change |
| AC-6 | `TestQueryRoute::test_range_over_90_days_returns_200_not_400`; `TestMaxOracleDaysRemoved::test_max_oracle_days_constant_absent`; spec `test_180_day_range_accepted_end_to_end` | unit + playwright green |
| AC-7 | `TestTwoParquetAtomicity::test_base_hit_jobs_miss_raises_loudly`; specs `test_wasm_init_failure_shows_error_banner_not_empty_table`, `test_parquet_fetch_404_shows_error_banner`; `tests/stress/test_downtime_analysis_stress.py::test_concurrent_wide_range_queries_no_oom_kill` (`pytest tests/stress/... -m stress`) | loud error, no OOM kill |
| AC-8 | composable `test_csv_export_blob_equals_rendered_data`; spec `test_csv_export_download_triggers_browser_blob`; `npm run test` + playwright | CSV blob equals rendered data |

Parity-fixture discipline (test-plan.md §Parity Fixture Note): the 184k-row fixture at `tests/fixtures/downtime_184k_reference/` must include at least one cross-midnight event and one ambiguous job-bridge tie-break (≥80% runner-up). A uniform fixture cannot distinguish correct from silently-corrupt SQL — do not weaken it.

## Feature Flag — DOWNTIME_BROWSER_DUCKDB
- Env var `DOWNTIME_BROWSER_DUCKDB`; read into module-level constant `_BROWSER_DUCKDB_ENABLED` in `downtime_analysis_service.py`.
- Default: decided + documented in env-contract.md by backend-engineer before setting the code default (contract-reviewer.yml open-question). Design.md targets default-on after parity sign-off; default-off ships safely but needs operator cutover. Pin the default with a companion test.
- Flag ON: `/query` returns `{base_spool_url, jobs_spool_url, query_id, taxonomy}`; server writes raw parquets, runs NO reductions on the request path; browser computes all views.
- Flag OFF (rollback target, no redeploy): `/query` returns prior `{query_id, summary, daily_trend, big_category, top_reasons}`; server runs `apply_view` + enriched `downtime_analysis_events` spool + `export_*_csv` streamers exactly as today.
- Tests MUST toggle via `monkeypatch.setattr(...)` on the constant — not `os.environ` (module-level constants frozen at import).

## Handoff Constraints
- Implementation agents must not infer missing requirements from chat history.
- Do not re-copy full design, test strategy, CI policy, or contract prose into this plan; follow the source pointers above.
- If this plan omits a required file, behavior, contract, or test, stop and report `blocked`.
- Keep implementation within the file-level plan unless a Context Expansion Request is approved.
- backend-engineer must confirm the live `{base_spool_url, jobs_spool_url, query_id, taxonomy}` response works before frontend-engineer starts.

## Key Constraints (do not violate)
- **`load_downtime_events` patch site**: always patch at `mes_dashboard.services.downtime_analysis_cache.load_downtime_events` — the service uses function-body imports at four call sites; patching the service-module name silently has no effect (CLAUDE.md).
- **ADR-0003 chunking exclusion**: the raw-parquet spool write must use one whole-dataset BQE chunk (no `USE_ROW_COUNT_CHUNKING`). The browser must download the COMPLETE base_events parquet before running the cross-shift merge or job-overlap bridge — these require the full dataset and a chunk-seam split silently corrupts output (ADR-0003; design.md D8).
- **730-day cap stays**: only `_MAX_ORACLE_DAYS = 90` and its `_validate_dates` check are removed; the 730-day SYS-04/VAL-03 hard cap remains (AC-6).
- **Flag-off path must stay alive**: `DOWNTIME_BROWSER_DUCKDB=false` must restore the exact prior `{query_id, summary, daily_trend, big_category, top_reasons}` shape and server-rendered views without redeploy (ci-gates.md §Rollback; design.md Migration).
- **Server-authoritative taxonomy**: generated from `_map_big_category()` at query time, serialized to JSON in `/query`; never hard-coded in the frontend (design.md D5; AC-4).
- **Two-parquet atomicity**: server writes both parquets or neither; the browser raises a visible error if one is missing/expired — never silently drop job enrichment (design.md Open Risks; AC-7).
- **No silent empty table (Type-A)**: the composable distinguishes "zero rows" (valid empty) from load/compute failure (error banner offering a narrower range). No silent empty render (design.md D3; CLAUDE.md Type-A note).
- **Route per-kwarg assertions**: assert each forwarded request param via `mock.call_args.kwargs[key] == non_default_value`; never use `assert_called_once_with(...)` as a kwarg allowlist (CLAUDE.md). Retain existing per-kwarg forwarding tests verbatim.
- **CHANGELOG location**: all 5 version entries go in `contracts/CHANGELOG.md` only (CLAUDE.md).
- **New Playwright spec → CI browser install**: `frontend-tests.yml` must add `npx playwright install --with-deps chromium` before the new spec (CLAUDE.md; ci-gates.md). Do NOT run `playwright install` on the local shared-browser host.
- **Spool schema-break cleanup**: bumping `SCHEMA_VERSION` orphans old raw parquets by key; a schema-breaking rollback also needs `rm -f tmp/query_spool/downtime_analysis_base_events/*.parquet tmp/query_spool/downtime_analysis_job_bridge/*.parquet` (design.md D4; ci-gates.md §Rollback).
- **`ci-gates.md` literal headers**: keep `## CI/CD Workflow`, `## Promotion Policy`, `## Rollback Policy` (already present) — `cdd-kit gate` checks the literal strings.

## Known Risks
- **Parity correctness** (highest): browser DuckDB SQL must byte/row-match Python `_merge_cross_shift_events` tie-break and `_bridge_jobid` ≥80%-runner-up ambiguity rule. ADR-0003 flags silent corruption. Mitigation: parity matrix on the 184k fixture incl. cross-midnight + ambiguous-tie cases; `nightly-parity-regression` is required from day one.
- **Low-RAM clients** on the ~62 MB / 184k-row parquet: D3 ceiling must be tuned against `duckdb-activation-policy.ts`; needs a real low-RAM profile test (stress-soak-engineer).
- **Flag-off OOM caveat**: rolling back to the server path without reinstating `_MAX_ORACLE_DAYS` accepts gunicorn OOM risk on >90-day ranges under the 6 GB/no-swap profile — short rollback windows only (ci-gates.md §Rollback item 2).
- **Two-parquet expiry race**: a base hit with an expired jobs parquet must fail loudly (410-equivalent), not silently drop enrichment.
