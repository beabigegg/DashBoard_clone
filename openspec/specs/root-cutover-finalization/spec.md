## Purpose
Define stable requirements for root-cutover-finalization.

## Requirements


### Requirement: Root Project SHALL be the Single Execution Target
The system SHALL run all application startup, test, and deployment workflows from `DashBoard_vite` root without requiring nested `DashBoard/` paths.

#### Scenario: Root startup script execution
- **WHEN** an operator runs start/deploy scripts from `DashBoard_vite` root
- **THEN** all referenced source/config/script paths MUST resolve inside root project structure

#### Scenario: Root test execution
- **WHEN** CI or local developer runs test commands from root
- **THEN** tests SHALL execute against root source tree and root config files

### Requirement: Reference Directory MUST Remain Non-Authoritative
`DashBoard/` SHALL be treated as reference-only and MUST NOT be required for production runtime.

#### Scenario: Runtime independence
- **WHEN** root application is started in an environment without `DashBoard/`
- **THEN** the application MUST remain functional for the defined migration scope
