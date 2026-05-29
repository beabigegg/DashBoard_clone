# Change Classification

## Change Types
- primary: feature-add (new page + new routes + new SQL + new Vue3 app)
- secondary: api-only-change (new endpoints), ui-only-change (new UI surface), business-logic-change (downtime aggregation rules, big-category mapping, cross-shift event merge, JOBID fallback bridge)

## Risk Level
- medium

Rationale: new surface area only — no existing behavior changes. Reuses the proven resource-history cache/spool/DuckDB pattern. Risk comes from (a) novel business rules (E10 status filter, JOBID-then-time-overlap bridge, cross-shift event merge), (b) Oracle column semantics (CHAR trailing-space, midnight-UTC DATE, partial-merge style invariants), (c) modernization-policy JSON files that crash gunicorn on startup if mis-edited.

## Impact Radius
- cross-module

Touches: backend routes/services/SQL, frontend Vue3 app + Vite entry + portal-shell registration, contracts (API/business/data), modernization JSON files, data/page_status.json, navigation/drawer wiring.

## Tier
- 1

## Architecture Review Required
- yes
- reason: Three non-obvious design decisions need a written design before implementation: (1) cross-shift event-merge key — wrong key risks silent row collapse like the prod-history partial-merge incident; (2) JOBID-primary + RESOURCEID+time-overlap fallback bridge — tiebreak rules, no-match handling, future IT JOBID backfill version-key invalidation; (3) spool/cache namespace decision (new downtime_analysis_* vs. extend resource_dataset_*) — has direct rollback-runbook and parquet-cleanup implications.

## Required Artifacts
Always required: change-request.md, change-classification.md, implementation-plan.md, test-plan.md, ci-gates.md, tasks.yml, context-manifest.md

## Optional Artifacts
| artifact | create? | reason |
|---|---|---|
| current-behavior.md | no | new page; no prior behavior to baseline |
| proposal.md | no | scope captured in change-request; design.md covers open architectural decisions |
| spec.md | no | acceptance criteria + business-rules-contract changes are sufficient |
| design.md | yes | three non-obvious decisions must be pinned before backend-engineer or SQL is written |
| qa-report.md | yes | new public page, two distinct user personas, JOBID coverage gap (~50% UDT) is known partial-failure surface |
| regression-report.md | no | additive change; no shared mutation surface with existing features |
| visual-review-report.md | yes | new UI surface with dual-view layout, charts, .theme-downtime-analysis CSS scope |
| monkey-test-report.md | no | not a high-input-volatility form |
| stress-soak-report.md | no | reuses resource-history cache architecture; not novel infra |

## Required Contracts
- API: contracts/api/api-contract.md, contracts/api/api-inventory.md — new `/api/downtime-analysis/*` endpoint family; CHANGELOG entry in contracts/CHANGELOG.md
- CSS/UI: contracts/css/css-inventory.md — register frontend/src/downtime-analysis/style.css; confirm .theme-downtime-analysis scoping per rule 4.4
- Env: none (no new env vars; revisit if pre-warm flag added)
- Data shape: contracts/data/data-shape-contract.md — define response shapes for daily-time, big-category-breakdown, top-reasons, equipment-detail-row, event-detail-row; document JOBID-null sentinel (null) handling
- Business logic: contracts/business/business-rules.md — new domain rules DA-01..DA-06
- CI/CD: contracts/ci/ci-gate-contract.md — only if new gate added; existing gates cover otherwise

## Required Tests
- unit: backend service for big-category mapping, cross-shift merge key, JOBID bridge (overlap/no-overlap/multi-overlap), filter narrowing; frontend composables for filter state, view-toggle, formatters (Oracle DATE midnight-UTC handling)
- contract: new endpoints vs data-shape-contract; tests/test_api_contract.py entries for each new route; DA-01..DA-06 assertion tests
- integration: route → service → SQL runtime end-to-end; snapshot/cache AND Oracle fallback paths BOTH covered for every filter kwarg; page_status.json and asset_readiness_manifest.json entries asserted in tests/test_modernization_policy_hardening.py
- E2E: frontend/tests/playwright/downtime-analysis.spec.js (overview loads, detail loads, filter cross-narrowing, JOBID-null row renders —, view toggle preserves state); tests/e2e/test_downtime_analysis_e2e.py
- visual: .theme-downtime-analysis scoping; teleport wrappers carry theme class per css-contract rule 4.4
- data-boundary: Oracle CHAR trailing-space strip(); null OLDREASONNAME, null JOBID, null wait-hours; midnight-UTC DATE detection
- resilience: Oracle timeout → fallback; Redis-down → spool; cache pre-warm contention (multi-worker lock); spool rebuild on IT JOBID backfill
- fuzz/monkey: not required
- stress: not required pre-merge; add to nightly registry only if cardinality proves heavier than resource-history
- soak: not required pre-merge

## Required Agents
1. spec-architect — writes design.md (merge key, JOBID bridge, spool namespace, big-category taxonomy, partial-failure contract)
2. contract-reviewer — updates API, data-shape, business-rules, css-inventory contracts; writes CHANGELOG entries to contracts/CHANGELOG.md
3. test-strategist — produces test-plan.md with AC→test mapping, fixture discipline for cross-shift merge and JOBID-bridge
4. ci-cd-gatekeeper — writes ci-gates.md
5. implementation-planner — writes implementation-plan.md after design + contracts + test plan are available
6. backend-engineer — routes, service, SQL runtime, spool/cache integration, blueprint registration, modernization JSON updates
7. frontend-engineer — Vue3 app, Vite entry, portal-shell registration, .theme-downtime-analysis CSS scope, midnight-UTC DATE formatter
8. contract-reviewer — post-implementation verification
9. ui-ux-reviewer — visual review, dual-view UX, focus management, theme scoping
10. visual-reviewer — CSS scope, chart rendering, responsive layout
11. qa-reviewer — final sign-off, writes qa-report.md capturing JOBID coverage gap as approved-with-risk

## Inferred Acceptance Criteria
- AC-1: `/api/downtime-analysis/summary` returns per-day downtime hours split into UDT/SDT/EGT buckets from SHIFT rows where OLDSTATUSNAME IN ('UDT','SDT','EGT'), summed by HOURS.
- AC-2: `/api/downtime-analysis/big-category` returns the eight-bucket taxonomy (維修/保養/換型換線/換刀清模/檢查/待料待指示/工程/其他未分類) with hours and event-count per bucket; mapping is deterministic per DA-04.
- AC-3: `/api/downtime-analysis/top-reasons` returns top-N OLDREASONNAME rows ordered by total downtime hours with hours, event-count, and average-event-duration.
- AC-4: A downtime event crossing a shift boundary is merged backend-side into one row with summed hours and earliest start timestamp per DA-02.
- AC-5: Event detail enriches each event with DW_MES_JOB columns (症狀/原因細項/維修動作/處理人/等待工時/維修工時) using JOBID when present, else RESOURCEID+time-overlap fallback; rows with no JOB match render JOB columns as null (frontend shows —) per DA-03, DA-05.
- AC-6: Filter dropdowns cross-narrow consistently; selecting equipment=X narrows reason and big-category dropdowns but excludes self (equipment dropdown still shows all options).
- AC-7: Navigation entry appears in sidebar via data/page_status.json; portal-shell loads frontend/src/downtime-analysis/ lazily; all CSS in style.css passes npm run css:check Rule 6 under .theme-downtime-analysis.
- AC-8: When IT backfills SHIFT.JOBID post-deploy, spool layer detects change via version key and rebuilds without manual parquet deletion; contingency documented in ci-gates.md §Rollback Policy.

## Tasks Not Applicable
- not-applicable: 6.4

## Clarifications or Assumptions
- Assumption: page registers under existing drawer (likely drawer-1 analytics group); confirmed during design.md.
- Assumption: spool namespace will be downtime_analysis_* (new) to keep cache invalidation independent for IT-JOBID-backfill scenario.
- Assumption: no new env var; if pre-warm flag needed, revisit env-contract.md.
- Open: IT JOBID backfill timing — change ships with bridge logic; spool version-key handles future backfill.
- Open: cross-shift merge key — working hypothesis from change-request §Open Questions; design.md must validate with fixture spanning ≥2 shift boundaries.
