## ADDED Requirements

### Requirement: Major Pages SHALL be Managed by Vite Modules
The system SHALL provide Vite-managed module entries for major portal pages, replacing inline scripts in a phased manner.

#### Scenario: Portal module loading
- **WHEN** the portal page is rendered
- **THEN** it MUST load its behavior from a Vite-built module asset when available

#### Scenario: Page module fallback
- **WHEN** a required Vite asset is unavailable
- **THEN** the system MUST keep page behavior functional through explicit fallback logic

### Requirement: Build Pipeline SHALL Produce Backend-Served Assets
Vite build output MUST be emitted into backend static paths and served by Flask/Gunicorn on the same origin.

#### Scenario: Build artifact placement
- **WHEN** frontend build is executed
- **THEN** generated JS/CSS files SHALL be written to the configured backend static dist directory
