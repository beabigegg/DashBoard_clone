## MODIFIED Requirements

### Requirement: MSD lineage spool results SHALL be consumed by DuckDB runtime
The MSD lineage parquet spool (produced by `msd_lineage_job_service`) SHALL be consumed by DuckDB for downstream aggregation, replacing Python in-memory graph reconstruction.

#### Scenario: Lineage spool used in DuckDB aggregation
- **WHEN** the MSD events aggregation stage needs lineage data (ancestors, cid_to_name)
- **THEN** it SHALL read the lineage parquet spool directly via DuckDB
- **THEN** it SHALL NOT call `get_msd_lineage_job_result()` to reconstruct Python dicts in memory

#### Scenario: Lineage + events JOIN in DuckDB
- **WHEN** DuckDB computes defect attribution
- **THEN** it SHALL JOIN the lineage edge-list parquet with the events parquet
- **THEN** the JOIN SHALL produce the attribution result (upstream machine → defect rate) without loading either dataset fully into Python memory
