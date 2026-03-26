## MODIFIED Requirements

### Requirement: Unified MultiSelect component
The system SHALL provide a single `MultiSelect` component at `shared-ui/components/MultiSelect.vue`, merging functionality from `resource-shared/components/MultiSelect.vue` and `mid-section-defect/components/MultiSelect.vue`.

#### Scenario: Component location
- **WHEN** any page imports MultiSelect
- **THEN** the import path SHALL be from `shared-ui/components/MultiSelect.vue`

#### Scenario: Loading state indicator in trigger
- **WHEN** the `loading` prop is `true`
- **THEN** a small spinner icon SHALL be displayed inside the trigger button
- **THEN** the trigger button SHALL be disabled

#### Scenario: SVG chevron with animation
- **WHEN** the dropdown opens
- **THEN** an SVG chevron icon SHALL rotate 180 degrees with a CSS transition
- **WHEN** the dropdown closes
- **THEN** the chevron SHALL rotate back to 0 degrees
- **THEN** no unicode `▲` or `▼` characters SHALL be used

#### Scenario: Styles scoped within component
- **WHEN** MultiSelect styling is needed
- **THEN** base `.multi-select` styles SHALL be defined in the component's `<style scoped>` block
- **THEN** feature CSS files SHALL only contain theme-specific overrides scoped under their theme root class
