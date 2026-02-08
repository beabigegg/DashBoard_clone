## Why

Operations stability still depends heavily on manual intervention when workers degrade or pools saturate. We need a formal operations phase to align conda/systemd runtime contracts and add controlled self-healing with guardrails, so recovery is faster without triggering restart storms.

## What Changes

- Standardize conda-based runtime paths across app service, watchdog, and operational scripts from a single source of truth.
- Introduce guarded worker self-healing policy (cooldown, churn windows, bounded retries, manual override).
- Add alert thresholds and machine-readable recovery signals for pool pressure, circuit-open persistence, and restart churn.
- Harden runbook documentation and scripts for deterministic restart, rollback, and incident triage.

## Capabilities

### New Capabilities
- `worker-self-healing-governance`: Define safe autonomous recovery behavior with anti-storm guardrails.

### Modified Capabilities
- `conda-systemd-runtime-alignment`: Extend runtime consistency requirements with startup validation and drift detection.
- `runtime-resilience-recovery`: Add auditable recovery-action requirements for automated and operator-triggered restart flows.

## Impact

- Affected code:
  - `deploy/systemd/*.service`
  - `scripts/worker_watchdog.py`
  - `src/mes_dashboard/routes/admin_routes.py`
  - `src/mes_dashboard/routes/health_routes.py`
  - `src/mes_dashboard/core/database.py`
  - `src/mes_dashboard/core/circuit_breaker.py`
  - `tests/`
  - `README.md`, `README.mdj`, runbook docs
- APIs:
  - `/health`
  - `/health/deep`
  - `/admin/api/system-status`
  - `/admin/api/worker/status`
  - `/admin/api/worker/restart`
- Operational behavior:
  - Preserve single-port bind model.
  - Add controlled self-healing policy and clearer alert thresholds.
