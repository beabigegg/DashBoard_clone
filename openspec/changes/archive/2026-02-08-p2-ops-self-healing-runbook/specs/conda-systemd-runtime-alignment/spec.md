## ADDED Requirements

### Requirement: Runtime Path Drift SHALL Be Detectable Before Service Start
Service startup checks MUST validate configured conda runtime paths across app, watchdog, and worker control scripts.

#### Scenario: Conda path mismatch detected
- **WHEN** startup validation finds runtime path inconsistency between configured units and scripts
- **THEN** service start MUST fail with actionable diagnostics instead of running with partial mismatch

### Requirement: Conda/Systemd Contract SHALL Be Versioned in Operations Docs
The documented runtime contract MUST include versioned path assumptions and verification commands.

#### Scenario: Operator verifies deployment contract
- **WHEN** operator follows runbook validation steps
- **THEN** commands MUST confirm active runtime paths match documented conda/systemd contract
