## Context

Phase 1 modernization was completed and archived, but post-delivery review identified several hardening gaps across policy loading, fallback behavior consistency, feature-flag ergonomics, and route-governance drift detection. The gaps are cross-cutting: backend route hosts, frontend contract metadata, CI governance checks, and operator onboarding defaults.

Current risks include:
- shared mutable cached policy payloads via `lru_cache` return values,
- inconsistent retired-fallback 503 response surfaces between app routes and blueprint routes,
- local bootstrap failures caused by strict `.env.example` defaults,
- duplicated boolean feature-flag parsing with slightly different precedence logic,
- missing frontend/backend route-inventory cross-validation.

## Goals / Non-Goals

**Goals:**
- Make modernization policy loading deterministic, mutation-safe, and explicitly documented.
- Standardize retired-fallback error response behavior across all in-scope route hosts.
- Keep `.env.example` local-safe while documenting production hardening expectations.
- Centralize feature-flag resolution semantics in shared helpers.
- Enforce route-contract parity across backend artifacts and frontend shell contracts.
- Improve operational observability for legacy contract fallback loading.

**Non-Goals:**
- No new route migrations in this change.
- No redesign of shell navigation UX.
- No deferred-route modernization implementation (`/tables`, `/excel-query`, `/query-tool`, `/mid-section-defect`).
- No runtime hot-reload framework for all policy artifacts.

## Decisions

### Decision 1: Introduce shared feature-flag helpers for bool parsing and env/config precedence
- Choice: Add shared helpers (for example `parse_bool`, `resolve_bool_flag`) used by app/policy/runtime modules.
- Rationale: eliminates duplicated parsing and precedence drift.
- Alternative considered: keep local `_to_bool` and alignment-by-convention.
- Why not alternative: high regression risk from future divergence and incomplete audits.

### Decision 2: Protect cached policy payloads from cross-caller mutation
- Choice: keep internal cache, but return defensive copies to callers; document refresh semantics and expose explicit cache-clear helper for tests/controlled refresh points.
- Rationale: avoids shared-reference corruption without changing call sites.
- Alternative considered: return `MappingProxyType`.
- Why not alternative: nested list/dict payloads still remain mutable unless deeply frozen.

### Decision 3: Unify retired-fallback response generation
- Choice: move to a shared fallback-retirement response helper callable from both app-level and blueprint-level routes.
- Rationale: consistent status/template/body contract and easier testing.
- Alternative considered: leave blueprint-specific inline HTML responses.
- Why not alternative: inconsistent user/operator behavior and duplicated logic.

### Decision 4: Rebalance `.env.example` for safe local onboarding
- Choice: set strict modernization toggles to local-safe defaults and annotate production-recommended values inline.
- Rationale: avoid false-negative startup failures in local/test environments while preserving explicit production guidance.
- Alternative considered: keep strict defaults and require all local users to override manually.
- Why not alternative: unnecessary onboarding friction and frequent bootstrap failures.

### Decision 5: Add governance parity checks across frontend and backend route contracts
- Choice: extend governance checks/tests to compare backend route contract artifacts with frontend route inventory/scope metadata.
- Rationale: catches silent drift before release.
- Alternative considered: rely only on backend JSON consistency.
- Why not alternative: frontend contract drift can still break runtime behavior silently.

### Decision 6: Emit explicit warning when legacy contract source is used
- Choice: log warning when loader falls back from primary contract artifact to legacy path.
- Rationale: improves observability during migration tail.
- Alternative considered: silent fallback.
- Why not alternative: hard to detect stale-source dependency in production.

### Decision 7: Reduce unnecessary redirect hops in `/hold-detail` missing-reason flow
- Choice: when SPA shell mode is enabled, redirect directly to canonical shell overview path.
- Rationale: reduces redirect chain complexity and improves deterministic route tracing.
- Alternative considered: keep current two-hop behavior.
- Why not alternative: no benefit, adds trace/debug noise.

### Decision 8: Add token fallbacks for shell-dependent route styles
- Choice: where route-local CSS consumes shell variables, include fallback values in `var(--token, fallback)` form.
- Rationale: prevents degraded rendering when route is rendered outside shell variable scope.
- Alternative considered: assume shell-only render path.
- Why not alternative: fallback/compatibility entry paths still exist in this phase.

## Risks / Trade-offs

- [Risk] Shared helper refactor may alter existing truthy/falsey behavior in edge env values.
  - Mitigation: add unit tests covering canonical and malformed env values before replacing call sites.
- [Risk] Contract parity gate can fail current CI if artifacts are already drifted.
  - Mitigation: land parity test with synchronized artifacts in same change.
- [Risk] Defensive-copy strategy adds minor per-call overhead.
  - Mitigation: policy payloads are small and low-frequency; prioritize correctness over micro-optimization.
- [Risk] `.env.example` default changes may be interpreted as weaker production stance.
  - Mitigation: add explicit production recommendation comments next to each local-safe default.

## Migration Plan

1. Add shared feature-flag helpers and migrate existing bool parsing call sites.
2. Refactor modernization policy cache-return behavior to mutation-safe contract and document refresh semantics.
3. Introduce shared retired-fallback response helper and migrate hold-overview/hold-history/hold-detail route handlers.
4. Update `.env.example` defaults and production guidance comments.
5. Extend governance script/tests for frontend/backend route-contract parity.
6. Add warning log on legacy contract-source fallback.
7. Update `/hold-detail` missing-reason redirect to single-hop canonical target under SPA mode.
8. Add fallback values for QC-GATE shell-derived CSS variables.
9. Run targeted unit/integration/e2e + governance checks.

Rollback strategy:
- Changes are config/code-level and can be reverted by standard git rollback.
- If parity gate causes unexpected release blocking, gate can temporarily run in warning mode while drift is fixed in same release window.

## Open Questions

- Should policy cache refresh be strictly restart-based, or do we want an operator-triggered cache-clear hook in production later?
- Do we want a single centralized governance artifact as source-of-truth long-term, with generated frontend/backend contract outputs?
