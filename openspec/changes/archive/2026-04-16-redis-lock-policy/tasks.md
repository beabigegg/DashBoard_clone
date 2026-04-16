## 1. Pre-requisite: ensure core/exceptions.py exists

- [x] 1.1 Confirm `query-tool-error-contract` change has landed (or land it first within the same merge). `core/exceptions.py` MUST exist and define `MesServiceError` before this change can compile.
- [x] 1.2 If co-merging, sequence the commits so `core/exceptions.py` is committed before `redis_client.py` is touched.

## 2. Add LockUnavailableError exception

- [x] 2.1 In `src/mes_dashboard/core/exceptions.py`, add `class LockUnavailableError(MesServiceError): pass`. The base class already accepts `(message, details=None, cause=None)`.
- [x] 2.2 Extend `tests/test_core_exceptions.py` (created by `query-tool-error-contract`) with a case for `LockUnavailableError` carrying `details={"lock_name": "x"}` and `cause=original_exc`.

## 3. Refactor try_acquire_lock signature

- [x] 3.1 In `src/mes_dashboard/core/redis_client.py`, change the signature to `try_acquire_lock(lock_name: str, ttl_seconds: int = 60, *, fail_mode: Literal["closed", "raise", "open"]) -> bool`. The `*` enforces keyword-only.
- [x] 3.2 Update the docstring to document all three fail modes and link to `distributed-lock-policy` spec.
- [x] 3.3 Replace the existing fail-open code paths (lines 218-222 and 233-236):
  - On Redis client `None` OR exception: branch on `fail_mode`:
    - `"closed"` → increment counter, log WARN, return `False`
    - `"raise"` → increment counter, log WARN, `raise LockUnavailableError(...) from cause`
    - `"open"` → increment counter, log WARN, return `True`
- [x] 3.4 Add the `mes.lock.fail_mode_triggered{name=<lock>,mode=<mode>}` counter increment. Wire it through the existing admin metrics surface (find the right module via grep on existing counters).

## 4. Add with_distributed_lock context manager

- [x] 4.1 In the same file, add `@contextmanager def with_distributed_lock(name, ttl_seconds=60, *, fail_mode)`. Yields the boolean from `try_acquire_lock`. Calls `release_lock` in `finally` only when `acquired` was `True`.
- [x] 4.2 Export it from `core/__init__.py` if there is a public re-export pattern; otherwise document the import path in the docstring.

## 5. Update all 9 existing call sites with explicit fail_mode

Each task is "open the file, find the `try_acquire_lock(` call(s), add `fail_mode=...` per the categorisation table in design.md, and add a comment if `open`". Run `pytest` after each file to catch typos.

- [x] 5.1 `src/mes_dashboard/core/cache_updater.py` — 4 sites (WIP, resource, container filter, reason filter, yield-alert warmup): all `fail_mode="closed"`.
- [x] 5.2 `src/mes_dashboard/services/realtime_equipment_cache.py` — 2 sites: `fail_mode="closed"`.
- [x] 5.3 `src/mes_dashboard/services/yield_alert_dataset_cache.py` — 2 sites (single-flight, streaming write): `fail_mode="closed"`. Verify the caller surfaces a useful message when the lock fails.
- [x] 5.4 `src/mes_dashboard/services/anomaly_detection_scheduler.py` — 2 sites (compute, daily refresh): `fail_mode="closed"`.
- [x] 5.5 `src/mes_dashboard/services/scrap_reason_exclusion_cache.py` — 2 sites: `fail_mode="closed"`.
- [x] 5.6 `src/mes_dashboard/core/query_spool_store.py` — 2 sites (cleanup): `fail_mode="raise"`. Wrap the daemon caller in try/except `LockUnavailableError` → log + sleep + retry next tick.
- [x] 5.7 `src/mes_dashboard/core/spool_warmup_scheduler.py` — 2 sites (leader election): `fail_mode="raise"`. Wrap the scheduler entry in try/except.
- [x] 5.8 Run `grep -rn "try_acquire_lock(" src/mes_dashboard/` to confirm zero call sites are missing `fail_mode=`.

## 6. New unit test: tests/test_lock_fail_modes.py

- [x] 6.1 Create the file. Use a pytest fixture that monkeypatches `mes_dashboard.core.redis_client.get_control_redis_client` to return `None` (simulates Redis unavailable).
- [x] 6.2 Test `fail_mode="closed"` → returns `False`, counter incremented.
- [x] 6.3 Test `fail_mode="raise"` → raises `LockUnavailableError`, counter incremented, exception has `details["lock_name"]`.
- [x] 6.4 Test `fail_mode="open"` → returns `True`, counter incremented, WARN log captured.
- [x] 6.5 Test omitting `fail_mode` → `TypeError`.
- [x] 6.6 Second fixture: monkeypatch `client.set` to raise `redis.exceptions.ConnectionError`. Repeat the three fail-mode assertions to cover the exception code path (not just the `client is None` path).
- [x] 6.7 Test `with_distributed_lock` happy path: lock acquired, block runs, `release_lock` called once.
- [x] 6.8 Test `with_distributed_lock` fail-closed: block sees `False`, no `release_lock` call.
- [x] 6.9 Test `with_distributed_lock` fail-raise: `LockUnavailableError` propagates out of the `with`.
- [x] 6.10 Run `pytest tests/test_lock_fail_modes.py -v` — green.

## 7. Static check for fail_mode="open" justification

- [x] 7.1 Add `tests/test_lock_open_justification.py` that walks every `.py` file under `src/mes_dashboard/`, finds lines containing `fail_mode="open"` or `fail_mode='open'`, and asserts each line (or the line above) contains the substring `fail_mode=open:`.
- [x] 7.2 Run it. Expect zero `open` sites today, so the test passes vacuously. The check is a guard against future drift.

## 8. Caller behaviour tests

- [x] 8.1 `tests/test_cache_updater_lock_behavior.py` (new): inject `get_control_redis_client → None`, call `wip_cache_update`, assert no Oracle call was made and the previously-cached data is still served.
- [x] 8.2 `tests/test_yield_alert_lock_behavior.py` (new): inject lock failure mid-query, assert the user-facing error envelope contains a "retry shortly" message, not a 500.
- [x] 8.3 `tests/test_spool_cleanup_lock_behavior.py` (new): inject lock raise, assert daemon catches `LockUnavailableError`, logs at WARN, and does not crash.

## 9. Verification

- [x] 9.1 `pytest tests/test_lock_fail_modes.py tests/test_lock_open_justification.py tests/test_cache_updater_lock_behavior.py tests/test_yield_alert_lock_behavior.py tests/test_spool_cleanup_lock_behavior.py -v` — all green.
- [x] 9.2 `pytest tests/test_distributed_lock.py --run-integration -v` against a real Redis — happy-path tests still pass with the new signature.
- [x] 9.3 `grep -rn "try_acquire_lock(" src/mes_dashboard/ | grep -v "fail_mode="` — expect zero matches.
- [x] 9.4 Manual smoke test in dev: stop local Redis, start the server, hit a dashboard page, verify cache refresh skips silently and the user sees the stale data with no error spam.
- [x] 9.5 Restart Redis. Verify cache refresh resumes on the next tick. Verify the `mes.lock.fail_mode_triggered` counter has incremented.
- [x] 9.6 `openspec validate redis-lock-policy --strict` passes.
