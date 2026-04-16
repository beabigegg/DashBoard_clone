## Context

`try_acquire_lock(lock_name, ttl_seconds=60) -> bool` is the only distributed lock primitive in the project. It uses Redis `SET NX EX` against the **control-plane** Redis instance (configured with `noeviction` policy at [redis_client.py:24-27](src/mes_dashboard/core/redis_client.py#L24)) so that lock keys are not subject to eviction pressure. That part is correct.

The bug is in the error path. At [redis_client.py:218-222](src/mes_dashboard/core/redis_client.py#L218) the function returns `True` when the control client is `None` (Redis disabled or unreachable), and at [lines 233-236](src/mes_dashboard/core/redis_client.py#L233) it returns `True` for any exception during the `SET NX EX` call. Both return paths log a warning but the warning blends into the access log and is not actionable.

Nine callers exist (full table in proposal). All assume the lock was acquired and proceed to do something expensive. When Redis is healthy this works fine. When Redis is unhealthy, the locks silently disappear and every gunicorn/RQ worker independently runs the protected operation. The most damaging case is `wip_cache_update` — under Redis trouble, every gunicorn worker triggers a full `DW_MES_LOT_V` table scan. Two gunicorn workers × four threads = up to 8 concurrent identical full table scans against Oracle.

The existing test at [tests/test_distributed_lock.py:60](tests/test_distributed_lock.py#L60) does `if not redis_available(): pytest.skip()` — so the entire fail-open code path has never been exercised in CI.

## Goals / Non-Goals

**Goals:**
- Force every existing and future caller of the lock primitive to declare its fail-mode intent. No more silent fail-open.
- Convert "Redis incident" from "Oracle amplification event" into "graceful degradation event".
- Provide a clean exception path (`LockUnavailableError`) for callers that genuinely cannot run without exclusivity.
- Give operators a leading indicator that Redis is in trouble (the new `fail_mode_triggered` counter).
- Add the missing test coverage for fail-mode behaviour using a fault-injecting fixture.

**Non-Goals:**
- Replacing Redis with a different lock store (Redlock / Zookeeper / etcd). The single-Redis SET NX EX approach is fit for purpose.
- Adding wait-and-retry semantics. The lock stays non-blocking. Callers that want to retry can loop themselves.
- Migrating other services to the same `MesServiceError` taxonomy en-masse — that's the scope of the per-service follow-up changes.
- Building a full circuit breaker around Redis. The fail-mode counter is the minimum signal; full circuit breaking is a future concern.

## Decisions

### 1. Required keyword-only `fail_mode` parameter, no default

**Decision**: `try_acquire_lock(lock_name, ttl_seconds=60, *, fail_mode: Literal["closed", "raise", "open"]) -> bool`. Calling without `fail_mode` raises `TypeError` at the call site (Python keyword-only enforcement).

**Alternatives considered:**
- *Default `fail_mode="closed"`*: silent migration would flip the behaviour of all 9 existing callers without a code review for each. Some callers (cleanup daemons) genuinely want "raise" semantics; auto-defaulting to "closed" would mask bugs.
- *Default `fail_mode="open"` (preserve current)*: continues the silent-trap. Future callers will copy the wrong example.
- *Two functions (`try_acquire_lock_or_skip` + `try_acquire_lock_or_raise`)*: cleaner but doubles the API surface and makes the third (`open`) mode awkward.

Forcing the keyword at the type level guarantees every existing caller is touched as part of this change — no caller gets migrated by accident.

### 2. Three modes, not two

**Decision**: `closed`, `raise`, and `open` — not just `closed`/`raise`.

**Rationale**: A small number of operations are idempotent and cheap enough that running twice is fine. Forcing them through `raise` would add try/except plumbing for no real benefit. Keeping `open` available — but as an explicit opt-in with a justifying comment — preserves correctness without sacrificing pragmatism.

**Discipline**: every `fail_mode="open"` call site MUST have a `# fail_mode=open: <reason>` comment on the same line or directly above. The integration check in tasks/8.x greps for this.

### 3. Per-callsite categorisation table

| Caller | Mode | Reason |
|---|---|---|
| `cache_updater.wip_cache_update` | `closed` | Stale WIP data is OK for one tick; Oracle amplification is not. |
| `cache_updater.resource_cache` | `closed` | Same — resource cache rebuilds tolerate skipping. |
| `cache_updater.filter_cache` (container, reason) | `closed` | Filter caches refresh on schedule; one missed refresh is invisible. |
| `realtime_equipment_cache._load_equipment_status_from_oracle` | `closed` | Equipment status updates every minute; one missed minute is acceptable. |
| `scrap_reason_exclusion_cache` | `closed` | Reason list changes infrequently. |
| `yield_alert_dataset_cache` (per-query single-flight) | `closed` | Caller surfaces "查詢進行中，請稍候" when lock unavailable; better than two parallel multi-minute queries with conflicting parquet writes. |
| `anomaly_detection_scheduler` (compute + daily refresh) | `closed` | Scheduler retries on next tick. |
| `query_spool_store.cleanup_expired_spool` | `raise` | Daemon caller wraps in try/except, logs, sleeps, retries. Raising stops the current tick cleanly. |
| `spool_warmup_scheduler` (leader election) | `raise` | If leader can't be elected, skip the warmup batch entirely — don't run two warmups. |

No site is a `open` candidate today. The `open` mode exists for future use and to signal opt-in is allowed when justified.

### 4. New context manager `with_distributed_lock`

**Decision**: Add a context manager that wraps `try_acquire_lock` and `release_lock`:

```python
@contextmanager
def with_distributed_lock(name: str, ttl_seconds: int = 60, *, fail_mode: str):
    acquired = try_acquire_lock(name, ttl_seconds, fail_mode=fail_mode)
    if not acquired:
        yield False
        return
    try:
        yield True
    finally:
        release_lock(name)
```

New code uses the context manager. Existing call sites stay on `try_acquire_lock` + `release_lock` to keep this PR focused on the contract change, not a structural refactor. A follow-up cleanup PR can migrate them.

### 5. New telemetry counter

**Decision**: Increment `mes.lock.fail_mode_triggered{name=<lock>,mode=<mode>}` whenever the fail-mode branch is entered (i.e., whenever Redis is unavailable / exception). The counter is exposed via the existing admin metrics endpoint (whatever surface `admin-performance` capability uses).

**Rationale**: Today, "Redis hiccupped and we lost a lock" is invisible unless an operator is grepping logs. A counter makes it dashboard-able, and a 5-minute alert on `> 0` is a leading indicator that Redis is in trouble before users notice slow queries.

### 6. New `LockUnavailableError` lives in `core/exceptions.py`

**Decision**: `LockUnavailableError(MesServiceError)` is added to `core/exceptions.py`, which is created by the `query-tool-error-contract` change. This change therefore depends on `query-tool-error-contract` being landed first, OR on the two PRs being co-merged with `core/exceptions.py` landing first within the merge.

**Alternatives considered:**
- *Define a new `core/lock_errors.py`*: scatters exceptions across multiple modules; one file is cleaner.
- *Inline `class LockUnavailableError(Exception)` in redis_client.py*: bypasses the unified hierarchy and the `@map_service_errors` decorator can't catch it consistently.

### 7. Test strategy: monkeypatch fixture, not real Redis kill

**Decision**: The new test file `tests/test_lock_fail_modes.py` uses pytest monkeypatch to replace `get_control_redis_client` with a function returning `None` (or raising) — fast, deterministic, no infrastructure dependency. Real-Redis chaos test is added separately as `tests/test_distributed_lock.py::test_real_redis_outage_recovery` and gated on `--run-integration` (it brings down a local Redis instance).

The chaos integration test belongs to the `qa-real-integration-coverage` change, not this one. This change ships the unit-level fault injection.

## Risks / Trade-offs

- **[Stale-data window during Redis outage]** → Cache refreshes pause. Users see data up to one refresh-cycle old (typically 60-300 seconds). Mitigation: surface `meta.cache_state="stale"` from the existing envelope so the frontend can show a banner. Banner UI is out of scope for this change but the meta hook already exists from `qa-coverage-hardening`.
- **[Single-flight collisions during outage]** → Two parallel users hitting yield-alert simultaneously while Redis is down both get `closed` from the lock. Caller logic surfaces a "in progress" message and asks them to retry. This is strictly better than running two multi-minute queries that race to write the same spool.
- **[Daemon `raise` callers spam logs during sustained outage]** → Spool cleanup raising every minute fills the log. Mitigation: callers should catch `LockUnavailableError` once, log at WARN, and back off (use existing log throttling helpers, or just rely on the log to be noisy — sustained Redis outage is already a P1).
- **[Hidden caller missed by grep]** → If there's a 10th `try_acquire_lock` caller that isn't in the table, it'll fail at runtime with `TypeError`. Mitigation: tasks include a `grep -rn "try_acquire_lock(" src/` pass before merge.
- **[Exception import cycle]** → `redis_client.py` importing from `core/exceptions.py` is fine (exceptions module has no dependencies). Verify in tasks.
- **[Counter cardinality]** → Lock names are bounded (~10 today), so counter cardinality is fine.

## Migration Plan

1. Pre-req: land `query-tool-error-contract` first (or co-merge with this PR, with exceptions.py landing first).
2. Land `LockUnavailableError` addition to `core/exceptions.py` as part of this change (or rely on it being already present).
3. Land `try_acquire_lock` signature change + 9 caller updates + new test file as one PR. CI fails immediately if any caller is missed (TypeError at import-time-ish).
4. Deploy. Watch the new `fail_mode_triggered` counter for a week. If it stays at zero, Redis is healthy.
5. Run the chaos integration test in a staging env (real Redis kill) once before declaring victory.

**Rollback**: revert the PR. The fail-mode parameter goes away and behaviour returns to fail-open. No data migration.

## Open Questions

*(none — all decisions resolved during planning)*
