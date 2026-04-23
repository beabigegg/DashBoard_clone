## ADDED Requirements

### Requirement: Hold History SummaryCards SHALL expose released vs on-hold averages and maximums

The SummaryCards row SHALL display separate real-average and real-maximum hold-duration cards for released and still-on-hold lots, replacing the single bucket-weighted estimate.

#### Scenario: SummaryCards shows averages and maximums

- **WHEN** the Hold History page renders SummaryCards with a successful dataset
- **THEN** the cards row SHALL include:
  - "已解除平均時長" bound to `summary.avgReleasedHours` (from duration payload, format `duration`, sub `hr`)
  - "持續 Hold 平均時長" bound to `summary.avgOnHoldHours` (from duration payload, format `duration`, sub `hr`)
  - "已解除最長時長" bound to `summary.maxReleasedHours` (from duration payload, format `duration`, sub `hr`)
  - "持續 Hold 最長時長" bound to `summary.maxOnHoldHours` (from duration payload, format `duration`, sub `hr`)
- **AND** the previous single "平均 Hold 時長" card SHALL be removed
- **AND** `SummaryCardGroup` columns count SHALL be adjusted to accommodate all cards while keeping a readable layout on 1920+ screens

#### Scenario: Average and maximum cards handle empty result sets

- **WHEN** any of `avgReleasedHours` / `avgOnHoldHours` / `maxReleasedHours` / `maxOnHoldHours` equals 0 because no rows match
- **THEN** each respective card SHALL render `0` (or a placeholder agreed with UI review) via `format="duration"` without breaking the layout

### Requirement: Hold History frontend SHALL remove bucket-weighted average estimate

The frontend SHALL source hold-duration averages and maximums from the API response, and SHALL NOT locally derive them from bucket midpoints.

#### Scenario: No bucket-midpoint estimation remains

- **WHEN** the Hold History page source is inspected
- **THEN** the `estimateAvgHoldHours()` function SHALL NOT exist in `frontend/src/hold-history/App.vue`
- **AND** the computed `summary` object SHALL source all four average/maximum values from `durationData.value`, not from `durationData.value.items`

#### Scenario: DuckDB-WASM local-compute path produces matching values

- **WHEN** the page runs in client-side DuckDB compute mode (`useHoldHistoryDuckDB.computeView`)
- **THEN** the local `queryDuration()` SHALL also compute all four values (`avgReleasedHours`, `avgOnHoldHours`, `maxReleasedHours`, `maxOnHoldHours`) using the same filter conditions as the bucket query
- **AND** the returned duration object SHALL include all four fields with the same shape as the server response

### Requirement: Hold History SummaryCards SHALL include a quality repeat-hold indicator

A "品質重複觸發" card SHALL display the stable quality re-hold count that is independent of `FUTUREHOLDCOMMENTS` content mutation.

#### Scenario: Quality repeat-hold card is visible

- **WHEN** the Hold History page renders SummaryCards with a successful dataset
- **THEN** the cards row SHALL include a "品質重複觸發" card bound to `summary.repeatQualityHoldQty` (format `number`)
- **AND** the value SHALL be the sum of daily `repeatQualityHoldQty` from the trend payload across the query range
- **AND** the card SHALL be positioned adjacent to "累計 Future Hold" for semantic comparison

#### Scenario: Card provides contextual label

- **WHEN** the user hovers or focuses the "品質重複觸發" card
- **THEN** an inline help text (or aria-label) SHALL explain: "同工單同原因的 quality Hold 再次發生總量（基於歷史重複推斷，不依賴 FutureHold 備註，值不會衰減）"

### Requirement: Hold History Future Hold card SHALL document its time-decay semantics

The existing "累計 Future Hold" card SHALL remain but SHALL expose a tooltip that explains the decay behavior observed when MES clears `FUTUREHOLDCOMMENTS` on release.

#### Scenario: Future Hold card tooltip is available

- **WHEN** the user hovers or focuses the "累計 Future Hold" card
- **THEN** a tooltip (or equivalent accessible affordance) SHALL be shown explaining:
  - The card counts holds where `FUTUREHOLDCOMMENTS IS NOT NULL AND RN_FUTURE_REASON > 1` (matching PJMES043 original logic)
  - Values for historical days may shrink over time because MES can clear `FUTUREHOLDCOMMENTS` after release
  - For a stable re-hold indicator, users should refer to "品質重複觸發"
- **AND** the tooltip content SHALL be sourced from i18n messages for future localization
