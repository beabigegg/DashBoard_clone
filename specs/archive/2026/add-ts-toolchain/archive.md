# Archive: add-ts-toolchain

> **Cold Data Warning**: This archive is historical evidence. Current requirements live in `contracts/` and active project guidance.

---

## Change Summary

Phase 0 of the TypeScript migration plan (`ts-migration-plan.md`). Installed
`typescript@6.0.3`, `vue-tsc@3.2.8`, and `@types/node@25.6.0` as devDependencies;
added `tsconfig.json` (strict mode, `allowJs: false`, `include: ["src/core/"]`);
renamed `vite.config.js` → `vite.config.ts`; added `npm run type-check` script;
and wired a `frontend-type-check` CI step with `continue-on-error: true`
(informational gate). The goal was to establish a passing `type-check` baseline
before migrating any source files.

## Final Behavior

- `npm run type-check` (`vue-tsc --noEmit`) runs from `frontend/` and exits 0 with 0 errors.
- Vite continues to resolve its config from `vite.config.ts` (native TS config support; no behavior change).
- CI runs `type-check` as an informational step inside the `frontend-unit-tests` job; the step will not block merge.
- All 270 existing Vitest tests continue to pass.

## Final Contracts Updated

| Contract file | Change |
|---|---|
| `contracts/ci/ci-gate-contract.md` | schema-version 1.1.0 → 1.2.0; added `frontend-type-check` gate row (tier 1, informational) |
| `contracts/CHANGELOG.md` | `[ci 1.2.0] — 2026-05-05` entry added |

Evidence: `agent-log/contract-reviewer.yml` → `artifacts: version-bumps`

## Final Tests Added / Updated

No new test files. Verification was via smoke commands (`vue-tsc --noEmit`,
`cdd-kit validate`). The existing Vitest suite (270 tests, 27 files) serves as
regression coverage at Tier 1.

Evidence: `agent-log/test-strategist.yml` → `artifacts: tdd-pairs: n/a`

## Final CI/CD Gates

| Gate | Tier | Required | Notes |
|---|---:|---|---|
| `frontend-type-check` | 1 | informational | `continue-on-error: true`; promotion when ≥20 days / ≥60 runs / ≥95% pass rate / ≤90 s runtime |
| `frontend-unit-tests` | 1 | required | unchanged |
| `contract-driven-gates` | 0 | required | unchanged |

Promotion action: remove `continue-on-error: true` and update `ci-gate-contract.md` required column from `informational` → `yes`.

Evidence: `specs/changes/add-ts-toolchain/ci-gates.md`

## Production Reality Findings

One non-obvious toolchain requirement discovered during implementation:
`vue-tsc` (and the underlying `tsc`) exits with error TS18003 ("No inputs were
found") when `allowJs: false` and `include` resolves to zero `.ts` files. This
blocks a clean Phase 0 where no production source files are migrated yet.
Resolution: add `frontend/src/core/index.ts` as a minimal placeholder (`export {}`)
to satisfy the compiler's input requirement without introducing any runtime behavior.

Evidence: `agent-log/frontend-engineer.yml` → `notes`

One pre-existing CVE was noted but not introduced by this change:
`postcss@8.5.6` moderate GHSA-qx2v-qp2m-jg93 — tracked separately.

Evidence: `agent-log/dependency-security-reviewer.yml` → `artifacts: cve-findings`

## Lessons Promoted to Standards

1. **`CLAUDE.md` § Dev commands → Lint / Type**: Added `cd frontend && npm run type-check` (vue-tsc --noEmit; Phase 0 scope: src/core/ only).
   - Evidence: `agent-log/frontend-engineer.yml` → `artifacts: files-changed: frontend/package.json:1-38` (type-check script confirmed present)
   - Classification: promote-to-guidance (durable dev workflow command, not a product behavior rule)

No contract schema changes required. `cdd-kit validate` passed after promotion. `cdd-kit context-scan` re-run to update hot context indexes.

## Follow-up Work

- **Phase 1a**: `/cdd-new migrate core/ utilities and API layer to TypeScript` — migrate all 21 files in `frontend/src/core/` from `.js` to `.ts`.
- **Gate promotion**: After 20 days / 60 runs / ≥95% pass, promote `frontend-type-check` from informational to required per `ci-gates.md` promotion policy.
- **postcss CVE**: `postcss@8.5.6` moderate CVE (GHSA-qx2v-qp2m-jg93) — pre-existing, fix separately.
