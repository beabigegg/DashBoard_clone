## ADDED Requirements

### Requirement: ERP-to-Reject linkage SHALL use a canonical key contract
The linkage layer SHALL map ERP yield records to Reject History records using canonical keys derived from business semantics.

#### Scenario: Canonical linkage key
- **WHEN** linkage is computed for ERP alert/detail records
- **THEN** canonical key SHALL include `date_bucket`, `workorder`, and normalized `reason_code`
- **THEN** linkage output SHALL preserve source and target key values for auditability

#### Scenario: Deterministic key generation
- **WHEN** the same source record is processed repeatedly
- **THEN** canonical key generation SHALL produce the same output key
- **THEN** linkage result SHALL be reproducible under unchanged source data

### Requirement: Linkage SHALL normalize reason codes before matching
The linkage layer SHALL apply standardized normalization to reason code/text variants before key comparison.

#### Scenario: Standard reason code normalization
- **WHEN** reason value contains format variants (spacing, punctuation, case, localized prefix)
- **THEN** normalization SHALL transform it into configured canonical code
- **THEN** matching SHALL run on canonical code instead of raw source text

#### Scenario: Unknown reason value
- **WHEN** reason value cannot be normalized to known canonical mapping
- **THEN** linkage SHALL mark the record as `unmapped_reason`
- **THEN** linkage metrics SHALL include this record in unmatched statistics

### Requirement: Linkage SHALL expose match quality and coverage metrics
The linkage service SHALL return machine-readable indicators so UI and API can show confidence and residual gaps.

#### Scenario: Match-quality output
- **WHEN** linkage query completes
- **THEN** response SHALL include counts for `matched`, `unmatched`, and `partially_matched` records
- **THEN** response SHALL include matched and unmatched scrap quantity totals

#### Scenario: Threshold warning signal
- **WHEN** unmatched ratio exceeds configured threshold for requested window
- **THEN** linkage response SHALL include a warning flag and reason code
- **THEN** consumer APIs/pages SHALL be able to surface the warning without custom parsing

### Requirement: Linkage SHALL support drilldown payload contract
The linkage layer SHALL provide normalized payload fields required by Reject History drilldown.

#### Scenario: Drilldown payload generation
- **WHEN** an alert row requests drilldown payload
- **THEN** linkage SHALL return normalized filter payload compatible with Reject History API fields
- **THEN** payload SHALL include explicit indicator of match status (`exact`, `partial`, `none`)

#### Scenario: No exact match fallback
- **WHEN** no exact target rows are found for canonical key
- **THEN** linkage SHALL return nearest supported fallback payload using available key subsets
- **THEN** fallback reason SHALL be included in response metadata
