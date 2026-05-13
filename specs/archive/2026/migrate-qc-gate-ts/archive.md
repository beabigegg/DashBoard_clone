---
change-id: migrate-qc-gate-ts
archived: 2026-05-13
---

# Archive — migrate-qc-gate-ts

## Change Summary

Migrated `frontend/src/qc-gate/` (QC-GATE 狀態) from JavaScript to TypeScript as Phase 3 item #17 of the project-wide TS migration plan. Five files were affected: `main.js→main.ts`, `App.vue`, `composables/useQcGateData.js→.ts`, `components/LotTable.vue`, `components/QcGateChart.vue`. The CI/CD gate contract was bumped from 1.3.7 to 1.3.8 to document the `frontend-type-check` scope expansion to `src/qc-gate/**/*`. A post-push fix was required to loosen two legacy `node --test` source-text assertions that hardcoded pre-migration JS syntax.

## Final Behavior

The system now compiles `src/qc-gate/**/*` under `strict: true` via `frontend/tsconfig.json`. No runtime behavior changed — all logic, templates, and CSS are identical to the pre-migration state. The `frontend-type-check` informational gate now covers 14 scopes including `qc-gate/`.

## Final Contracts Updated

- `contracts/ci/ci-gate-contract.md` — schema-version 1.3.7 → 1.3.8; Gate Compatibility Note added for Phase 3 item #17 scope expansion.
- `contracts/CHANGELOG.md` — entry `[ci 1.3.8] — 2026-05-13` added.

## Final Tests Added / Updated

- `frontend/tests/legacy/portal-shell-wave-a-chart-lifecycle.test.js` — two assertions loosened:
  - `/const activeFilter = ref\(null\)/` → `/const activeFilter = ref/`
  - `/function handleChartSelect\(filter\)/` → `/function handleChartSelect\(filter/`
  These were hardcoded JS-syntax regexes that broke when `App.vue` adopted TS type parameters.
- No new Vitest tests required — existing 302/302 suites cover behavior unchanged.

## Final CI/CD Gates

| Gate | Result |
|---|---|
| frontend-unit (Vitest 302/302) | PASSED |
| frontend-legacy (node --test) | PASSED (after fix commit 6c75e54) |
| css-governance | PASSED |
| frontend-type-check | PASSED (0 errors; informational) |
| frontend-build | PASSED (CI) |
| contract-validate | PASSED (CI) |
| cdd-strict-gate | PASSED (CI) |

## Production Reality Findings

**Legacy test assertion brittleness** (deviation from plan): The `portal-shell-wave-a-chart-lifecycle.test.js` legacy test suite contained source-text regex assertions using hardcoded JS syntax — `ref(null)` without a type parameter, and `handleChartSelect(filter)` without a type annotation. After migration these matched against the TypeScript form `ref<ActiveFilter | null>(null)` and `handleChartSelect(filter: ActiveFilter): void`, causing CI failure. A fix commit (`6c75e54`) loosened both regexes to prefix matches. This pattern recurred from prior migrations (similar issue was seen in migrate-shared-composables-ts) and indicates a systematic brittleness in the legacy test suite.

No other deviations from plan. The `as unknown as ApiPayload` double-cast, echarts `unknown` callback parameter, and local `ActiveFilter` interface strategy all worked as expected per established migration rules.

## Lessons Promoted to Standards

- **CLAUDE.md — TypeScript Migration Rules** (appended): When migrating an SFC that has a paired `node --test` legacy test using `readSource` + `assert.match`, audit every regex for JS-specific syntax (bare `ref\(null\)`, untyped function signatures). Replace with prefix/looser forms that survive both JS and TS. Evidence: `frontend/tests/legacy/portal-shell-wave-a-chart-lifecycle.test.js` lines 42–44; commit `6c75e54`.

## Follow-up Work

- `frontend-type-check` gate promotion from informational to required follows the standard Informational Gate Promotion Policy (20 calendar days / 60 runs / pass rate above threshold / failures triaged / owner assigned). No action required in this change.
- Any remaining legacy test suite source-text assertions that use hardcoded JS syntax (bare `ref(null)`, untyped function signatures) should be audited before future Phase 3 migrations to prevent repeat CI failures.

## Cold Data Warning

This archive is historical evidence. Current requirements live in `contracts/` and active project guidance (`CLAUDE.md`).
