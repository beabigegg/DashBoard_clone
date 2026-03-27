## ADDED Requirements

### Requirement: RQ workers SHALL use an independently injected Oracle pool configuration
Each RQ worker process SHALL use a smaller Oracle pool configuration than gunicorn workers.

#### Scenario: Effective env names
- **WHEN** an RQ worker starts
- **THEN** `start_server.sh` SHALL inject the env names that the runtime actually reads
- **THEN** with the current runtime, that means `DB_POOL_SIZE` and `DB_MAX_OVERFLOW`

#### Scenario: Optional RQ-specific aliases
- **WHEN** the project wants `RQ_DB_*` aliases
- **THEN** the runtime config loader SHALL be updated accordingly before those names are documented
