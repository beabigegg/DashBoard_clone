## ADDED Requirements

### Requirement: Reject dataset cache view path SHALL use DuckDB SQL runtime as sole compute engine
The `apply_view()` function in `reject_dataset_cache.py` SHALL compute all view results exclusively via `reject_cache_sql_runtime.py`, without loading the spool file as a pandas DataFrame.

#### Scenario: View computed by DuckDB SQL runtime
- **WHEN** `apply_view()` is called with a valid query_id and a spool file exists
- **THEN** the system SHALL compute the view result via `reject_cache_sql_runtime.py`
- **THEN** the system SHALL NOT call `_get_cached_df()` to load a pandas DataFrame for derivation
- **THEN** no pandas `_derive_*()` function SHALL be called in the view path

#### Scenario: DuckDB runtime failure or spool miss returns cache_expired
- **WHEN** `apply_view()` is called and the DuckDB SQL runtime returns no result (spool file missing, runtime error, or feature flag disabled)
- **THEN** the response SHALL return `{ success: false, error: "cache_expired" }` with HTTP 410
- **THEN** the system SHALL NOT fall back to the pandas computation path
- **THEN** async re-query behavior (202 response from `execute_primary_query()`) SHALL be unchanged
