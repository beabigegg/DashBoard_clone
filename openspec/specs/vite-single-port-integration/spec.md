## Purpose
Define stable requirements for vite-single-port-integration.

## Requirements


### Requirement: Frontend Build SHALL Use Vite With Flask Static Output
The system SHALL use Vite to build frontend assets and output artifacts into Flask static directories served by the backend.

#### Scenario: Build asset generation
- **WHEN** frontend build is executed
- **THEN** Vite SHALL generate portal-related JS/CSS artifacts into the backend static output path

### Requirement: Deployment SHALL Preserve Single External Port
The system SHALL preserve single-port external serving through Flask/Gunicorn.

#### Scenario: Production serving mode
- **WHEN** the system runs in deployment mode
- **THEN** frontend assets SHALL be served through Flask on the same external port as API/page routes
