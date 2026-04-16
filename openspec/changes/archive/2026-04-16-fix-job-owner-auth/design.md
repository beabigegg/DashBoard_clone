## Context

The async job lifecycle (queue → running → terminal) is shared by 6+ heavy queries (`reject_history`, `material_trace`, `mid_section_defect`, `production_history`, `yield_alert`, `trace_lineage`, `msd_lineage`). Each domain enqueues via the shared `enqueue_job()` helper in `async_query_job_service.py`. The abandon endpoint at `routes/job_routes.py` exposes a single rate-limited POST that any client can call to mark a job `abandoned`, freeing worker slots and stopping further processing.

The current owner-check at [job_routes.py:92-100](src/mes_dashboard/routes/job_routes.py#L92) reads `stored_owner = status_data.get("owner")` and only enforces equality if `stored_owner` is truthy. But [enqueue_job() at line 150-162](src/mes_dashboard/services/async_query_job_service.py#L150) writes the initial Redis HSET with no `owner` key, so `stored_owner` is always falsy and any caller passes the check. The existing test `tests/test_job_abandon_routes.py::TestAbandonOwnerCheck` mocks `status_data` to inject owner and never goes through `enqueue_job()`, so the gap was invisible.

Flask sessions are cookie-backed and present on every same-origin request including `sendBeacon` (which sends credentials by default). The login flow at `routes/user_auth_routes.py:161` populates `session["user"]["username"]`. There is no global `@login_required` on the async query routes today — anonymous users can run reject-history queries and need to be able to abandon their own jobs.

## Goals / Non-Goals

**Goals:**
- Make job ownership unforgeable: derive owner from server-side session, never from request body.
- Owner identity works for both logged-in users (use username) and anonymous tabs (use a per-session uuid token persisted in the Flask session cookie).
- Fail-closed: a job whose meta lacks `owner` cannot be abandoned at all.
- Add a regression test that catches the exact "enqueue_job forgot to write owner" gap that hid the original bug.
- Zero coordinated frontend release: existing `sendBeacon` payload remains valid.

**Non-Goals:**
- Adding `@login_required` to async query routes (orthogonal — anonymous use must still work).
- Reworking RQ worker authentication (workers consume; they never enqueue or abandon).
- Cross-tab job sharing (each browser cookie = one identity, by design).
- Persisting owner across cookie expiry / logout (jobs become un-abandonable; rely on TTL).

## Decisions

### 1. Owner token strategy: session cookie, not user account

**Decision**: Owner identity = `session["user"]["username"]` if logged in, else `session["mes_owner_token"]` (lazily-minted uuid4 hex stored in the same Flask session). A new helper `get_owner_token()` in `core/permissions.py` encapsulates this.

**Alternatives considered:**
- *Require login on all async routes*: cleanest, but breaks anonymous reject-history workflow that ops relies on.
- *Use Flask session id directly (`session.sid`)*: not stable across Flask's session lifecycle and not present on all session backends.
- *Per-tab token in localStorage*: client-controlled = forgeable; defeats the purpose.
- *X-Forwarded-For + User-Agent fingerprint*: trivially spoofable.

The session cookie is server-issued, HTTP-only, and naturally rides along with `sendBeacon`. It already exists. Using it is the lowest-friction path.

### 2. enqueue_job() requires owner — TypeError, not default

**Decision**: `owner` is a required keyword argument on `enqueue_job()`. Forgetting to pass it raises `TypeError` at the call site, not at runtime in Redis.

**Alternatives considered:**
- *Optional with `None` default*: a future caller will forget; we get a silent regression.
- *Read from `flask.session` inside enqueue_job*: couples a service module to request context. Also breaks unit tests that import `enqueue_job` outside a request.

Forcing the parameter at the type-system level makes the contract self-enforcing. The 6 wrapper services and 1 inline call site are touched anyway.

### 3. abandon_job: no body owner, fail-closed on missing meta

**Decision**: `abandon_job` deletes the `body.get("owner")` lookup entirely. It reads `caller_owner = get_owner_token()`. If `meta["owner"]` is missing OR does not equal `caller_owner` → 403 `FORBIDDEN`. No backward-compat branch.

**Alternatives considered:**
- *One-deploy compat window* (allow legacy meta without owner): adds a feature flag + a compat branch + a follow-up cleanup PR. Not worth it for the small population of in-flight jobs at deploy.
- *Soft-fail to log-only*: leaves the security hole open.

In-flight jobs without owner expire on TTL (`ASYNC_JOB_DEFAULT_TTL_SECONDS`, currently 3600s) so there is at most a one-hour window where a small number of jobs become un-abandonable. They still complete or fail naturally; only the manual abandon button stops working for them.

### 4. Frontend: no functional change

**Decision**: Leave `pending-jobs-registry.js` and `main.js` `beforeunload` handler as-is. Optionally remove the unused `owner` field from the registry entry shape if it exists.

**Rationale**: The frontend already sends only `{ prefix }`. The session cookie (which carries the owner identity server-side) is automatically attached to `sendBeacon` for same-origin requests. No coordinated release required.

### 5. Regression test: round-trip through enqueue_job

**Decision**: New test file `tests/test_job_owner_auth.py` includes a test that:
1. Sets up a Flask test client with a session.
2. Calls `enqueue_job(...)` through the wrapper (e.g., `enqueue_reject_query`).
3. Reads `redis.hget(meta_key, "owner")` directly and asserts it matches the session's `get_owner_token()`.

This test would have failed against the original code and is the canonical guard going forward.

## Risks / Trade-offs

- **[In-flight jobs un-abandonable post-deploy]** → Acceptable. TTL expiry bounds the impact at ~1 hour. Operators can `redis-cli HSET <meta_key> owner <username>` as a manual escape hatch if truly needed.
- **[Anonymous user clears cookies mid-job]** → Job becomes orphaned (un-abandonable) until TTL. Same outcome as today for any unauthenticated user; no regression.
- **[Worker-initiated re-enqueue paths]** → If any RQ worker calls `enqueue_job` (it should not), it will not have a Flask request context and will fail with `RuntimeError` from `get_owner_token()`. Verify in implementation phase that all `enqueue_job` callers are inside Flask request context. The grep at exploration time found only Flask routes/services calling it.
- **[Test mocks that bypass enqueue_job]** → Existing tests in `test_job_abandon_routes.py` mock `status_data["owner"]` directly. Rewriting them to use the real flow makes them slower but more truthful. The new round-trip test is the canonical check; the unit tests can stay as fast-path with explicit owner injection via Redis fixture.
- **[`get_owner_token()` writes to session on read]** → Lazy mint mutates `session`, which marks it dirty and triggers a cookie set on the response. This is fine for the first call but means GET endpoints that previously didn't touch session will now set a cookie. Acceptable; documented in the helper docstring.

## Migration Plan

1. Land all backend changes in one PR (helper + enqueue_job + 6 wrappers + abandon_job + tests).
2. Deploy. Existing in-flight jobs lose abandonability for up to `result_ttl` seconds.
3. Verify in production: pick a fresh job, confirm `redis-cli HGETALL <prefix>:job:<id>:meta` shows `owner=<expected>`. Try abandoning from a different incognito tab → expect 403.
4. Frontend cleanup (drop unused owner from registry shape) can ride a later release.

**Rollback**: revert the PR. No schema migration; Redis meta keys are TTL-bounded so old-shape and new-shape coexist without cleanup.

## Open Questions

*(none — both decisions resolved during planning)*
