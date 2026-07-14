## Change Summary

Full rewrite of the 生產達成率 (Production Achievement Rate) report: PACKAGE_LF
became a first-class grouping dimension with admin-configurable merge rules
(sparse exception-mapping, fallback-to-self), workcenter_group gained an
analogous but deliberately opposite merge step (explicit-inclusion,
absence-excludes), and a new "daily plan" concept (workcenter_group ×
package_lf_group → qty, no shift dimension) shipped additive to the existing
shift-based targets table. The page itself moved from a free-form date-range
query to four fixed views (當日/前日/當月/自訂區間), with 當日/前日 backed by an
hourly warm-cache reusing the existing async job pipeline. A long-standing
N-shift undercount at the tail of any multi-day query range (D6) was fixed in
the same change. Shipped as one large Tier-0 CDD change per the user's explicit
choice to avoid splitting into a sequence of smaller changes.

## Final Behavior

- Report rows are now grouped by merged PACKAGE_LF group (in addition to the
  existing shift/workcenter_group/SPECNAME dimensions); an unmapped raw
  PACKAGE_LF value renders as its own group (fallback-to-self), never dropped.
- Workcenter groups absent from `production_achievement_workcenter_merge_map`
  are excluded from the report entirely (opposite default from PACKAGE_LF,
  deliberately — flagged repeatedly in code/contracts as easy to invert by
  copy-paste).
- New daily-plan concept, editable via the new settings mini-app, coexists
  with (never replaces) the pre-existing shift-based targets table.
- 4-mode UI (當日/前日/當月/自訂區間) replaces the old date-range picker; 當日/前日
  read from an hourly warm-cache, falling through unchanged to the existing
  202-poll path on a cache miss.
- New standalone `/production-achievement-settings` mini-app (no drawer nav
  entry) for editing the 3 new MySQL tables, gated by the pre-existing
  `can_edit_targets()` permission flag.
- Month-mode cumulative trend aggregates SUM(actual)/SUM(plan) across all
  PACKAGE_LF groups before dividing — never a mean of each group's own rate.
- D6: the final day of any multi-day query range now correctly includes its
  full N-shift tail via one extra closing chunk in `pre_query()`.
- `AchievementChart.vue` deleted (hard cutover, no feature flag); replaced by
  `PlanAchievementStackedChart.vue` (real, uncapped >100% stacking + a y=100
  target markLine), shared by both DailyView and CumulativeView's trend chart.

## Final Contracts Updated

- `contracts/business/business-rules.md` 1.46.0 → 1.47.0 (PA-09..PA-15: D1/D2
  opposite-default mapping, D3 aggregate-then-divide, D6 fix, warm-cache SLA)
- `contracts/api/api-contract.md` 1.40.0 → 1.41.0 (10 new/redefined endpoints;
  5 response schemas corrected to the site-wide `{success,data,meta}` envelope
  after backend-engineer/frontend-engineer found the un-enveloped originals
  were a pre-existing contract-authoring defect, not a code bug)
- `contracts/data/data-shape-contract.md` 1.39.0 → 1.40.0 (§3.28.1 extended
  +PACKAGE_LF; new §3.30-§3.34 for the 3 new tables + inline map shapes)
- `contracts/css/css-contract.md` + `css-inventory.md` (new
  `.theme-production-achievement-settings` scope)
- `docs/adr/0016-production-achievement-async-spool-seam-reduction.md`
  Extension addendum (2-stage client-side rollup; D6 is fetch-completeness,
  not a rollup-locus change — ADR not superseded)

## Final Tests Added / Updated

- ~380 backend unit/contract/integration tests across 3 new service test
  files, extended route/worker/service tests, and a rewritten dual-tier
  parity test (`tests/test_frontend_production_achievement_parity.py`)
- 3 new property-based tests for the D3 aggregate-then-divide invariant
  (`tests/property/test_production_achievement_aggregate_invariant.py`) —
  exact closed-form Fraction arithmetic, not probabilistic
- 123 frontend vitest tests across composables/components/settings panels
- 49 Playwright tests across 6 spec files (critical-journey, async, monkey,
  resilience, data-boundary, settings) — see Production Reality Findings for
  why this suite's own mechanics were never validated until real CI ran it
- 10 new stress tests (warmup-scheduler 8-job fairness; D6 chunk-boundary
  correctness at 30/90/180-day scale)
- 1 human-authored acceptance case (`package-lf-fallback-to-self`, ADR 0010)
  with an agent-built driver exercising the real DuckDB SQL expression

## Final CI/CD Gates

- `production-achievement-monkey` and `production-achievement-settings-e2e`:
  brand-new Tier-1 required gates.
- `playwright-critical-journeys` / `playwright-resilience` /
  `playwright-data-boundary`: these gate *names* pre-existed in
  `contracts/ci/ci-gate-contract.md`'s Gate Inventory, but no workflow step in
  this repo had ever actually executed the corresponding spec files before
  this change — ci-cd-gatekeeper closed the wiring gap for this change's own
  spec files only (not the whole `resilience/`/`data-boundary/` directories;
  broader repo-wide gap left explicitly out of scope).
- `.cdd/boundary-manifest.yml` bootstrapped repo-wide (212 operations,
  fail-closed scaffold) as a side effect of getting this change's own 10 new
  endpoints past a previously-unbootstrapped Boundary Guard gate.

## Production Reality Findings

1. **qa-reviewer caught 3 real coverage gaps other agents' own self-reports
   missed**: a property test that test-strategist's agent-log claimed was
   planned but was never actually created (confirmed via `git log --all`); a
   dual-tier parity test file left stale, still verifying SQL this change's
   frontend-engineer had already deleted; `regression-report.md`, required
   "yes" per the classifier, never produced. All 3 closed via a backend-
   engineer fix-back cycle plus main Claude writing the regression report
   directly from re-verified live evidence.

2. **e2e-resilience-engineer found a real, build-breaking bug** (4 missing
   Tailwind color tokens) that made `npm run build` fail for the *entire*
   frontend, not just this feature — invisible to vitest/tsc/css:check since
   none of those exercise Tailwind's actual `theme()` resolution the way a
   real `vite build` PostCSS pass does.

3. **No agent in this session could ever execute the Playwright specs against
   a live browser** (this sandbox's Chromium is a version behind what this
   project's pinned `@playwright/test` expects, and installing a matching one
   is out of scope per `docs/architecture/ci-workflow.md` — CI-runner-only).
   Every agent, including e2e-resilience-engineer, monkey-test-engineer, and
   visual-reviewer, verified their Playwright work via `--list` (parse-only)
   and source-reading only. This made an entire class of bug — "does the
   no-server skip guard actually skip fast" — structurally undetectable until
   the very first real CI run.

4. **That first real CI run (main Claude, after merging to main) surfaced 3
   more real, only-findable-with-a-live-browser bugs**, fixed over 3 follow-up
   commits:
   - All 5 new/rewritten Playwright spec files' no-server "pageRendered"
     guard called `page.goto(30s timeout)` directly followed by
     `page.waitForFunction(20s timeout)`, with no fast body-text pre-check.
     Since `frontend-tests.yml`'s job never starts a real dev server, every
     test paid a ~50-65s tax before giving up, blowing the 8-minute step
     timeout.
   - Shortening those timeout *values* alone (first fix attempt) did not
     help: `page.waitForFunction()` does not reliably honor its own `timeout`
     option when called on a frame whose navigation just failed — confirmed
     by direct comparison against 2 sibling files
     (`production-achievement-async.spec.ts`, the monkey spec's
     `gotoAndWaitForApp()`) that already gate `waitForFunction` behind a fast
     `bodyText.length < 50` pre-check and run in ~200-300ms/test. The fast
     check must run *before* `waitForFunction` is ever called, not just bound
     its timeout.
   - The regex-based bulk fix for the above introduced a duplicate-`const`
     SyntaxError in the one test (the OD-7 round-trip test in
     `production-achievement-settings.spec.ts`) that navigates to and guards
     the same `.theme-production-achievement` selector twice within one
     function — fixed by renaming every inserted variable to a globally
     unique name.

5. **`.cdd/boundary-manifest.yml` had never existed in this repo**, despite
   Boundary Guard's policy and CI step being wired in 2 days prior (the
   cdd-kit 3.13.1 sync). This change's own new endpoints were the first ones
   to ever trigger a real check against it. Root cause: the raw
   `cdd-kit boundary check` CLI step in CI (unlike `cdd-kit gate`'s own
   wrapping) has no `shadow_mode` awareness at all, so a project correctly
   configured for gradual rollout (`shadow_mode: true`) still gets
   immediately hard-blocked on day one of any API-contract-touching change.
   Fixed by scaffolding the manifest via `cdd-kit boundary init` and wrapping
   the CI step to respect `shadow_mode`. Filed upstream:
   github.com/beabigegg/contract-driven-delivery-kit issue #65.

6. Two further tool defects, unrelated to this change's own implementation but
   diagnosed while authoring this change's `interaction-design.md` citations
   and `acceptance.yml` driver, filed upstream: the ADR 0012 citation resolver
   rejects nullable-union `type: [object, null]` schema nodes (issue #66); the
   acceptance.yml hardcoded-expect scanner matches file-wide at a word
   boundary instead of per-case (issue #67).

## Lessons Promoted to Standards

Reviewed by contract-reviewer; all 3 candidates approved, evidence-checked
against this change's agent-logs and the actual current file states.

1. **Boundary Guard `shadow_mode` gap** (promote-to-guidance) — extended the
   existing `CLAUDE.md` bullet under "CDD Kit operations" (was: only the
   `CDD_BASE_SHA` gap; now also: no `shadow_mode` awareness, fixed this
   session) and rewrote `docs/cdd-kit-patterns.md`'s `## cdd-kit boundary
   check --base` section (updated the stale code sample to the actual wrapped
   step, replaced the "not fixed, deferred" paragraph with what was actually
   done + the upstream issue link). Evidence: Production Reality Finding #5
   above; `.github/workflows/contract-driven-gates.yml`'s "Boundary Guard (PR
   diff)" step; `.cdd/policy.yml:3` (`shadow_mode: true`, confirming the gap
   was live, not hypothetical).

2. **Playwright no-server skip must GATE `waitForFunction`, not just bound its
   timeout** (promote-to-guidance) — tightened the existing `CLAUDE.md`
   bullet under "CI workflow & GunicornHarness" (the prior wording was
   ambiguous enough to cause this exact mistake once this session) and
   appended a second-occurrence evidence line to
   `docs/architecture/ci-workflow.md`'s already-correct rule text (this same
   bug class first happened in `production-achievement-async-spool`, and
   recurred here across 5 different files despite the existing doc). Evidence:
   Production Reality Findings #3-4 above; `production-achievement-async.spec.ts`
   /`production-achievement-monkey.spec.ts`'s `gotoAndWaitForApp()` (the
   correct pattern, ~200-300ms/test) vs. the 5 broken files (~50-65s/test
   until fixed).

3. **Gate Inventory presence ≠ proof of wiring** (promote-to-contract, new) —
   added `## Gate Inventory Verification (Cross-Cutting Rule)` to
   `contracts/ci/ci-gate-contract.md` (schema-version 1.3.39→1.3.40), plus a
   `contracts/CHANGELOG.md [ci 1.3.40]` entry. Evidence:
   `agent-log/ci-cd-gatekeeper.yml` for this change, which found
   `playwright-critical-journeys`/`playwright-resilience`/
   `playwright-data-boundary` had been claimed-covered by at least 6 prior
   Gate Compatibility Notes across other changes, with no workflow step ever
   executing the referenced files until this change.

Not promoted: contract-reviewer separately flagged (as an observation, not a
candidate) that `contracts/ci/ci-gate-contract.md`'s Gate Inventory has no row
at all for Boundary Guard / `cdd-kit boundary check`, despite it being a real,
merge-blocking CI step — left for a future change to decide, not acted on here
(this change only worked around Boundary Guard, it didn't formalize its own
Gate Inventory entry).

## Follow-up Work

- monkey-test-engineer's 2 confirmed hardening findings, not fixed this
  change (low severity — idempotent upserts, no FK, no data corruption):
  `DailyPlanPanel.vue`'s new-row form doesn't re-validate its selection
  against a live-narrowed options list before submit; the settings
  composable's 5 write functions share one `editSaving` flag with no
  reentrancy guard (unlike `runQuery()`'s `if (loading.value) return`).
- ui-ux-reviewer's 3 cosmetic nits (dash-style mismatch, redundant
  empty-state text, stale prior-query results undimmed during a
  filter-triggered re-query) — all explicitly non-blocking.
- dependency-security-reviewer's advisory: the 3 new services don't
  pre-validate string length against VARCHAR(60)/(100) before the MySQL
  round-trip (mirrors the pre-existing targets service's own behavior, not a
  new regression); applying the DDL script after the code deploy (violating
  the stated precondition) would silently empty the whole report via D2's
  INNER JOIN.
- `business-rules.md` PA-07's citation may now be stale (references a browser
  dual-tier parity pattern pre-dating this change, from the already-archived
  `production-achievement-async-spool` change) — flagged non-blocking,
  worth revisiting in a future related change.
- Month-mode (當月) warm-cache is an explicit non-goal (unpredictable-cost
  range) — natural follow-up if month-mode latency later proves inadequate.
- Repo-wide gap, left out of scope: `playwright-resilience` and
  `playwright-data-boundary` gates are wired only for this change's own spec
  files, not the whole `resilience/`/`data-boundary/` directories — other
  declared-but-unwired gates may still exist elsewhere in the repo.
- `tests/test_runtime_hardening.py::test_health_reports_pool_saturation_degraded_reason`
  fails in the full pytest suite for reasons unconnected to this change
  (confirmed unrelated via grep + git status) — separate, non-blocking, worth
  the user's attention outside this change's scope.

## Cold Data Warning

This archive is historical evidence. Current requirements live in `contracts/`
and active project guidance (`CLAUDE.md`); do not treat this file as a source
of current requirements in future work.
