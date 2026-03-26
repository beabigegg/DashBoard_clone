## ADDED Requirements

### Requirement: Card styling SHALL be consolidated to shared-ui
Duplicate card CSS class definitions across feature CSS files SHALL be removed in favor of the canonical `SectionCard` component and `ui-section-card` class.

#### Scenario: No duplicate card class in resource-shared
- **WHEN** `resource-shared/styles.css` is reviewed
- **THEN** locally defined `.section-card` / `.section-inner` / `.section-title` classes that duplicate `ui-section-card` behavior SHALL be removed or refactored to extend the shared class

#### Scenario: No duplicate card class in hold-overview
- **WHEN** `hold-overview/style.css` is reviewed
- **THEN** locally defined `.card` / `.card-header` / `.card-body` classes that duplicate `ui-card` behavior SHALL be removed or refactored

### Requirement: MultiSelect styles SHALL be scoped within the component
All `.multi-select` related CSS rules SHALL be moved from feature CSS files into the `MultiSelect.vue` component's `<style scoped>` block.

#### Scenario: No multi-select styles in resource-shared
- **WHEN** searching for `.multi-select` in `resource-shared/styles.css`
- **THEN** zero standalone `.multi-select` class definitions SHALL remain (only theme-specific overrides allowed)

### Requirement: Loading component styles SHALL not be duplicated
Feature CSS files SHALL NOT define `.loading-overlay` or `.loading-spinner` classes that duplicate the shared-ui components.

#### Scenario: No duplicate loading styles
- **WHEN** searching for `.loading-overlay` or `.loading-spinner` in `resource-shared/styles.css` and `wip-shared/styles.css`
- **THEN** duplicate definitions that replicate `LoadingOverlay.vue` / `LoadingSpinner.vue` behavior SHALL be removed

### Requirement: Error banner styles SHALL be consolidated
Feature CSS files SHALL use the shared `ErrorBanner` component (from Phase 5) instead of locally defined `.error-banner` classes.

#### Scenario: Gradual replacement
- **WHEN** a feature page is modified
- **THEN** local `<p class="error-banner">` usages SHALL be replaced with the `ErrorBanner` component
- **THEN** the corresponding local `.error-banner` CSS definitions SHALL be removed

### Requirement: Token hex references SHALL migrate to semantic tokens
Direct `token.hXXXXXX` hex color references SHALL be progressively replaced with semantic token paths (brand, state, text, surface).

#### Scenario: New code prohibition
- **WHEN** new CSS rules are added
- **THEN** `theme('colors.token.hXXXXXX')` references SHALL NOT be introduced
- **THEN** semantic token paths SHALL be used instead

#### Scenario: Existing code migration
- **WHEN** a feature CSS file is modified for other reasons
- **THEN** `token.hXXXXXX` references in the modified file SHOULD be migrated to semantic equivalents where the mapping is clear
