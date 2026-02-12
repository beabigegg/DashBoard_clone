## Context

This follow-up change consumes the explicit handoff from `full-modernization-architecture-blueprint` phase 1. Deferred routes were intentionally excluded to control blast radius, but they now represent the remaining architecture gap.

Current deferred-route risks:
- Shell contract incompleteness and mixed navigation behavior.
- Legacy runtime fallback dependency.
- Content modernization parity not yet formalized.
- Potential legacy bug carry-over if migration is done implementation-first.

## Goals / Non-Goals

**Goals**
- Complete shell-governed route coverage for deferred routes.
- Adopt canonical shell routing and explicit compatibility policy.
- Execute contract-first content modernization with parity and rollback controls.
- Enforce mandatory manual acceptance and BUG revalidation before sign-off.

**Non-Goals**
- Reworking already in-scope phase-1 routes again.
- Changing backend business data semantics beyond compatibility safeguards.
- Bundling unrelated admin/report features into this follow-up.

## Decisions

### D1. Deferred routes are promoted to in-scope as a single governed wave
- `/tables`, `/excel-query`, `/query-tool`, `/mid-section-defect` are all in-scope for this change.

### D2. Canonical policy matches phase 1
- Canonical shell path is `/portal-shell/<route>`.
- Direct entry behavior remains explicit compatibility (redirect or compatibility render) with preserved query semantics.

### D3. Content migration remains route-by-route, not big-bang
- Only one deferred route can be in cutover state at a time.
- Next route is blocked until current route has parity pass + manual sign-off + bug replay pass.

### D4. Legacy bug carry-over prevention is a hard gate
- Known bug baseline must be recorded before implementation.
- Reproduced known bugs on modernized path block sign-off and legacy retirement.

## Risks / Trade-offs

- Deferred routes may have heavier legacy coupling than phase-1 routes.
- Route-by-route cutover increases total elapsed time but reduces rollback blast radius.
- Asset-readiness enforcement can block releases earlier; rollout plan must phase warn->block.

## Migration Plan

1. Freeze deferred-route scope matrix for this follow-up change.
2. Extend shell route contracts and metadata coverage to full completeness.
3. Define route content contracts + golden fixtures + interaction parity checks.
4. Execute per-route migration with feature-flagged cutover and manual acceptance.
5. Retire deferred-route runtime fallback posture after acceptance and readiness gates pass.
6. Update runbook/rollback docs and close handoff linkage.

## Rollback Strategy

- Keep route-scoped cutover flags for immediate per-route rollback.
- Allow temporary gate downgrade (`block` -> `warn`) only with explicit waiver and expiry.
- Preserve route-level evidence (parity, manual sign-off, bug replay) to support rollback decisions.
