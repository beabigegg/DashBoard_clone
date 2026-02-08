## 1. Resource Cache Representation Normalization

- [x] 1.1 Refactor `resource_cache` derived index to use lightweight row-position references instead of full duplicated records payload.
- [x] 1.2 Keep `get_all_resources` / `get_resources_by_filter` API outputs backward compatible while sourcing data from normalized representation.
- [x] 1.3 Update cache telemetry fields to reflect normalized representation and verify amplification calculation remains interpretable.

## 2. Oracle Query Fragment Governance

- [x] 2.1 Extract shared Oracle SQL fragments/constants for resource/equipment cache loading into a common module.
- [x] 2.2 Replace duplicated SQL literals in `resource_cache.py` and `realtime_equipment_cache.py` with shared definitions.
- [x] 2.3 Add/adjust tests to lock expected query semantics and prevent drift.

## 3. Maintainability Hygiene

- [x] 3.1 Normalize type annotations in touched cache/service modules to one consistent style.
- [x] 3.2 Replace high-frequency magic numbers with named constants or env-driven config in touched modules.
- [x] 3.3 Confirm existing login/API rate-limit and bool parser utilities remain centralized without new duplication.

## 4. Verification and Documentation

- [x] 4.1 Run targeted backend tests for resource cache, equipment cache, health/admin, and route behavior.
- [x] 4.2 Update `README.md` and `README.mdj` with round-4 hardening notes.
