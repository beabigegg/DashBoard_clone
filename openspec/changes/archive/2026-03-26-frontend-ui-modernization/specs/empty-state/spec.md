## ADDED Requirements

### Requirement: EmptyState SHALL support illustration and action slots

#### Scenario: Illustration slot
- **WHEN** `EmptyState` has a `#illustration` slot
- **THEN** it SHALL render the slot content above the message text
- **WHEN** no `#illustration` slot is provided
- **THEN** no illustration area SHALL be rendered (current behavior preserved)

#### Scenario: Action slot
- **WHEN** `EmptyState` has a `#action` slot
- **THEN** it SHALL render the slot content below the message text with `margin-top: 16px`
- **THEN** the action area SHALL be centered

#### Scenario: Backward compatibility
- **WHEN** `EmptyState` is used without new slots
- **THEN** it SHALL render identically to current behavior (message text only based on `type` prop)
