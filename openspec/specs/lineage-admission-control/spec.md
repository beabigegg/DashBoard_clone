# lineage-admission-control Specification

## Purpose
Define admission control guards for LineageEngine to prevent OOM from unbounded seed inputs.
## Requirements
### Requirement: LineageEngine SHALL enforce seed count hard limit
`resolve_full_genealogy()` and `resolve_forward_tree()` SHALL reject inputs exceeding `LINEAGE_MAX_SEED_COUNT`.

#### Scenario: Seed count exceeds hard limit
- **WHEN** `resolve_full_genealogy()` or `resolve_forward_tree()` is called with `len(container_ids) > LINEAGE_MAX_SEED_COUNT` (default 80,000)
- **THEN** the method SHALL raise `ValueError` with message including the seed count and limit
- **THEN** no Oracle queries SHALL be executed

#### Scenario: Seed count within limit
- **WHEN** `resolve_full_genealogy()` is called with `len(container_ids) <= LINEAGE_MAX_SEED_COUNT`
- **THEN** execution SHALL proceed normally (existing behavior)

#### Scenario: Limit configurable via environment
- **WHEN** `LINEAGE_MAX_SEED_COUNT` environment variable is set
- **THEN** the hard limit SHALL use the configured value
- **THEN** the default SHALL be 80,000

### Requirement: LineageEngine SHALL check RSS before execution
`resolve_full_genealogy()` and `resolve_forward_tree()` SHALL check process RSS before starting heavy computation.

#### Scenario: RSS exceeds threshold
- **WHEN** `process_rss_mb()` returns a value exceeding `LINEAGE_RSS_REJECT_MB` (default 900)
- **THEN** the method SHALL raise `MemoryError` with message indicating current RSS and limit
- **THEN** no Oracle queries SHALL be executed

#### Scenario: RSS within threshold
- **WHEN** `process_rss_mb()` returns a value below `LINEAGE_RSS_REJECT_MB`
- **THEN** execution SHALL proceed normally

#### Scenario: RSS check unavailable
- **WHEN** `process_rss_mb()` returns None (platform not supported)
- **THEN** the RSS check SHALL be skipped (fail-open)

### Requirement: LineageEngine SHALL log progress for large inputs
`resolve_split_ancestors()` SHALL log progress when processing large batch counts.

#### Scenario: Progress logging for large input
- **WHEN** `resolve_split_ancestors()` processes more than 5 Oracle batches (>5000 input CIDs)
- **THEN** it SHALL log an INFO message after every 5 batches with completed/total count
- **THEN** it SHALL log a summary on completion with total seeds, edges, and names discovered

#### Scenario: Small input no extra logging
- **WHEN** `resolve_split_ancestors()` processes 5 or fewer Oracle batches
- **THEN** the existing summary logging SHALL be sufficient (no per-batch logging)

### Requirement: Lineage admission guards SHALL be retired only after lineage is fully spool-safe
The removal of `LINEAGE_MAX_SEED_COUNT` and `LINEAGE_RSS_REJECT_MB` SHALL be gated by the retirement of the legacy heavy sync path.

#### Scenario: Legacy lineage path still callable
- **WHEN** a compatibility path can still execute large lineage work in-process
- **THEN** the corresponding admission guards SHALL remain

#### Scenario: Full RQ/spool migration complete
- **WHEN** all heavy lineage execution is guaranteed to run in RQ with spool-backed output
- **THEN** the legacy seed-count and RSS rejection guards MAY be removed
