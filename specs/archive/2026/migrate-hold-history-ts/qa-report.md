---
change-id: migrate-hold-history-ts
schema-version: 0.1.0
last-changed: 2026-05-12
agent: qa-reviewer
---

# QA Report — migrate-hold-history-ts

## Verdict

**approved**

No blocking defects. All pre-merge gates (frontend-unit, css-governance, type-check) passed. No bare `any`, no `@ts-expect-error`. The `useAutoRefresh.js` audit decision is documented and correct. TODO:type debt is bounded, reasoned, and consistent with the pattern established in reject-history. AC-12 (cdd-kit gate --strict) is deferred to post-QA per task plan — no dependency on this review.

---

## AC Coverage

| AC | Description | Verified By | Status |
|---|---|---|---|
| AC-1 | main.js → main.ts; index.html unchanged | File presence check: `main.ts` exists; `index.html` still references `./main.js` (correct per CLAUDE.md rule) | PASS |
| AC-2 | useAutoRefresh.js audit: renamed in-place to .ts; local API diverges from shared | Agent-log decision note; file presence of `useAutoRefresh.ts`; no shared import; API difference documented | PASS |
| AC-3 | useHoldHistoryDuckDB.js → .ts with explicit types; DuckDB rows typed | File presence check; agent-log confirms DuckDBClient imported directly from core (already .ts, no @ts-expect-error needed) | PASS |
| AC-4 | App.vue `<script setup lang="ts">`, typed reactive state, bare specifiers | grep confirmed `lang="ts"` on App.vue; no stale `.js"` specifiers found | PASS |
| AC-5 | All 8 SFCs use `<script setup lang="ts">` with typed defineProps | grep confirmed all 9 files (App.vue + 8 components) carry `lang="ts"`; defineProps generic confirmed in all 8 components | PASS |
| AC-6 | Zero stale `.js"` specifiers in migrated files | grep for `\.js"` in hold-history: only `index.html` src attribute (excluded per rule) | PASS |
| AC-7 | tsconfig.json include has `"src/hold-history/**/*"` | grep on tsconfig.json confirmed entry on line 19 | PASS |
| AC-8 | ci-gate-contract.md schema-version 1.3.6; CHANGELOG [ci 1.3.6] added | ci-gates.md header confirmed; contract-reviewer status: done (tasks.yml 5.3) | PASS |
| AC-9 | npm run type-check 0 errors; npm run build 0 errors; css:check 0 violations | Agent-log type_check_result: 0 errors; gate results from briefing confirmed all three pass | PASS |
| AC-10 | 270/270 Vitest tests pass; no regressions | Gate results: 270/270, 27 test files | PASS |
| AC-11 | 14 TODO:type annotations with reasons; 0 bare any; 0 @ts-expect-error | Source scan: 22 comment lines (multiple per echarts file = expected); 0 bare `any`/`as any`/`: any`; 0 `@ts-expect-error` | PASS |
| AC-12 | cdd-kit gate --strict | Pending — to run after qa-review; not a QA-reviewer responsibility | PENDING |

---

## TODO:type Debt

14 logical annotation points (22 physical comment lines due to multiple echarts callbacks per file). All have explicit reasons. No bare `any`.

| File | Count (logical) | Category | Reason |
|---|---|---|---|
| App.vue | 7 | server API response shapes | /query, /view, /config, /export, snapshot, list payload, trend endpoints not in frontend/src/types/ |
| SummaryCards.vue | 1 | mode-discriminated shape | summary keys vary by range/today/current mode; needs union type |
| DetailTable.vue | 1 | DuckDB vs server union | HoldListItem typed in DuckDB composable; server path untyped |
| ReasonPareto.vue | 1 | same as DetailTable | server path untyped |
| DurationChart.vue | 1 | same as DetailTable | server path untyped |
| DailyTrend.vue | 1 | echarts callbacks | echarts formatter/color callbacks; per CLAUDE.md rule |
| DurationChart.vue | 1 | echarts callbacks | same |
| ReasonPareto.vue | 1 | echarts callbacks | same |

**Resolution path:** debt clears when (a) server API response types are promoted to `frontend/src/types/` and (b) hold-history adopts those types. No action required from this migration.

---

## Non-blocking Observations

1. **TODO:type count discrepancy (cosmetic).** The agent-log reports 14 annotations; the source contains 22 physical comment lines. The difference is entirely due to multiple echarts callback sites per file (DailyTrend: 3 lines, DurationChart: 4 lines, ReasonPareto: 3 lines). All are annotated and reasoned. No action needed; a future update to agent-log counting guidance could clarify "logical annotation points vs. physical comment lines."

2. **index.html `src="./main.js"` is intentional and correct.** Vite resolves `main.ts` at build time. This is explicitly endorsed in CLAUDE.md TypeScript Migration Rules and the change-request. Reviewers should not flag this as a defect.

3. **useAutoRefresh triplication.** Three distinct `useAutoRefresh` implementations exist in the codebase (hold-history local, shared-composables, wip-shared). The divergent APIs preclude consolidation without behavioral risk. The in-place rename decision is correct for this Tier 3 migration. A future consolidation should be a separate tracked change.

4. **AC-12 gate is post-QA.** `cdd-kit gate --strict` is listed as PENDING in tasks.yml (task 6.1) and is not a QA-reviewer gate. This report does not block on it.

---

## Sign-off

- Reviewer: qa-reviewer agent
- Date: 2026-05-12
- Change: migrate-hold-history-ts (Phase 3, item #2)
- Verdict: **approved**
