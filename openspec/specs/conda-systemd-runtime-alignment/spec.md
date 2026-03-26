# conda-systemd-runtime-alignment Specification

## Purpose
TBD - created by archiving change stability-and-frontend-compute-shift. Update Purpose after archive.
## Requirements
### Requirement: Production Service Runtime SHALL Use Conda-Aligned Execution Paths
Service units and operational scripts MUST run with a consistent conda-managed Python runtime.

#### Scenario: Service unit starts application
- **WHEN** systemd starts the dashboard service and watchdog
- **THEN** both processes MUST execute using the configured conda environment binaries and paths

### Requirement: Watchdog and Runtime Paths MUST Be Operationally Consistent
PID files, restart flag paths, state files, and worker control interfaces SHALL be consistent across scripts, environment variables, and systemd units.

#### Scenario: Watchdog handles restart flag
- **WHEN** a restart flag is written by admin control endpoints
- **THEN** watchdog MUST read the same configured path set and signal the correct Gunicorn master process

### Requirement: Deployment Documentation MUST Match Runtime Contract
Runbooks and deployment documentation MUST describe the same conda/systemd/watchdog contract used by the deployed system.

#### Scenario: Operator follows deployment runbook
- **WHEN** an operator performs deploy, health check, and rollback from documentation
- **THEN** documented commands and paths MUST work without requiring venv-specific assumptions

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

