## Purpose
Define stable requirements for full-vite-page-modularization.
## Requirements
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

### Requirement: Vite Page Modules SHALL Reuse Shared Chart and Query Building Blocks
Page entry modules MUST consume shared chart/query/drawer utilities for common behaviors.

#### Scenario: Common chart behavior across pages
- **WHEN** multiple report pages render equivalent chart interactions
- **THEN** the behavior MUST be provided by shared Vite modules rather than duplicated page-local implementations

### Requirement: Modularization MUST Preserve Established Navigation and Drill-Down Semantics
Refactoring into Vite modules SHALL not alter existing page transitions, independent tabs, and drill-down entry points.

#### Scenario: User follows existing drill-down path
- **WHEN** the user navigates from summary page to detail views
- **THEN** the resulting flow and parameter semantics MUST match the established baseline behavior

### Requirement: Module Boundaries SHALL Support Frontend Compute Expansion
Vite module structure MUST keep compute logic decoupled from DOM wiring so additional backend-to-frontend computation shifts can be added safely.

#### Scenario: Adding a new frontend-computed metric
- **WHEN** a new metric is migrated from backend to frontend
- **THEN** the metric logic MUST be integrated through shared compute modules without rewriting page routing structure

### Requirement: WIP Report Pages SHALL Be Served by Vite Modules
The system SHALL provide Vite entry bundles for WIP overview and WIP detail pages, with template-level asset resolution.

#### Scenario: WIP module asset available
- **WHEN** the built asset exists in backend static dist
- **THEN** the page MUST load behavior from the corresponding Vite module entry

#### Scenario: WIP module asset unavailable
- **WHEN** the built asset is not present
- **THEN** the page MUST retain equivalent behavior through explicit inline fallback logic

### Requirement: Vite Modules MUST Preserve Legacy Handler Compatibility
Vite report modules SHALL expose required global handlers for existing inline entry points until event wiring is fully migrated.

#### Scenario: Inline-triggered handler compatibility
- **WHEN** a template control invokes existing global handler names
- **THEN** the migrated module MUST provide compatible callable handlers without runtime scope errors

### Requirement: Hold Detail Page SHALL Be Served by a Vite Module
The system SHALL provide a dedicated Vite entry bundle for the hold-detail report page.

#### Scenario: Hold-detail module asset exists
- **WHEN** `/hold-detail` is rendered and `hold-detail.js` exists in static dist
- **THEN** the page MUST load behavior from the Vite module entry

#### Scenario: Hold-detail module asset missing
- **WHEN** `/hold-detail` is rendered and the module asset is unavailable
- **THEN** the page MUST remain operational through explicit inline fallback logic

### Requirement: WIP Modules SHALL Reuse Shared Autocomplete and Filter Query Utilities
WIP overview and WIP detail Vite entry modules SHALL use shared frontend core utilities for autocomplete request construction and cross-filter behavior.

#### Scenario: Cross-filter autocomplete parity across WIP pages
- **WHEN** users type in workorder/lot/package/type filters on either WIP overview or WIP detail pages
- **THEN** both pages MUST generate equivalent autocomplete request parameters and return behaviorally consistent dropdown results

#### Scenario: Shared utility change propagates across both pages
- **WHEN** autocomplete mapping rules are updated in the shared core module
- **THEN** both WIP overview and WIP detail modules MUST consume the updated behavior without duplicated page-local logic edits
