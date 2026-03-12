## ADDED Requirements

### Requirement: Frontend compute shift SHALL support DuckDB-WASM as a computation backend
The frontend compute shift capability SHALL be extended to include DuckDB-WASM as an alternative to pure JS Array computation for large datasets.

#### Scenario: DuckDB-WASM used for large datasets
- **WHEN** a report page receives a dataset exceeding the JSON-mode threshold
- **THEN** the page SHALL load the dataset as Parquet into DuckDB-WASM
- **THEN** all filter/sort/page/aggregate operations SHALL be executed via SQL in the Web Worker
- **THEN** results SHALL match server-computed baselines within parity tolerance

#### Scenario: JS Array used for small datasets
- **WHEN** a report page receives a dataset within the JSON-mode threshold
- **THEN** the page SHALL use existing JS Array computation (no DuckDB-WASM overhead)
- **THEN** parity verification SHALL apply equally to both computation paths

### Requirement: Frontend compute shift SHALL use Web Workers for non-blocking computation
Compute-shifted logic that operates on large datasets SHALL execute in a Web Worker to prevent UI thread blocking.

#### Scenario: Heavy computation does not block UI
- **WHEN** a DuckDB-WASM SQL query or JS Array aggregation operates on >5,000 rows
- **THEN** the computation SHALL execute in a Web Worker
- **THEN** the UI SHALL remain responsive (no frame drops exceeding 100ms)
- **THEN** a loading indicator SHALL be displayed during computation

### Requirement: Frontend compute shift SHALL support Parquet as a data transfer format
In addition to JSON, the frontend compute shift capability SHALL support receiving datasets as Parquet files for more efficient transfer and local processing.

#### Scenario: Parquet transfer efficiency
- **WHEN** a dataset is transferred as Parquet instead of JSON
- **THEN** the transfer size SHALL be at least 2x smaller than the equivalent JSON payload
- **THEN** the Parquet file SHALL be directly loadable by DuckDB-WASM without intermediate conversion
