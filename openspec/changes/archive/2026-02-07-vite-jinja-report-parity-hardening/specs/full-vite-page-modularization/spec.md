## ADDED Requirements

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
