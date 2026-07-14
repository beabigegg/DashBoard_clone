# Change Classification

## Change Types
- primary: `feature-enhancement` (生產達成率 report overhaul), `business-logic-change` (PACKAGE_LF/workcenter merge semantics, daily-plan denominator, cumulative aggregate-then-divide), `api-change` (10 new endpoints + breaking redefinition of `ProductionAchievementReportResponse`), `ui-redesign` (App.vue rewrite, chart replacement, new standalone settings page), `data-shape-change` (new Oracle `PACKAGE_LF` column, 3 new MySQL tables, spool parquet schema v1→v2)
- secondary: `migration` (additive MySQL DDL — 3 `CREATE TABLE IF NOT EXISTS`, manually applied), `bug-fix` (D6 N-shift-tail chunk-boundary under-count — bundled in-scope fix), `docs/ADR` (ADR-0016 extension addendum)

## Lane
- feature

(D6 — the N-shift-tail chunk-boundary fix — is an in-scope correctness fix with an already-identified root cause. It is owned by `backend-engineer` inside the normal feature lane, NOT routed through the bug-fix lane, but still requires a reproduction fixture + regression test proving the previously-missed seam.)

## Risk Level
- high

## Impact Radius
- cross-module

(Spans SQL → worker → service → routes → warm-cache → frontend rewrite → new route category within one feature, PLUS additive touches to shared subsystems consumed by other reports: `spool_warmup_scheduler.py` (6 other warmup jobs), `filter_cache.py`, `permissions.py`, and the spool/parquet plane. A breaking wire-protocol change and a parquet schema-version break add blast radius. Fail-safe degradation (warm-cache miss → 202 poll) and verbatim permission reuse keep it below `critical`.)

## Tier
- 0

Classified upward to Tier 0 (high + cross-module maps to the 0–1 band). Justification: (1) the approved plan Phase 0 explicitly directs "this repo's highest risk tier (full design.md/implementation-plan.md/test-plan.md capsule)"; (2) breaking `ProductionAchievementReportResponse` redefinition with no deprecation window; (3) `_PA_SPOOL_SCHEMA_VERSION` parquet break; (4) modification of a scheduler subsystem shared by 6 other warmup jobs; (5) widening a shared permission's authorization scope; (6) a production-Oracle data-completeness fix (D6) that alters historical N-shift numbers.

## Architecture Review Required
- yes
- reason: New data model (3 MySQL tables with deliberately opposite default semantics — D1 sparse fallback-to-self vs D2 explicit-inclusion), new caching-subsystem integration into a shared hourly scheduler (with a non-obvious Redis-orphan-key trap requiring a `progress_report()` no-op subclass), a new standalone route category (7-file registration), a breaking wire-protocol change, a 2-stage DuckDB-WASM rollup pipeline, a data-flow/chunk-boundary correctness fix (D6), and an ADR-0016 extension. These are exactly the module-boundary / data-flow / compatibility-trade-off / migration-rollback decisions that require `spec-architect` to write `design.md` before `implementation-planner` runs.

## Required Artifacts
Always required: change-request.md, change-classification.md, implementation-plan.md, test-plan.md, ci-gates.md, tasks.yml, context-manifest.md

## Optional Artifacts (default: no — set yes only with explicit reason)
| artifact | create? | reason |
|---|---|---|
| current-behavior.md | no | Current behavior + D6 baseline are already documented exhaustively in the approved plan and captured as the current→target delta in design.md; avoid a duplicate source of truth. |
| proposal.md | no | Product investigation is complete and approved in plan mode; no open user-facing decision remains. |
| spec.md | no | Requirements fully specified in change-request.md + the approved plan; design.md + implementation-plan.md carry the detail. |
| design.md | yes | Forced by Architecture Review Required: yes — new data model, shared-subsystem integration, breaking wire protocol, ADR-0016 extension, D1/D2 opposite defaults, D6 chunk-seam. |
| qa-report.md | yes | Tier 0 release readiness with durable sign-off: breaking API change, manual-DDL rollout precondition, and an approved-with-risk item (warm-cache staleness SLA + settings→report propagation latency). |
| regression-report.md | yes | Durable evidence that shared surfaces are unaffected: warmup scheduler (esp. test_production_history_not_in_warmup_jobs), filter_cache, permission scope, and that D6 changes historical N-shift counts intentionally and only at the intended seam. |
| visual-review-report.md | yes | Visual evidence bundle for a full App.vue rewrite + new PlanAchievementStackedChart with non-trivial semantics (>100% over-plan segments, y=100 計畫 markLine) + brand-new settings page. |
| monkey-test-report.md | no | Covered by the rewritten production-achievement-monkey.spec.ts + an agent-log pointer; promote to yes only if blocking findings surface. |
| stress-soak-report.md | no | Warm-cache is low-frequency (hourly) and fail-safe; captured via extended stress tests + agent-log. Promote to yes only if warmup-scheduler load or chunk-boundary results are concerning. |

## Required Contracts
- API: yes — contracts/api/api-contract.md (schema-version bump; 10 new endpoint rows: GET/PUT/DELETE /package-lf-map[/<raw>], GET/PUT/DELETE /workcenter-merge-map[/<raw>], GET/PUT /daily-plans, GET /known-package-lf-values, GET /known-workcenter-groups (added post-review per interaction-design.md OD-8); breaking in-place redefinition of ProductionAchievementReportResponse with Compatibility Notes, no deprecation window); contracts/api/api-inventory.md; regenerate contracts/api/openapi.json + contracts/openapi.json via `cdd-kit openapi export` (both paths).
- CSS/UI: yes — contracts/css/css-inventory.md (new .theme-production-achievement-settings scope row); contracts/css/css-contract.md (chart replacement classes, scoped-theme rule 4/6 compliance); `npm run css:check`.
- Env: no — plan introduces no new env vars; reuses existing WARMUP_INTERVAL_SECONDS / WARMUP_SCHEDULER_ENABLED / QUERY_SPOOL_TTL_SECONDS / PRODUCTION_ACHIEVEMENT_USE_UNIFIED_JOB.
- Data shape: yes — contracts/data/data-shape-contract.md: §3.28.1 (+PACKAGE_LF column, updated row-grain), §3.28.4 (envelope grows 2→5 inline arrays), new §3.30/§3.31/§3.32 (3 MySQL tables, each stating D1-vs-D2 default-on-absence), new §3.33/§3.34 (inline map shapes); document _PA_SPOOL_SCHEMA_VERSION v2.
- Business logic: yes — contracts/business/business-rules.md: PA-06 rollup-locus note extended to the 2-stage pipeline; new PA rules for D1 sparse mapping, D2 explicit-inclusion (flag opposite defaults), daily-plan semantics, new achievement-rate denominator, month/range cumulative aggregate-then-divide + 1st-of-month edge case, warm-cache freshness SLA (~1hr, degrade-to-202), and the D6 closing-chunk fix.
- CI/CD: no — no contracts/ci/ci-gate-contract.md change. No new RQ worker service, so the "New RQ Worker Deploy Checklist" gate is NOT triggered.

Also required (architecture doc, not a contract per se): docs/adr/0016-production-achievement-async-spool-seam-reduction.md — extension addendum (do NOT mark superseded).

## Required Tests
- unit: yes — 3 new MySQL service test files; filter_cache package_lf_values extension; worker post_aggregate/pre_query; resolveMonthPeriod() boundary; computeDailyView/computeCumulativeView; chart props→ECharts-option; App 4-mode wiring; 3 settings panels.
- contract: yes — per-endpoint route-forwarding + 403-when-not-whitelisted for all 10 new endpoints; widened /report response-shape assertions; new test_production_achievement_contract.py; contract-sample regeneration; pin test _PA_SPOOL_SCHEMA_VERSION == 2.
- integration: yes — extend mysql_roundtrip + resilience tests for all 3 tables; filter_cache reuse test; new test_production_achievement_daily_cache.py; _WARMUP_JOBS registry assertions (+2 entries; test_production_history_not_in_warmup_jobs still passes); rq_async tests.
- E2E: yes — ground-up rewrite of the 5 existing page specs; new /production-achievement-settings spec (whitelisted-edit vs non-whitelisted-read-only); route-registration parity check across the 6 registry files.
- visual: yes — PlanAchievementStackedChart (>100% over-plan segments render, markLine present, real-percentage not normalize-to-100), 4-mode UI, settings page.
- data-boundary: yes — D1 fallback-to-self, NULL/blank→sentinel, D2 exclude-by-absence, empty-result 5-column schema fallback, D6 closing-chunk (correct inclusion + zero leakage), dual-tier parity with multiple PACKAGE_LF per SPECNAME/day.
- resilience: yes — MySQL read-degrade / write-MySQLUnavailableError, warm-cache miss → seamless 202 poll, flag-off no-ops without importing worker/hitting Oracle, progress_report() override never calls update_job_progress.
- fuzz/monkey: yes — rewrite production-achievement-monkey.spec.ts for the 4-mode UI + settings-page CRUD interaction surface.
- stress: yes — extend production_achievement stress test; new chunk_boundary stress test; warmup-scheduler load with 2 added hourly jobs.
- soak: consider — hourly warm-cache is fail-safe/low-frequency; a light soak is optional, not blocking.

## Required Agents
- spec-architect — writes design.md
- implementation-planner — writes implementation-plan.md + tasks.yml execution packet
- backend-engineer — SQL/worker/service/3 new MySQL services/filter_cache/warm-cache module/scheduler wiring/routes/DDL/permissions docstring; owns D6
- frontend-engineer — DuckDB-WASM rollup, composable 4-mode state, App.vue rewrite, chart replacement, new settings mini-app, 7-file route registration
- test-strategist — test-plan.md
- contract-reviewer — api/css/data/business contract diffs + ADR-0016 extension
- ui-ux-reviewer — 4-mode tab interaction/copy/accessibility, settings-page flows
- visual-reviewer — chart replacement + full page rewrite + settings-page visual evidence
- e2e-resilience-engineer — warm-cache miss degrade, MySQL degrade paths, Playwright resilience/async specs
- stress-soak-engineer — warmup-scheduler + chunk-boundary stress
- qa-reviewer — release readiness / qa-report.md
- ci-cd-gatekeeper — openapi export, css:check, type-check, full pytest, contract-sample regeneration, gate readiness

(bug-fix-engineer intentionally NOT included — D6 stays in the feature lane under backend-engineer.)

## Inferred Acceptance Criteria
- AC-1: Oracle SQL adds weh.PACKAGE_LF to SELECT + GROUP BY (4-dim group key output_date/shift_code/SPECNAME/PACKAGE_LF); worker post_aggregate() re-aggregation and empty-result schema fallback both carry PACKAGE_LF as a nullable 5th column; _PA_SPOOL_SCHEMA_VERSION bumps 1→2; dual-tier parity test passes with multiple PACKAGE_LF values per SPECNAME/day.
- AC-2: production_achievement_package_lf_map is sparse/exceptions-only with fallback-to-self (D1): a raw value absent from the table groups to itself; NULL/blank raw → sentinel "(未分類)"; seeded with only the ~9 rows behind the 4 confirmed merges, not all 37 observed values.
- AC-3: production_achievement_workcenter_merge_map is explicit-inclusion / exclude-by-absence (D2): exactly the 12 seeded groups appear; every other raw WORK_CENTER_GROUP is excluded with no row. D1 and D2 opposite defaults are documented in code comments + business-rules.md.
- AC-4: production_achievement_daily_plans is keyed (workcenter_group[merged], package_lf_group[merged]) with no shift dimension, coexists with and does not affect the existing shift-based production_achievement_targets; daily 產出 = D班+N班, daily 達成率 = daily 產出 / daily 計畫.
- AC-5: Permission reuse — can_edit_targets()/targets_edit_required gate all new CRUD verbatim; every new PUT/DELETE returns 403 when not whitelisted; no new permission system or "am-I-whitelisted" endpoint is introduced.
- AC-6: Ten new endpoints (distinct method+path rows: GET/PUT/DELETE ×2 resources + GET/PUT ×1 + GET ×2 — reconciled from the plan's "7" during contract review, then +1 again for OD-8's known-workcenter-groups) exist and forward per-kwarg correctly (GET/PUT/DELETE /package-lf-map[/<raw>], GET/PUT/DELETE /workcenter-merge-map[/<raw>], GET/PUT /daily-plans, GET /known-package-lf-values, GET /known-workcenter-groups); /report's spool-hit branch ships 5 inline maps; ProductionAchievementReportResponse is redefined in place (breaking, atomic, no deprecation window) and `cdd-kit openapi export` is re-run for both output paths.
- AC-7: Warm-cache — 當日/前日 served from the existing hourly spool_warmup_scheduler.py (+2 warmup jobs) reusing ProductionAchievementJob via a subclass whose progress_report() is a no-op; on cache miss /report degrades seamlessly to the existing 202-enqueue-and-poll path; with PRODUCTION_ACHIEVEMENT_USE_UNIFIED_JOB off the module no-ops without importing the worker or hitting Oracle; test_production_history_not_in_warmup_jobs still passes.
- AC-8: Frontend presents 4 fixed modes 當日/前日/當月/自訂區間 (default landing 當日), one single-select workcenter_group filter from the merged 12-value list (default 焊接_DB); today/yesterday → computeDailyView; month/range → computeCumulativeView; resolveMonthPeriod returns the full previous month when the reference date is the 1st; range end is capped at min(end, today); both modes reuse the identical GET /report fetch/poll.
- AC-9: AchievementChart.vue is deleted and replaced by one shared PlanAchievementStackedChart.vue, rendering D%+N% as real stacked percentages (can exceed 100%; NOT normalize-to-100) with a markLine at y=100 labeled 計畫; colors come from resolveCssVar() CSS custom properties, not inline rgb() literals.
- AC-10: The cumulative trend chart aggregates across ALL PACKAGE_LF groups (D3) using aggregate-then-divide — SUM(actual)/SUM(plan) computed before dividing, never a mean of per-group percentages.
- AC-11: New standalone /production-achievement-settings page — no drawer/side-nav entry, reachable only via a 設定 button; registered across all 7 required locations; whitelisted users edit all 3 tables, non-whitelisted users are read-only via the fail-closed editForbidden pattern.
- AC-12: D6 fix — :chunk_end_excl widened to full datetime, and pre_query() appends exactly one closing chunk [end_date+1 00:00:00, end_date+1 07:30:00); the last day's N-shift tail is correctly attributed with zero leakage into the next day; a regression test demonstrates the previously-under-counted seam is now captured.
- AC-13: Contracts updated coherently — business-rules.md, api-contract.md, data-shape-contract.md, and the ADR-0016 extension addendum citing every new client-side join stage.

## Tasks Not Applicable
- not-applicable: 2.3 (Env contract — no new env vars, existing ones reused), 2.6 (CI/CD contract — no ci-gate-contract.md change), 4.3 (Env/deploy — no new env vars, no new deploy/*.service file, existing warmup RQ worker already runs generically), 4.4 (CI/CD workflows — no new GitHub Actions workflow files; gate/export/test running is covered under ci-gates.md task 1.4 and Verification section 6)

## Clarifications or Assumptions
1. Atomic-split vs monolithic: NOT emitted despite task-heaviness, because (a) this is one cohesive, tightly-coupled feature, not 2+ unrelated change-types, and (b) the user explicitly and in-writing chose monolithic (change-request.md + the approved plan). Proceeding as one Tier 0 change.
2. Tier 0 vs Tier 1: classified upward to Tier 0 per the plan's explicit "highest risk tier" instruction plus breaking-response-shape / parquet-schema-break / shared-subsystem factors.
3. D6 lane: kept inside the feature lane under backend-engineer (root cause already identified in the approved plan), not routed through bug-fix-engineer. Still requires a reproduction fixture + regression test.
4. Env: no .env.example / env-contract.md change — warm-cache reuses existing global env vars.
5. No new RQ worker service / deploy/*.service change — the generic warmup queue worker already runs.
6. Rollout gate: the 3 MySQL tables must be created (scripts/sql/production_achievement_tables.sql, manually applied) BEFORE the backend deploy that reads/writes them; _PA_SPOOL_SCHEMA_VERSION v2 self-heals via key mismatch, with an optional parquet-purge fast-forward documented in ci-gates.md rollback section.
7. frontend/src/production-achievement-settings/ is a NEW directory not yet present in the project-map; granted in Allowed Paths prospectively for creation.
8. change-request.md's Business/User Goal, Non-goals, Constraints, Known Context, Open Questions, and Delivery Date sections are empty; the approved plan (/home/egg/.claude/plans/calm-plotting-diffie.md) is the authoritative scope source. spec-architect/implementation-planner should backfill Non-goals (e.g. "month-mode warm-caching is explicitly out of scope") into design.md.

## Context Manifest Draft
See specs/changes/production-achievement-overhaul/context-manifest.md (copied verbatim from this classification).
