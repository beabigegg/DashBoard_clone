# Full Modernization Architecture Blueprint Artifacts

This directory stores execution artifacts for `full-modernization-architecture-blueprint`.

## Core Governance

- `route_scope_matrix.json`: frozen in-scope/deferred route contract matrix.
- `governance_milestones.md`: completion and deprecation milestones.
- `exception_registry.json`: approved temporary exceptions with owner and milestone.
- Policy artifact runtime cache model:
  - `src/mes_dashboard/core/modernization_policy.py` caches `route_scope_matrix.json` and
    `asset_readiness_manifest.json` in-process with `lru_cache`.
  - Runtime behavior is restart-refresh by default: JSON edits take effect after worker restart.
  - Controlled refresh is available through `clear_modernization_policy_cache()` for tests or
    explicit maintenance hooks; no automatic file watcher/hot reload is active in production.

## Content Modernization Safety

- `page_content_manual_acceptance_checklist.md`: mandatory manual sign-off checklist.
- `known_bug_baseline.json`: route-level known bug baseline and replay blocking policy.

## Rollout Operations

- `rollout_runbook.md`: phase steps and hold points.
- `rollback_controls.md`: rollback and false-positive gate handling.
- `observability_checkpoints.md`: route/gate/rollback observability contract.
- `deferred_route_handoff.md`: explicit handoff package to deferred-route follow-up change.
