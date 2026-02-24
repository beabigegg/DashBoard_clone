## ADDED Requirements

### Requirement: FilterBar SHALL include station dropdown
FilterBar SHALL display a `<select>` dropdown populated from `GET /api/mid-section-defect/station-options` on mount. The dropdown SHALL default to '測試' and emit `station` via the `update-filters` mechanism.

#### Scenario: Station dropdown loads on mount
- **WHEN** the FilterBar component mounts
- **THEN** it SHALL fetch station options from the API and populate the dropdown with 12 workcenter groups
- **THEN** the default selection SHALL be '測試'

#### Scenario: Station selection updates filters
- **WHEN** user selects a different station
- **THEN** `update-filters` SHALL emit with the new `station` value

### Requirement: FilterBar SHALL include direction toggle
FilterBar SHALL display a toggle button group with two options: '反向追溯' (`backward`) and '正向追溯' (`forward`). Default SHALL be `backward`.

#### Scenario: Direction toggle switches direction
- **WHEN** user clicks '正向追溯'
- **THEN** `update-filters` SHALL emit with `direction: 'forward'`
- **THEN** the active button SHALL visually indicate the selected direction

### Requirement: KPI cards SHALL display direction-aware labels
KpiCards component SHALL accept `direction` and `stationLabel` props and switch card labels between backward and forward modes.

#### Scenario: Backward KPI labels
- **WHEN** `direction='backward'`
- **THEN** KPI cards SHALL display existing labels: 偵測批次數, 偵測不良數, 上游追溯批次數, 上游站點數, etc.

#### Scenario: Forward KPI labels
- **WHEN** `direction='forward'`
- **THEN** KPI cards SHALL display: 偵測批次數, 偵測不良數, 追蹤批次數, 下游到達站數, 下游不良總數, 下游不良率

### Requirement: Chart layout SHALL switch by direction
App.vue SHALL render direction-appropriate chart sets.

#### Scenario: Backward chart layout
- **WHEN** `direction='backward'`
- **THEN** SHALL render 6 Pareto charts: by_station, by_loss_reason, by_machine, by_detection_machine, by_workflow, by_package

#### Scenario: Forward chart layout
- **WHEN** `direction='forward'`
- **THEN** SHALL render 4 Pareto charts: by_downstream_station, by_downstream_loss_reason, by_downstream_machine, by_detection_machine

### Requirement: Detail table columns SHALL switch by direction
DetailTable component SHALL accept a `direction` prop and render direction-appropriate columns.

#### Scenario: Backward detail columns
- **WHEN** `direction='backward'`
- **THEN** columns SHALL match existing backward layout (CONTAINERID, station history, upstream machine attribution, etc.)

#### Scenario: Forward detail columns
- **WHEN** `direction='forward'`
- **THEN** columns SHALL include: CONTAINERID, 偵測設備, 偵測投入, 偵測不良, 下游到達站數, 下游不良總數, 下游不良率, 最差下游站

### Requirement: Page header SHALL reflect station and direction
Page title SHALL be '製程不良追溯分析'. Subtitle SHALL dynamically reflect station and direction.

#### Scenario: Backward subtitle
- **WHEN** `station='電鍍', direction='backward'`
- **THEN** subtitle SHALL indicate: `電鍍站不良 → 回溯上游機台歸因`

#### Scenario: Forward subtitle
- **WHEN** `station='成型', direction='forward'`
- **THEN** subtitle SHALL indicate: `成型站不良批次 → 追蹤倖存批次下游表現`

### Requirement: CSV export SHALL include direction-appropriate columns
Export SHALL produce CSV with columns matching the current direction's detail table.

#### Scenario: Forward CSV export
- **WHEN** user exports with `direction='forward'`
- **THEN** CSV SHALL contain forward-specific columns (detection equipment, downstream stats)

### Requirement: Page metadata SHALL be updated
`page_status.json` SHALL update the page name from '中段製程不良追溯' to '製程不良追溯分析'.

#### Scenario: Page name in page_status.json
- **WHEN** the page metadata is read
- **THEN** the name for `mid-section-defect` SHALL be '製程不良追溯分析'

## REMOVED Requirements

### Requirement: TMTT印字腳型不良分析 page
**Reason**: Functionality fully superseded by generalized traceability center (station=測試 + loss reasons filter for 276_腳型不良/277_印字不良)
**Migration**: Use `/mid-section-defect` with station=測試 and filter loss reasons to 276_腳型不良 or 277_印字不良

#### Scenario: TMTT defect page removal
- **WHEN** the change is complete
- **THEN** `frontend/src/tmtt-defect/` directory SHALL be removed
- **THEN** `src/mes_dashboard/routes/tmtt_defect_routes.py` SHALL be removed
- **THEN** `src/mes_dashboard/services/tmtt_defect_service.py` SHALL be removed
- **THEN** `src/mes_dashboard/sql/tmtt_defect/` directory SHALL be removed
- **THEN** `nativeModuleRegistry.js` SHALL have tmtt-defect registration removed
- **THEN** `page_status.json` SHALL have tmtt-defect entry removed
