# distributed-lock-policy Specification

## Purpose
TBD - created by archiving change redis-lock-policy. Update Purpose after archive.
## Requirements
### Requirement: Distributed lock primitive SHALL require explicit fail-mode declaration
The `try_acquire_lock(lock_name, ttl_seconds, *, fail_mode)` function in `mes_dashboard.core.redis_client` SHALL require a keyword-only `fail_mode` argument. Calling it without `fail_mode` SHALL raise `TypeError`. The accepted values are `"closed"`, `"raise"`, and `"open"`. There SHALL be no default.

#### Scenario: Missing fail_mode raises TypeError
- **WHEN** `try_acquire_lock("my_lock", ttl_seconds=60)` is called without the `fail_mode` keyword
- **THEN** Python SHALL raise `TypeError`
- **THEN** no Redis call SHALL be issued

#### Scenario: fail_mode="closed" returns False on Redis unavailable
- **WHEN** `try_acquire_lock("my_lock", fail_mode="closed")` is called and the control-plane Redis client is `None` or any exception is raised during acquisition
- **THEN** the function SHALL return `False`
- **THEN** the function SHALL increment the metric `mes.lock.fail_mode_triggered{name="my_lock",mode="closed"}`
- **THEN** the function SHALL log a WARN-level message identifying the lock and the failure cause

#### Scenario: fail_mode="raise" raises LockUnavailableError on Redis unavailable
- **WHEN** `try_acquire_lock("my_lock", fail_mode="raise")` is called and Redis is unavailable
- **THEN** the function SHALL raise `LockUnavailableError` with a message identifying the lock
- **THEN** the function SHALL increment the metric `mes.lock.fail_mode_triggered{name="my_lock",mode="raise"}`
- **THEN** the original cause SHALL be chained via `raise ... from exc`

#### Scenario: fail_mode="open" returns True on Redis unavailable (legacy escape hatch)
- **WHEN** `try_acquire_lock("my_lock", fail_mode="open")` is called and Redis is unavailable
- **THEN** the function SHALL return `True`
- **THEN** the function SHALL increment the metric `mes.lock.fail_mode_triggered{name="my_lock",mode="open"}`
- **THEN** the function SHALL log a WARN-level message naming the lock and stating that fail-open is in use

#### Scenario: Healthy path is unchanged
- **WHEN** `try_acquire_lock("my_lock", fail_mode="closed")` is called against a healthy Redis and the lock is free
- **THEN** the function SHALL return `True`
- **THEN** no `fail_mode_triggered` metric SHALL be incremented

### Requirement: Context manager SHALL wrap try_acquire_lock with try/finally release
The module SHALL provide `with_distributed_lock(name, ttl_seconds=60, *, fail_mode)` as a context manager that calls `try_acquire_lock` on entry and `release_lock` on exit (regardless of how the protected block exits). The context manager SHALL yield a boolean indicating whether the lock was acquired.

#### Scenario: Acquired path
- **WHEN** the context manager enters and `try_acquire_lock` returns `True`
- **THEN** the `with` block SHALL receive `True` from `as`
- **THEN** `release_lock` SHALL be called when the block exits, even if an exception is raised inside

#### Scenario: Closed-mode skip path
- **WHEN** `with with_distributed_lock("x", fail_mode="closed") as held:` runs and Redis is unavailable
- **THEN** `held` SHALL be `False`
- **THEN** the protected block SHALL be reachable and the caller SHALL decide whether to skip
- **THEN** `release_lock` SHALL NOT be called on exit (nothing to release)

#### Scenario: Raise-mode propagates
- **WHEN** `with with_distributed_lock("x", fail_mode="raise"):` runs and Redis is unavailable
- **THEN** the context manager SHALL raise `LockUnavailableError`
- **THEN** the protected block SHALL NOT execute

### Requirement: Cache refresh callers SHALL use fail_mode="closed"
All cache refresh code paths protected by a distributed lock SHALL pass `fail_mode="closed"` so that Redis incidents do not trigger Oracle thundering herds.

#### Scenario: WIP cache refresh skips when Redis unavailable
- **WHEN** `cache_updater.wip_cache_update` runs and the control-plane Redis is unavailable
- **THEN** `try_acquire_lock("wip_cache_update", fail_mode="closed")` SHALL return `False`
- **THEN** the WIP cache update SHALL exit without executing the Oracle query
- **THEN** the previously-cached WIP data SHALL continue to serve until the next refresh tick

#### Scenario: Equipment status cache skips when Redis unavailable
- **WHEN** `realtime_equipment_cache._load_equipment_status_from_oracle` is called and Redis is unavailable
- **THEN** the lock SHALL fail closed
- **THEN** the function SHALL return without scanning the equipment status table

#### Scenario: Yield-alert single-flight skips during Redis outage
- **WHEN** a yield-alert query is initiated and Redis is unavailable
- **THEN** the per-query single-flight lock SHALL fail closed
- **THEN** the caller SHALL surface a user-visible message indicating the system is busy and to retry

### Requirement: Daemon-leader callers SHALL use fail_mode="raise"
Background daemon and leader-election callers SHALL use `fail_mode="raise"` so that Redis incidents abort the current tick cleanly without doing damage.

#### Scenario: Spool cleanup daemon aborts current tick on Redis outage
- **WHEN** `query_spool_store.cleanup_expired_spool` runs and Redis is unavailable
- **THEN** `try_acquire_lock("spool_cleanup", fail_mode="raise")` SHALL raise `LockUnavailableError`
- **THEN** the daemon SHALL catch the exception, log at WARN, and skip to the next scheduled tick

#### Scenario: Spool warmup leader election skips during outage
- **WHEN** `spool_warmup_scheduler` attempts leader election and Redis is unavailable
- **THEN** the lock SHALL raise `LockUnavailableError`
- **THEN** the warmup scheduler SHALL skip the warmup batch entirely and not enqueue jobs

### Requirement: Fail-open opt-in SHALL be justified inline
Any caller that passes `fail_mode="open"` SHALL include a comment on the same line or directly above stating the justification. The format SHALL be `# fail_mode=open: <reason>`. A static check SHALL grep the source tree for `fail_mode="open"` (and `fail_mode='open'`) and assert that each occurrence is accompanied by such a comment.

#### Scenario: Justified fail-open
- **WHEN** a caller writes `try_acquire_lock("my_lock", fail_mode="open")  # fail_mode=open: idempotent metric increment`
- **THEN** the static check SHALL pass

#### Scenario: Unjustified fail-open
- **WHEN** a caller writes `try_acquire_lock("my_lock", fail_mode="open")` with no justifying comment
- **THEN** the static check SHALL fail with a message naming the file and line

### Requirement: LockUnavailableError SHALL be a MesServiceError subclass
`LockUnavailableError` SHALL be defined in `mes_dashboard.core.exceptions` as a subclass of `MesServiceError`. It SHALL carry the lock name as the `details["lock_name"]` field and the original cause via the `cause` attribute.

#### Scenario: Exception attributes
- **WHEN** `LockUnavailableError("lock x unavailable", details={"lock_name": "x"}, cause=original_exc)` is raised
- **THEN** `isinstance(err, MesServiceError)` SHALL be `True`
- **THEN** `err.details["lock_name"]` SHALL be `"x"`
- **THEN** `err.cause` SHALL be `original_exc`

