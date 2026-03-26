## ADDED Requirements

### Requirement: Runtime Resilience Diagnostics MUST Expose Actionable Signals
The system MUST expose machine-readable resilience thresholds, restart-churn indicators, and operator action recommendations so degraded states can be triaged consistently.

#### Scenario: Health payload includes resilience diagnostics
- **WHEN** clients call `/health` or `/health/deep`
- **THEN** responses MUST include resilience thresholds and a recommendation field describing whether to observe, throttle, or trigger controlled worker recovery

#### Scenario: Admin status includes restart churn summary
- **WHEN** operators call `/admin/api/system-status` or `/admin/api/worker/status`
- **THEN** responses MUST include bounded restart history summary within a configured time window and indicate whether churn threshold is exceeded
