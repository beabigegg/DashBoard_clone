## ADDED Requirements

### Requirement: ui-btn base class
The system SHALL define `.ui-btn` as the base button class providing shared styles: font, padding, border-radius, cursor, transition using motion tokens, and disabled state.

#### Scenario: Base button renders correctly
- **WHEN** an element has class `ui-btn`
- **THEN** it SHALL display with consistent font, padding, rounded corners, and `transition: all var(--motion-normal) var(--motion-ease)`

### Requirement: ui-btn--primary variant
The system SHALL define `.ui-btn--primary` providing the brand gradient background, white text, and hover shadow + lift effect.

#### Scenario: Primary button hover
- **WHEN** a user hovers over a `.ui-btn--primary` element
- **THEN** it SHALL show a box-shadow and `transform: var(--hover-lift)`

### Requirement: ui-btn--ghost variant
The system SHALL define `.ui-btn--ghost` providing transparent background, border, and hover background fill.

#### Scenario: Ghost button hover
- **WHEN** a user hovers over a `.ui-btn--ghost` element
- **THEN** the background SHALL fill with a subtle color

### Requirement: ui-btn--sm size modifier
The system SHALL define `.ui-btn--sm` providing reduced padding and font-size for compact contexts.

#### Scenario: Small button sizing
- **WHEN** an element has classes `ui-btn ui-btn--sm`
- **THEN** it SHALL render smaller than the default `.ui-btn`

### Requirement: ui-btn loading state
The system SHALL support `.ui-btn.is-loading` which disables pointer events, reduces opacity, and shows an inline `LoadingSpinner` inside the button.

#### Scenario: Button loading state
- **WHEN** a button has class `is-loading`
- **THEN** pointer-events SHALL be `none`, opacity SHALL be reduced, and an inline spinner SHALL be visible

### Requirement: Legacy button classes removed
The system SHALL NOT contain `.btn-primary`, `.btn-secondary`, `.btn`, or any non-`ui-` prefixed button class definitions. All usages across all pages SHALL be replaced.

#### Scenario: No legacy classes in codebase
- **WHEN** running `grep -r "\.btn-primary\b" frontend/src/ --include="*.css" --include="*.vue"`
- **THEN** zero matches SHALL be returned
