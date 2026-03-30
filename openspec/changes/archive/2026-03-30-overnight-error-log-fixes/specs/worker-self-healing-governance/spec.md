# Delta Spec: worker-self-healing-governance

## ADDED Requirements

### Requirement: Graceful cache_updater shutdown before engine disposal

`dispose_engine()` SHALL signal the `cache_updater` background thread to stop and join it (with timeout) **before** disposing any SQLAlchemy engine.

The shutdown sequence SHALL be:
1. Stop keep-alive thread (existing)
2. Stop cache_updater thread (new)
3. Dispose health engine
4. Dispose slow-query engine
5. Dispose main engine

`cache_updater` module SHALL export a `stop_cache_updater()` function that:
- Sets a stop event
- Joins the thread with `timeout=5` seconds
- Logs whether the thread stopped or timed out

#### Scenario: Clean shutdown during worker recycling
- **WHEN** gunicorn sends SIGTERM to a worker
- **AND** the worker calls `dispose_engine()`
- **THEN** `cache_updater` thread receives stop signal before engines are disposed
- **AND** `cache_updater` thread stops within 5 seconds
- **AND** no `threading._shutdown` deadlock occurs

#### Scenario: cache_updater thread does not stop in time
- **WHEN** `stop_cache_updater()` is called
- **AND** the cache_updater thread does not stop within 5 seconds
- **THEN** disposal proceeds anyway (non-blocking)
- **AND** a WARNING is logged indicating the thread did not stop in time

#### Scenario: dispose_engine called when cache_updater not running
- **WHEN** `dispose_engine()` is called
- **AND** cache_updater was never started (e.g., test environment)
- **THEN** `stop_cache_updater()` is a no-op and does not raise
