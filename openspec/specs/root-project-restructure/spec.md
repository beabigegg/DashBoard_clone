## Purpose
Define stable requirements for root-project-restructure.

## Requirements


### Requirement: Root Directory SHALL be the Primary Executable Project
The system SHALL treat `DashBoard_vite` root directory as the primary executable project, while `DashBoard/` remains reference-only during migration.

#### Scenario: Running app from root
- **WHEN** a developer runs project scripts from `DashBoard_vite` root
- **THEN** the application startup flow SHALL resolve code and config from root project files

#### Scenario: Reference directory preserved
- **WHEN** migration is in progress
- **THEN** `DashBoard/` SHALL remain available for structure comparison and behavior verification
