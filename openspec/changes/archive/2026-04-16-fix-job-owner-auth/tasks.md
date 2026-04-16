## 1. Owner token helper

- [x] 1.1 Add `get_owner_token() -> str` to `src/mes_dashboard/core/permissions.py`. Logged-in branch returns `session["user"]["username"]`; anonymous branch lazily mints `session["mes_owner_token"] = uuid4().hex` and returns it. Document in docstring that the helper mutates session on first anonymous call.
- [x] 1.2 Add unit test `tests/test_owner_token.py` covering: logged-in username, anonymous lazy mint, anonymous re-read returns same value, value is hex/uuid-shaped.

## 2. enqueue_job contract

- [x] 2.1 Modify `enqueue_job()` in `src/mes_dashboard/services/async_query_job_service.py` to require keyword-only `owner: str`. Add `"owner": owner` into the initial meta dict at line ~150-162.
- [x] 2.2 Update `get_job_status()` in the same file so the returned dict surfaces `meta.get("owner")` as the `owner` field.
- [x] 2.3 Run `pytest tests/test_async_query_job_service.py` and fix any signature-mismatch failures (these are expected and prove the contract is enforced).

## 3. Thread owner through wrapper services

- [x] 3.1 `services/reject_query_job_service.enqueue_reject_query` — add `owner` parameter, pass to `enqueue_job`.
- [x] 3.2 `services/yield_alert_job_service.enqueue_yield_alert_query` — same.
- [x] 3.3 `services/production_history_job_service.enqueue_production_history_query` — same.
- [x] 3.4 `services/msd_lineage_job_service` enqueue function (line ~54) — same.
- [x] 3.5 `services/trace_lineage_job_service` enqueue function (line ~142) — same.
- [x] 3.6 `services/mid_section_defect_service` inline enqueue at line ~276 — same. If callers do not have a Flask request context, document why and resolve.

## 4. Thread owner from routes

- [x] 4.1 `routes/reject_history_routes.py:745` — `caller_owner = get_owner_token()`, pass to `enqueue_reject_query`.
- [x] 4.2 `routes/material_trace_routes.py:154` — `caller_owner = get_owner_token()`, pass to inline `enqueue_job`.
- [x] 4.3 Grep for every other caller of the 6 wrappers (`grep -rn "enqueue_yield_alert_query\|enqueue_production_history_query\|...etc" src/mes_dashboard/routes/`) and thread owner through each.
- [x] 4.4 Verify with `pytest tests/test_*_routes.py -k "async or job"` — failures here indicate a missed call site.

## 5. Rewrite abandon_job authorisation

- [x] 5.1 In `routes/job_routes.py:60-136`, delete the `body.get("owner")` lookup and the truthiness gate on `stored_owner`.
- [x] 5.2 Read `caller_owner = get_owner_token()`. Compare to `status_data.get("owner")`. Mismatch OR missing → return `error_response(FORBIDDEN, ..., status_code=403)`.
- [x] 5.3 Update the docstring at line 63 to describe the new session-derived authz.

## 6. Regression and integration tests

- [x] 6.1 New test file `tests/test_job_owner_auth.py`. Required cases:
  - Round-trip: logged-in client calls a real enqueue path → assert `redis.hget(meta_key, "owner")` equals the session username. **This is the test that would have caught the original bug.**
  - Same logged-in session abandons own job → 200.
  - Different logged-in session attempts abandon → 403.
  - Anonymous session A enqueues, same anonymous A abandons → 200 (cookie persistence).
  - Anonymous session A enqueues, anonymous session B abandons → 403.
  - Body `owner` field is ignored when session token differs → 403 (proves the body is not trusted).
  - Legacy meta with no `owner` field → 403 (fail-closed).
  - `enqueue_job(...)` without `owner` kwarg → `TypeError`.
- [x] 6.2 Update `tests/test_job_abandon_routes.py` to inject owner into Redis meta directly (not via `body.get("owner")`) and to authenticate via session fixture.
- [x] 6.3 Audit `tests/test_async_query_job_service.py` and the per-domain job tests for any place that calls `enqueue_job` without `owner`; fix.

## 7. Frontend housekeeping

- [x] 7.1 In `frontend/src/portal-shell/pending-jobs-registry.js` (or wherever the job entry shape is defined), drop `owner` from the registered entry shape if present. Confirm the `beforeunload` handler at `frontend/src/portal-shell/main.js:65-78` still sends only `{ prefix }`.
- [x] 7.2 ~~sendBeacon cookie check~~ — deferred-manual: requires DevTools in real browser. sendBeacon is same-origin and carries cookies by spec; verified in Playwright E2E test (qa-real-integration-coverage).

## 8. Verification

- [x] 8.1 `pytest tests/test_job_owner_auth.py tests/test_job_abandon_routes.py tests/test_owner_token.py -v` — all pass.
- [x] 8.2 ~~Manual owner+abandon Redis verification~~ — deferred-manual: requires running dev server + Redis CLI. Owner assignment verified by unit tests (test_job_owner_auth.py) and integration tests (test_real_multi_worker.py).
- [x] 8.3 ~~Cross-user 403 manual test~~ — deferred-manual: requires two browser sessions. Owner enforcement verified by unit tests (test_job_owner_auth.py: different-session abandon → 403).
- [x] 8.4 `openspec validate fix-job-owner-auth --strict` — passed at archive time (2026-04-16).
