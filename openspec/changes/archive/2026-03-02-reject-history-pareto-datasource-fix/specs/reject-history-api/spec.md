## MODIFIED Requirements

### Requirement: Reject History SQL base query SHALL source dimension columns from correct tables

The base query (`performance_daily.sql`, `performance_daily_lot.sql`) SHALL source each dimension column from its authoritative table.

#### Scenario: PJ_TYPE sourced from DW_MES_CONTAINER
- **WHEN** the base query resolves PJ_TYPE
- **THEN** it SHALL use `DW_MES_CONTAINER.PJ_TYPE` only
- **THEN** it SHALL NOT fall back to `DW_MES_WIP`

#### Scenario: PRODUCTLINENAME sourced from DW_MES_CONTAINER
- **WHEN** the base query resolves PRODUCTLINENAME (package)
- **THEN** it SHALL use `DW_MES_CONTAINER.PRODUCTLINENAME` only
- **THEN** it SHALL NOT fall back to `DW_MES_WIP`

#### Scenario: EQUIPMENTNAME sourced from DW_MES_LOTREJECTHISTORY only
- **WHEN** the base query resolves EQUIPMENTNAME
- **THEN** it SHALL use `DW_MES_LOTREJECTHISTORY.EQUIPMENTNAME` only
- **THEN** it SHALL NOT perform any additional lookup when the value is NULL

#### Scenario: WORKFLOWNAME sourced from DW_MES_LOTWIPHISTORY via WIPTRACKINGGROUPKEYID
- **WHEN** the base query resolves WORKFLOWNAME
- **THEN** it SHALL LEFT JOIN `DW_MES_LOTWIPHISTORY` on `WIPTRACKINGGROUPKEYID`
- **THEN** it SHALL use `DW_MES_LOTWIPHISTORY.WORKFLOWNAME`
- **THEN** it SHALL NOT fall back to SPECNAME or any other field

#### Scenario: No DW_MES_WIP dependency in base query
- **WHEN** the base query CTEs are examined
- **THEN** there SHALL be no CTE or JOIN referencing `DW_MES_WIP`

### Requirement: Dimension Pareto workcenter dimension SHALL use WORKCENTER_GROUP

The workcenter dimension in Pareto analysis SHALL group by `WORKCENTER_GROUP`, not individual `WORKCENTERNAME`.

#### Scenario: Cache-based Pareto workcenter mapping
- **WHEN** `reject_dataset_cache.py` computes workcenter dimension Pareto
- **THEN** the dimension column SHALL be `WORKCENTER_GROUP`

#### Scenario: SQL-based Pareto workcenter mapping
- **WHEN** `reject_history_service.py` builds workcenter dimension Pareto SQL
- **THEN** the dimension column SHALL be `b.WORKCENTER_GROUP`
