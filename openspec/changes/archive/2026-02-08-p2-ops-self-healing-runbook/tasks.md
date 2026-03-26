## 1. Conda/Systemd Contract Alignment

- [x] 1.1 Centralize runtime path configuration consumed by service units, watchdog, and scripts.
- [x] 1.2 Add startup validation that fails fast on conda path drift.
- [x] 1.3 Update systemd/watchdog integration tests for consistent runtime contract.

## 2. Worker Self-Healing Policy

- [x] 2.1 Implement bounded auto-restart policy (cooldown, retry budget, churn window).
- [x] 2.2 Add guarded mode behavior when churn threshold is exceeded.
- [x] 2.3 Implement authenticated manual override flow with explicit logging context.

## 3. Alerting and Operational Signals

- [x] 3.1 Expose policy-state fields in health/admin payloads (`allowed`, `cooldown`, `blocked`).
- [x] 3.2 Add structured audit events for restart decisions and override actions.
- [x] 3.3 Define alert thresholds and wire monitoring-friendly fields for pool/circuit/churn conditions.

## 4. Validation and Runbook Delivery

- [x] 4.1 Add tests for policy transitions, guarded mode, and override behavior.
- [x] 4.2 Validate single-port continuity during controlled recovery and hot reload paths.
- [x] 4.3 Update README/README.mdj and deployment runbook with verified operational procedures.
