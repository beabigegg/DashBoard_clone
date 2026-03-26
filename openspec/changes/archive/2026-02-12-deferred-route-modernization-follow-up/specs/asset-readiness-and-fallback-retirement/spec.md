## MODIFIED Requirements

### Requirement: Deferred-route assets SHALL be release-ready before promotion
Deferred routes SHALL adopt release-time asset-readiness checks and SHALL fail promotion when required assets are missing.

#### Scenario: Deferred-route readiness validation
- **WHEN** release artifacts are prepared for follow-up phase promotion
- **THEN** required assets for `/tables`, `/excel-query`, `/query-tool`, and `/mid-section-defect` SHALL be validated
- **THEN** missing required assets SHALL fail release gating

### Requirement: Deferred-route runtime fallback SHALL be retired by governed policy
Deferred routes SHALL not remain on runtime fallback posture after follow-up modernization completion criteria are met.

#### Scenario: Deferred-route fallback retirement
- **WHEN** a deferred route passes readiness + parity + manual acceptance gates
- **THEN** runtime fallback posture for that route SHALL be retired according to milestone policy
- **THEN** rollback control SHALL remain available via explicit route-level governance switch

