## MODIFIED Requirements

### Requirement: Lineage admission guards SHALL be retired only after lineage is fully spool-safe
The removal of `LINEAGE_MAX_SEED_COUNT` and `LINEAGE_RSS_REJECT_MB` SHALL be gated by the retirement of the legacy heavy sync path.

#### Scenario: Legacy lineage path still callable
- **WHEN** a compatibility path can still execute large lineage work in-process
- **THEN** the corresponding admission guards SHALL remain

#### Scenario: Full RQ/spool migration complete
- **WHEN** all heavy lineage execution is guaranteed to run in RQ with spool-backed output
- **THEN** the legacy seed-count and RSS rejection guards MAY be removed
