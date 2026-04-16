## Why

The async job abandon endpoint `/api/job/<job_id>/abandon` accepts an `owner` field from the request body and uses it to authorise the call. In practice this check is dead code: `enqueue_job()` never writes an `owner` field into the job metadata, so `stored_owner` is always falsy and the owner branch is skipped. Net effect — **any unauthenticated client can abandon any in-flight async job** by knowing the prefix and job_id (both observable in the network tab).

The bug was hidden by tests that mock `status_data["owner"]` directly instead of round-tripping through `enqueue_job()`. We need server-derived ownership and a regression test that catches the meta-population gap.

## What Changes

- **BREAKING** `enqueue_job()` requires a new `owner: str` keyword argument. Every call site must thread an owner token through. RQ workers do not enqueue, so this only affects Flask request-context callers.
- New helper `get_owner_token()` in `core/permissions.py`: returns `session["user"]["username"]` for logged-in users, otherwise lazily mints and stores `session["mes_owner_token"]` (uuid4 hex). Cookie-bound; unforgeable from the client side.
- `abandon_job` route stops reading `owner` from the request body. It reads `get_owner_token()` from the session and compares it to `meta["owner"]`. If `meta["owner"]` is missing (legacy job created before this deploy) → **fail-closed 403**. Affected legacy jobs expire on TTL.
- All 6 enqueue wrapper services (`reject_query_job_service`, `yield_alert_job_service`, `production_history_job_service`, `msd_lineage_job_service`, `trace_lineage_job_service`, `mid_section_defect_service`) gain an `owner` parameter and pass it through.
- All Flask routes that call those wrappers (and the inline `enqueue_job` call at `material_trace_routes.py:154`) read `get_owner_token()` and pass it.
- Frontend `pending-jobs-registry` and the `beforeunload` `sendBeacon` handler need no functional change — they already do not send `owner`. The same browser cookie naturally resolves to the same owner token server-side.
- New regression test that round-trips through `enqueue_job()` and asserts `redis.hget(meta_key, "owner")` matches the session token. This is the test that would have caught the original bug.

## Capabilities

### New Capabilities
*(none)*

### Modified Capabilities
- `async-query-job-service`: `enqueue_job()` requires `owner`; `get_job_status()` returns the stored owner; abandon authorisation is now session-derived and fail-closed.

## Impact

- **Affected code**:
  - `src/mes_dashboard/core/permissions.py` (new helper)
  - `src/mes_dashboard/services/async_query_job_service.py` (`enqueue_job` signature + meta write)
  - `src/mes_dashboard/services/{reject_query,yield_alert,production_history,msd_lineage,trace_lineage,mid_section_defect}_job_service.py` (parameter pass-through)
  - `src/mes_dashboard/routes/job_routes.py` (abandon authz rewrite)
  - `src/mes_dashboard/routes/{reject_history,material_trace,...}_routes.py` (read session, pass owner)
  - `frontend/src/portal-shell/main.js` and `pending-jobs-registry.js` (housekeeping only — already do not send owner)
  - `tests/test_job_owner_auth.py` (new), `tests/test_job_abandon_routes.py` (rewrite mocks)
- **API contract**: abandon endpoint no longer accepts `owner` in body; it is silently ignored. Returns 403 instead of 200 when owner does not match. Error envelope unchanged.
- **Operational**: jobs in flight at deploy time will have no `owner` field and become un-abandonable until they expire on `result_ttl`. Acceptable per design discussion.
- **Dependencies**: none added.
