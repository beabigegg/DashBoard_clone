## MODIFIED Requirements

### Requirement: Historical query domains SHALL be classified into Type A or Type B semantic response contract
All historical query domains SHALL declare and implement one of two query response semantic patterns based on their primary query execution model.

**Type A — Synchronous Bootstrap:**
The primary query executes synchronously in the request thread. On view miss (410), the client SHALL re-trigger `execute_primary_query()` synchronously and load the view after completion. If the synchronous bootstrap finishes the Oracle/spool stage but cannot render a valid view result from DuckDB, the server SHALL surface an explicit failure and SHALL NOT synthesize a `200` empty success payload.

Domains: `resource-history`, `hold-history`, `yield-alert`, `production-history`

**Type B — Async Polling:**
The primary query executes asynchronously via an RQ job (202 response). On view miss (410), the client SHALL dispatch a new async job (POST to query endpoint → 202) and poll for completion before loading the view.

Domains: `reject-history`, `material-trace`, `MSD`

#### Scenario: Type A view miss — client re-triggers sync query
- **WHEN** a Type A domain returns HTTP 410 `cache_expired` on a view request
- **THEN** the client SHALL call the domain's primary query endpoint synchronously
- **THEN** upon receiving a 200 response with result data, the client SHALL load the view with the returned data
- **THEN** the client SHALL NOT display a polling spinner for Type A domains

#### Scenario: Type A bootstrap render failure — server returns explicit failure
- **WHEN** a Type A primary query successfully produces or locates a spool but DuckDB cannot render the requested bootstrap view
- **THEN** the server SHALL return a non-200 failure response
- **THEN** the response SHALL NOT be a synthetic empty success payload

#### Scenario: Type B view miss — client dispatches async job
- **WHEN** a Type B domain returns HTTP 410 `cache_expired` on a view request
- **THEN** the client SHALL POST to the domain's async query endpoint
- **THEN** the server SHALL return HTTP 202 with a `job_id`
- **THEN** the client SHALL enter polling mode using the `job_id` until the job completes
- **THEN** upon job completion, the client SHALL request the view again

#### Scenario: View hit — both types return result directly
- **WHEN** a spool file exists for the `query_id` and DuckDB computes a result successfully
- **THEN** both Type A and Type B domains SHALL return HTTP 200 with the view data
- **THEN** no re-query or polling SHALL be triggered

### Requirement: View endpoints SHALL NOT auto-dispatch primary queries on spool miss
The view layer SHALL maintain strict separation from the primary query layer. When `apply_view()` returns None (spool miss or DuckDB failure), the route SHALL return HTTP 410 `cache_expired` without triggering any background job or inline re-execution.

**Rationale**: View endpoints only receive `query_id`; they do not have access to the original query parameters (date range, filters) required to re-dispatch the primary query. Auto-dispatch would require the route to reconstruct these parameters, violating separation of concerns.

#### Scenario: View endpoint receives miss — returns 410, does not dispatch
- **WHEN** `apply_view(query_id)` returns `None` for any domain (Type A or Type B)
- **THEN** the route SHALL return `{ success: false, error: "cache_expired" }` with HTTP 410
- **THEN** the route SHALL NOT call `execute_primary_query()` or enqueue an RQ job
- **THEN** the client is responsible for initiating re-query per its domain's Type A or Type B contract

#### Scenario: MSD detail or export misses spool — route does not enqueue recovery work
- **WHEN** an MSD detail or export route cannot resolve a valid spool for the requested canonical query
- **THEN** the route SHALL return HTTP 410 `cache_expired`
- **THEN** the route SHALL NOT call `ensure_analysis_background_job()` or any equivalent enqueue helper
