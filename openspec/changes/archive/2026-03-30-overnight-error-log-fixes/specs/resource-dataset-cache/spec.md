# Delta Spec: resource-dataset-cache

## MODIFIED Requirements

### Requirement: Resource dimension data convenience accessors

`resource_dataset_cache` SHALL export `_get_resource_lookup()` and `_get_workcenter_mapping()` as parameter-less convenience functions that return dimension data needed by downstream consumers (`resource_history_sql_runtime`, `resource_history_routes`).

- `_get_resource_lookup()` SHALL return a `Dict[str, Dict[str, Any]]` mapping RESOURCEID to resource info by delegating to `resource_history_service._get_filtered_resources()` (no filters) + `_build_resource_lookup()`.
- `_get_workcenter_mapping()` SHALL re-export `filter_cache.get_workcenter_mapping()`.

#### Scenario: sql_runtime loads dimension data successfully
- **WHEN** `resource_history_sql_runtime` imports `_get_resource_lookup` and `_get_workcenter_mapping` from `resource_dataset_cache`
- **THEN** both imports resolve without `ImportError`
- **AND** `_get_resource_lookup()` returns a dict keyed by RESOURCEID
- **AND** `_get_workcenter_mapping()` returns a dict keyed by workcenter name

#### Scenario: routes inject resource metadata successfully
- **WHEN** `resource_history_routes._inject_resource_metadata()` calls `_get_resource_lookup()` and `_get_workcenter_mapping()`
- **THEN** both calls succeed and return populated dicts when resource cache is warm

#### Scenario: e2e tests can patch the accessors
- **WHEN** e2e tests use `@patch('mes_dashboard.services.resource_dataset_cache._get_resource_lookup')`
- **THEN** the patch target resolves correctly
