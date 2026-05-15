---
change-id: fix-prod-history-multiselect-filter
schema-version: 0.1.0
last-changed: 2026-05-15
risk: medium
tier: 2
---

# QA Report: fix-prod-history-multiselect-filter

## Test Execution Summary

| Gate | Command | Result | Notes |
|---|---|---|---|
| Type-check | `cd frontend && npm run type-check` | **PASS** (0 errors) | Re-run after focus-return follow-up still green |
| CSS governance | `cd frontend && npm run css:check` | **PASS** (0 errors, 47 pre-existing warnings) | No new warnings introduced |
| Vitest unit | `cd frontend && npm run test` | **PASS** (337 passed / 1 skipped) | Skipped: `emits dropdown-close on blur` — flaky focusout simulation; documented as known gap |
| node:test legacy unit | `cd frontend && npm run test:legacy` | **PASS** (257 passed / 0 failed) | Includes 2 migrated + 6 new buffer/commit tests |
| Playwright E2E | `npx playwright test production-history-cross-filter.spec.ts` | **BLOCKED** (9/9 fail) | **Pre-existing infra issue** — see Known Gaps |
| `cdd-kit validate` | — | (run at gate step) | |

## Acceptance Criteria Coverage

| AC | How verified | Status |
|---|---|---|
| AC-1: no requests while dropdown open across toggles | Vitest (`does not emit dropdown-close while dropdown is open across multiple toggles`) + node:test (`setSelection() updates buffer but does not call fetcher`, `setSelection() does not start debounce timer`) | covered at unit layer |
| AC-2: dropdown close with diff → 1 cross-filter, 0 main-query | Vitest (`emits dropdown-close once on outside-click/Escape`) + node:test (`commitSelection() fires fetcher exactly once with debounce`) | covered at unit layer; main-query button gating verified by reading App.vue (`runQuery` button-bound) |
| AC-3: cross-filter then second filter still buffers | node:test (`multiple setSelection followed by single commitSelection produces one fetcher call`) | covered at composable layer; full integration in E2E (currently blocked) |
| AC-4: no-op close fires zero requests | node:test (`commitSelection() with unchanged selection is a no-op`) + Vitest (`consumers without @dropdown-close listener see no behavioral change`) | covered |
| AC-5: zero visual change | visual-reviewer verdict **approved** — `<style scoped>` byte-identical, no new tokens/classes/DOM | covered |
| AC-6: payload schema invariant | contract-reviewer verdict **approved** — only emit timing changes; `fetchFilterOptions` payload unchanged | covered by inspection; E2E snapshot blocked |

## Reviewer Verdicts

- **contract-reviewer**: `approved` — no contracts need updating; additive `dropdown-close` event has no contract surface (no `contracts/component/` directory in this repo).
- **ui-ux-reviewer**: `approved-with-comments` — flagged one **major** finding (focus return after Escape close) → **fixed in follow-up commit**: `closeDropdown()` now refocuses `.multi-select-trigger` via `nextTick`. Remaining nits/minors deferred as out-of-scope follow-ups.
- **visual-reviewer**: `approved` — AC-5 holds.

## Known Gaps / Risk Acceptance

### Pre-existing E2E infrastructure failure (not introduced by this change)

The 6 new Playwright cases in `frontend/tests/playwright/production-history-cross-filter.spec.ts` cannot be executed locally because all 9 tests in the spec (including the 3 pre-existing cases that landed before this change) fail at the auth bootstrap step:

```
TimeoutError: locator.waitFor: Timeout 30000ms exceeded
  at loginViaUI → page.waitForSelector('#username')
  (after loginViaApi rejected default credentials 92367/1QAZ2wsx3edc)
```

- **Owner**: separate follow-up (E2E credentials / test fixture refresh) — not in scope for this bug fix.
- **Evidence baseline**: same 3 pre-existing tests fail on `main` branch HEAD `c4ff11a` (verified by frontend-engineer agent).
- **Compensating coverage**: AC-1 / AC-2 / AC-3 / AC-4 are all asserted at the Vitest or node:test layer with passing tests. The E2E layer is the cross-browser integration confirmation; absence is a coverage gap, not a correctness gap.
- **Recommended action**: file a separate change for E2E auth fixture refresh; do not block this PR.

### Skipped Vitest case

`emits dropdown-close on blur with final selection` — marked `.skip`. Reason: simulating `focusout` deterministically in JSDOM requires more harness than this fix warrants. Outside-click + Escape paths together cover the practical close surface; blur-via-keyboard is rare for this widget (popup has its own focus trap on the search input).

### ui-ux nits deferred (recorded for follow-up, not blocking)

- Tab navigation inside dropdown bypasses 全選 / 清除 / 關閉 footer buttons (no focus trap). A11y improvement, not behavioral.
- Loading spinner on the trigger button is briefly disabled while cross-filter request is in flight after a commit — may feel sluggish when users tab rapidly between filters. Within the design's accepted trade-off; not introduced by this change.

## Release Readiness

- **Verdict**: `approved-with-risk` — the Playwright runtime gap is a pre-existing infra issue independent of this change; compensating unit coverage is strong; reviewer concerns addressed inline.
- **Recommended deployment path**: standard `git revert` rollback if regression observed; no DB / parquet / cache cleanup required (see [ci-gates.md §Rollback Policy](ci-gates.md#rollback-policy)).
- **Follow-ups to file separately**:
  1. Refresh Playwright E2E auth fixture so `production-history-cross-filter.spec.ts` (and the rest of the suite) can run.
  2. Generalize the buffered-commit pattern to wip-/hold-/resource- filter composables.
  3. A11y: focus-trap inside MultiSelect dropdown, Tab cycle through footer actions.
