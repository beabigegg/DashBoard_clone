# `frame_id` / `tool_src` Deprecation Plan

## Status

- Retirement completed in this change.
- Runtime navigation payload generation no longer emits:
  - `frame_id`
  - `tool_src`

## Context

Frame-era fields were used for iframe loading compatibility:

- `frame_id`
- `tool_src`

## Policy

Deprecation is phased and must not break active routes.

## Phases

1. **Compatibility phase**:
   - Keep fields in payload.
   - Ensure new router navigation logic does not rely on these fields.
2. **Dual-run phase**:
   - Validate all navigation paths without frame fields.
3. **Retirement readiness**:
   - Wrapper-first pages are stable in shell.
   - Cutover gates G1~G7 are green in rehearsal.
4. **Removal phase**:
   - Remove generation and downstream usage of `frame_id/tool_src`.
   - Update related tests and docs.

## Removal Checkpoints

- Checkpoint A: drawer parity stable in canary.
- Checkpoint B: legacy wrappers stable with no frame-field dependency.
- Checkpoint C: rollback mechanism verified independent of frame fields. ✓

## Risk Controls

- Keep rollback-safe path via route-level navigation and kill-switch.
- Keep gate coverage for route/drawer/workflow parity after field removal.
