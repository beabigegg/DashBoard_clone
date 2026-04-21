## ADDED Requirements

### Requirement: Equipment tab URL state SHALL restore active UI state after reload
When the Query Tool URL encodes equipment-tab state, the page SHALL restore that
state on initial load and hard reload so the visible active tab, controls, and
accessibility semantics match the URL.

#### Scenario: Hard reload restores equipment tab active state
- **WHEN** the browser loads Query Tool with `tab=equipment` in the URL
- **THEN** the equipment tab SHALL render as the active tab
- **THEN** the equipment tab button SHALL expose `aria-current="page"`

#### Scenario: Hard reload restores date filters on equipment tab
- **WHEN** the browser reloads Query Tool with equipment date params in the URL
- **THEN** the equipment tab date inputs SHALL be restored from those params
- **THEN** the restored filters SHALL match the values encoded in the URL

#### Scenario: Invalid or missing tab param falls back safely
- **WHEN** the Query Tool page loads without a valid tab param
- **THEN** the page SHALL fall back to the default tab state without throwing
- **THEN** no equipment-tab `aria-current` state SHALL be rendered unless the
  active tab is actually equipment

