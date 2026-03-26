## 1. Cache Consistency and Contention Hardening

- [x] 1.1 Harden WIP cache publish in `cache_updater.py` to preserve old snapshot on publish failure.
- [x] 1.2 Refactor WIP process-cache slow path in `core/cache.py` so heavy parse runs outside lock.
- [x] 1.3 Extend realtime equipment process cache with bounded `max_size` + deterministic LRU and add regression tests.

## 2. API Safety and Config Hygiene

- [x] 2.1 Add depth-safe NaN cleaning in `resource_routes.py` and tests for deep payloads.
- [x] 2.2 Add shared boolean query parser in `core/utils.py` and switch `wip_routes.py` / `hold_routes.py` to it.
- [x] 2.3 Make filter-cache source views configurable (env-based) in `filter_cache.py` and add config tests.

## 3. Runtime Guardrails

- [x] 3.1 Add DB connection-string redaction logging filter in `core/database.py` (or logging bootstrap) with tests.
- [x] 3.2 Add 5-second internal memoization for `/health` and `/health/deep` (disabled in testing) and tests.
- [x] 3.3 Add lightweight rate limiting for selected high-cost APIs with clear throttling responses and tests.

## 4. Validation and Documentation

- [x] 4.1 Run targeted backend/frontend tests and benchmark smoke gate.
- [x] 4.2 Update `README.md` and `README.mdj` with round-3 hardening notes and new env variables.
