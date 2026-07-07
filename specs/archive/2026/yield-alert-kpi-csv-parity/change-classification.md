# Change Classification

## Change Types
- primary: business-logic-change (KPI/CSV scope unification with a `contracts/business/business-rules.md` update), bug-fix (CSV float precision)
- secondary: api-only-change (behavior of `GET /api/yield-alert/view` summary payload changes — same shape, changed values/semantics)

## Risk Level
- medium

## Impact Radius
- module-level → cross-module (touches shared CTE aggregation patterns in `yield_alert_sql_runtime.py` used by summary/trend/heatmap)

## Tier
- 2

Rationale: Part 1 changes SQL aggregation semantics in `yield_alert_sql_runtime.py`, a file where `summary`/`trend`/`heatmap` share similar CTE patterns, and introduces a tx-dedup correctness fix (double-counting risk on `transaction_qty`). It alters a numeric value users reconcile against exports and adds a business-rule contract. Not Tier 0/1: no auth/payments/migration/concurrency surface, no system-wide blast radius.

## Lane
- bug-fix

Note: promoted to carry `business-logic-change` as a primary change-type (see Change Types above) because a business-rules contract (YA-13) + data-shape semantics change is required. The investigative discipline of the bug-fix lane (reproduction, root cause, failing test, regression test) still applies.

## Bug Symptom Type
- data

## Diagnostic Only
- no

## Bug Evidence Required
- symptom: KPI card 移轉量/報廢量 do not reconcile with CSV detail totals under the same filters; CSV emits values like `4011.9999999999995`.
- expected behavior: KPI 移轉量/報廢量 reflect alert-candidate totals under current filters (same scope as `_query_alerts()`), reconciling with CSV detail sums after tx dedup; CSV numeric fields are cleanly rounded.
- actual behavior: KPI uses whole-plant `SUM` over `dept_proc_where` only, ignoring `risk_threshold`/`min_scrap_qty`/`SCRAP_QTY<>0` and 4 of 6 filter dims; CSV writes raw floats via `String(v)`.
- reproduction status: to be captured by `bug-fix-engineer`.
- hypotheses: (1) KPI scope divergence from alert-candidate scope; (2) naive SUM over `alerts_filtered.transaction_qty` double-counts when a group has multiple reason_codes; (3) missing rounding in `_buildAlertsCSV()`.
- root cause pointer: `yield_alert_sql_runtime.py:196-240` (`_query_summary`), `:491-670` / `:533-548` (`_query_alerts`, `tx_lookup`), `:656-657` (ROUND DOUBLE); `frontend/src/yield-alert-center/App.vue:643-660` (`_buildAlertsCSV`), `frontend/src/yield-alert-center/utils.ts:6-8` (`toPcs`).
- regression evidence: new failing test asserting KPI↔CSV reconciliation (post-dedup) and a CSV-formatting test; both must fail before the fix and pass after.

## Architecture Review Required
- yes
- reason: The dedup + scope-unification decision is architecturally significant. It defines a shared aggregation contract across the yield-alert `summary`/`trend`/`heatmap` CTE patterns, decides the tx-dedup dimension (excluding `REASON_CODE`) to avoid double-counting, and codifies a new business rule (YA-13). Implementation agents should not infer the dedup dimension from chat history — it must be settled in `design.md` first.

## Required Artifacts
Always required: change-request.md, change-classification.md, implementation-plan.md, test-plan.md, ci-gates.md, tasks.yml, context-manifest.md

## Optional Artifacts (default: no — set yes only with explicit reason)
| artifact | create? | reason |
|---|---|---|
| current-behavior.md | no | Current behavior fully documented in change-request root-cause section |
| proposal.md | no | Scope/direction already settled |
| spec.md | no | Behavior decision fits in design.md + implementation-plan.md |
| design.md | yes | Architecture Review Required = yes; dedup-dimension and KPI-scope-unification decision must be recorded before planning |
| qa-report.md | no | Routine pass/fail belongs in agent-log/qa-reviewer.yml; promote only if QA finds blocking findings |
| regression-report.md | no | Regression scope captured in test-plan + failing/passing tests |
| visual-review-report.md | no | No visual/layout change (KPI card values change, not UI structure or styling) |
| monkey-test-report.md | no | Not applicable |
| stress-soak-report.md | no | No new load/concurrency surface |

## Required Contracts
- API: contracts/api/api-contract.md — `GET /api/yield-alert/view` summary field semantics change (values/scope), same shape
- CSS/UI: none
- Env: none
- Data shape: contracts/data/data-shape-contract.md — CSV export column formatting (rounded pcs granularity) for transaction_qty/scrap_qty
- Business logic: contracts/business/business-rules.md — new rule (YA-13) defining KPI scope = alert-candidate scope + tx-dedup dimension
- CI/CD: none

## Required Tests
- unit: yes — backend `_query_summary` scope + tx-dedup; frontend `_buildAlertsCSV()` rounding
- contract: yes — business-rule (YA-13) assertion + API summary-field semantic pin
- integration: yes — KPI↔CSV reconciliation across route + service, fixture with multiple reason_codes per group
- E2E: optional — Playwright CSV export assertion, deferred to test-strategist, not blocking at Tier 2
- visual: no
- data-boundary: yes — CSV numeric formatting fixture reproducing the `4011.9999999999995` case
- resilience: no
- fuzz/monkey: no
- stress: no
- soak: no

## Required Agents
1. spec-architect
2. implementation-planner
3. bug-fix-engineer
4. backend-engineer
5. frontend-engineer
6. test-strategist
7. contract-reviewer
8. qa-reviewer

(ci-cd-gatekeeper also runs per the always-required `ci-gates.md` artifact rule, even though no CI/CD contract change is expected.)

## Inferred Acceptance Criteria
- AC-1: Under a given date range + set of dimension filters, the KPI card 移轉量 equals the tx-dedup sum of the CSV detail transaction_qty for the same filters, within pcs-level rounding tolerance.
- AC-2: Under the same filters, the KPI card 報廢量 equals the sum of CSV detail scrap_qty (no dedup needed) within pcs-level rounding tolerance.
- AC-3: The KPI summary applies the same alert-candidate predicate as `_query_alerts()`: SCRAP_QTY <> 0, exclusion of (yield_pct >= risk_threshold AND scrap_qty < min_scrap_qty), and all 6 dimension filters.
- AC-4: When a (workorder+date+dept+proc+line+package+type+function+operation) group has multiple distinct reason_code rows, KPI 移轉量 counts that group's transaction_qty exactly once (no double-counting).
- AC-5: CSV export transaction_qty and scrap_qty columns contain cleanly rounded values (no float noise such as 4011.9999999999995), Excel-parseable as numbers.
- AC-6: A new business rule (YA-13) in contracts/business/business-rules.md documents the KPI scope definition and tx-dedup dimension; CHANGELOG carries the version entry.
- AC-7: `GET /api/yield-alert/view` response shape is unchanged (only summary values/semantics change); contract samples regenerate cleanly with no unexpected drift.

## Tasks Not Applicable
- not-applicable: 2.2 (CSS/UI contract — no UI/CSS change), 2.3 (Env contract — no env var change), 2.6 (CI/CD contract — none required), 4.4 (CI/CD workflows — none required), 5.1 (UI/UX review — no UI/UX change, values only), 5.2 (Visual review — no visual/layout change), 3.5 (Stress/soak tests — no new load/concurrency surface)

## Clarifications or Assumptions
- Deferred: contracts/api/api-contract.md Compatibility Notes/CHANGELOG addition for this change was deferred (not applied) — the repo's `pre-tool-use-contract-write.sh` hook hardcodes `CDD_CONTRACT_WRITE_STRICT=1` for this file, and `cdd-kit contract endpoint set`/`schema set` only mutate structured table cells, not prose sections. User declined a permanent settings.json change to bypass this for a one-time edit. business-rules.md YA-13 and data-shape-contract.md §3.16.7 fully document the value-semantics change; no endpoint request/response shape actually changed. Tracked as a known gap on tasks.yml item 2.1.
- Assumption: Part 1 changes `GET /api/yield-alert/view` summary values but not the response JSON shape.
- Assumption: The rounding granularity for CSV is a design decision for spec-architect; requester suggests parity with yield_pct/risk_score handling or pcs granularity — record the chosen precision in the data-shape contract and YA-13.
- Assumption: No lockfile/dependency/migration changes.
- Open question for design: whether trend/heatmap KPIs share the old whole-plant scope and therefore need the same unification, or whether only the top summary cards change — must be decided explicitly to avoid a partial fix that re-introduces the reconciliation gap elsewhere.

## Context Manifest Draft
<!-- Copied verbatim into context-manifest.md -->

### Affected Surfaces
- yield-alert-center (良率警報中心): backend SQL aggregation + route, frontend Vue/TS CSV export, business-rules contract.

### Allowed Paths
- specs/changes/yield-alert-kpi-csv-parity/
- specs/context/project-map.md
- specs/context/contracts-index.md
- contracts/business/business-rules.md
- contracts/api/api-contract.md
- contracts/api/api-inventory.md
- contracts/api/openapi.json
- contracts/data/data-shape-contract.md
- contracts/CHANGELOG.md
- contracts/openapi.json
- src/mes_dashboard/services/yield_alert_sql_runtime.py
- src/mes_dashboard/routes/yield_alert_routes.py
- src/mes_dashboard/sql/yield_alert/
- frontend/src/yield-alert-center/
- tests/
- frontend/tests/unit/
- frontend/tests/playwright/
- frontend/tests/validation/
- frontend/tests/yield-alert/

### Agent Work Packets

#### spec-architect
- specs/changes/yield-alert-kpi-csv-parity/
- contracts/business/business-rules.md
- contracts/api/api-contract.md
- contracts/data/data-shape-contract.md
- src/mes_dashboard/services/yield_alert_sql_runtime.py
- src/mes_dashboard/routes/yield_alert_routes.py
- src/mes_dashboard/sql/yield_alert/
- frontend/src/yield-alert-center/

#### implementation-planner
- specs/changes/yield-alert-kpi-csv-parity/
- contracts/business/business-rules.md
- contracts/api/api-contract.md
- contracts/data/data-shape-contract.md
- src/mes_dashboard/services/yield_alert_sql_runtime.py
- src/mes_dashboard/routes/yield_alert_routes.py
- src/mes_dashboard/sql/yield_alert/
- frontend/src/yield-alert-center/
- tests/
- frontend/tests/unit/
- frontend/tests/yield-alert/
- frontend/tests/playwright/

#### bug-fix-engineer
- specs/changes/yield-alert-kpi-csv-parity/
- src/mes_dashboard/services/yield_alert_sql_runtime.py
- src/mes_dashboard/routes/yield_alert_routes.py
- frontend/src/yield-alert-center/
- tests/
- frontend/tests/unit/
- frontend/tests/yield-alert/

#### backend-engineer
- specs/changes/yield-alert-kpi-csv-parity/
- src/mes_dashboard/services/yield_alert_sql_runtime.py
- src/mes_dashboard/routes/yield_alert_routes.py
- src/mes_dashboard/sql/yield_alert/
- contracts/business/business-rules.md
- contracts/api/api-contract.md
- contracts/api/openapi.json
- contracts/openapi.json
- contracts/data/data-shape-contract.md
- contracts/CHANGELOG.md
- tests/
- tests/integration/
- tests/contract/

#### frontend-engineer
- specs/changes/yield-alert-kpi-csv-parity/
- frontend/src/yield-alert-center/
- frontend/tests/unit/
- frontend/tests/yield-alert/
- frontend/tests/playwright/

#### test-strategist
- specs/changes/yield-alert-kpi-csv-parity/
- src/mes_dashboard/services/yield_alert_sql_runtime.py
- src/mes_dashboard/routes/yield_alert_routes.py
- frontend/src/yield-alert-center/
- tests/
- tests/integration/
- tests/contract/
- frontend/tests/unit/
- frontend/tests/yield-alert/
- frontend/tests/playwright/

#### contract-reviewer
- specs/changes/yield-alert-kpi-csv-parity/
- contracts/business/business-rules.md
- contracts/api/api-contract.md
- contracts/api/api-inventory.md
- contracts/data/data-shape-contract.md
- contracts/CHANGELOG.md

#### qa-reviewer
- specs/changes/yield-alert-kpi-csv-parity/
- contracts/business/business-rules.md
- contracts/data/data-shape-contract.md

### Context Expansion Requests
- request-id: CER-001
  requested_paths: src/mes_dashboard/sql/yield_alert/
  reason: project-map truncates this directory; exact .sql template files backing _query_summary/_query_alerts not enumerated in the index. Needed by spec-architect/backend-engineer to confirm the dedup dimension.
  status: pending
- request-id: CER-002
  requested_paths: tests/ (specific yield-alert backend test files)
  reason: index truncates tests/ (189 more entries); exact test_yield_alert*.py filenames not confirmed. test-strategist/implementation-planner should narrow to specific files once confirmed.
  status: pending
