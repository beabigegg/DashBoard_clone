## ADDED Requirements

### Requirement: Today-snapshot API SHALL provide current hold state and today-local events

A new `POST /api/hold-history/today-snapshot` endpoint SHALL return a unified snapshot combining "all lots currently on hold" and "today-local hold/release events", anchored on server SYSDATE with the existing 07:30 shift boundary.

#### Scenario: Today-snapshot endpoint contract

- **WHEN** `POST /api/hold-history/today-snapshot` is called with optional `{ hold_type, record_type, reason, duration_range, page, per_page }`
- **THEN** the service SHALL derive "today" as the shift-adjusted date from server `SYSDATE` using the 07:30 rule (same as `base_facts.sql`)
- **AND** the service SHALL read/write a dedicated cache namespace `hold_today:*` with TTL `HOLD_TODAY_CACHE_TTL_SECONDS` (default 60)
- **AND** the response SHALL return `{ success: true, data: { query_id, summary, reason_pareto, duration, list } }`
- **AND** the response SHALL NOT include a `trend` field (trend has no meaning for a single day)
- **AND** `query_id` SHALL be returned for idempotency and cache debug, even though no `/view` follow-up is required

#### Scenario: Summary card values

- **WHEN** the snapshot is computed
- **THEN** `summary` SHALL include:
  - `onHoldTotalCount`: count of lots with `RELEASETXNDATE IS NULL` (any hold_day)
  - `onHoldTotalQty`: sum of QTY for the same set
  - `todayNewQty`: sum of QTY where `hold_day = today`
  - `todayReleaseQty`: sum of QTY where `release_day = today`
  - `todayFutureHoldQty`: sum of QTY where `hold_day = today AND FUTUREHOLDCOMMENTS IS NOT NULL` (interpretation (a) — naive "filled today")
  - `onHoldAvgHours`: `AVG(HOLD_HOURS) WHERE RELEASETXNDATE IS NULL`
  - `onHoldMaxHours`: `MAX(HOLD_HOURS) WHERE RELEASETXNDATE IS NULL`
- **AND** all values SHALL be numeric (rounded to 2 decimal places where applicable) or 0 when no matching rows exist
- **AND** the service SHALL apply the `hold_type` filter before computing these values (defaulting to `quality` if not provided, matching existing behavior)

#### Scenario: Record Type semantics in today mode

- **WHEN** `record_type` filter is provided
- **THEN** `on_hold` SHALL filter to `RELEASETXNDATE IS NULL` with no hold_day restriction
- **THEN** `new` SHALL filter to `hold_day = today`
- **THEN** `release` SHALL filter to `release_day = today`
- **THEN** multiple values SHALL be OR-combined (same as existing query API)
- **AND** the filter SHALL apply uniformly to `reason_pareto`, `duration`, and `list`

#### Scenario: Data volume limits

- **WHEN** the snapshot would return more than 10000 lots for `on_hold` (configurable via `HOLD_TODAY_MAX_SNAPSHOT_ROWS`)
- **THEN** the response SHALL include `_meta: { truncated: true, total_before_limit: N, limit_applied: 10000 }`
- **AND** the list / pareto / duration SHALL be computed on the truncated set
- **AND** the client SHALL surface a warning to the user

#### Scenario: Cache miss fallback

- **WHEN** the dedicated cache is empty and Oracle is unavailable (circuit open)
- **THEN** the response SHALL return `{ success: false, error: "database_unavailable" }` with HTTP 503
- **AND** the frontend SHALL retain the previously rendered snapshot (if any) and display a stale-data warning

#### Scenario: Timezone anchoring

- **WHEN** computing "today" from `SYSDATE`
- **THEN** the calculation SHALL rely on Oracle DBTIMEZONE being `+08:00` (verified during design)
- **AND** no client-side date SHALL be used to determine the "today" boundary
- **AND** the 07:30 shift rule SHALL apply consistently (a call at 07:15 sees yesterday-as-today; a call at 07:30 sees today-as-today)

### Requirement: Today-snapshot API SHALL integrate with CI/CD regression gates

The new endpoint SHALL be covered by every relevant CI gate that already protects hold-history: real-infra-smoke (Stage 4a+), route fuzz, released-pages hardening, soak, and stress.

#### Scenario: Real-infra-smoke dispatch includes today-snapshot

- **WHEN** the real-infra-smoke pre-merge gate runs via `workflow_dispatch`
- **THEN** the smoke harness SHALL include `POST /api/hold-history/today-snapshot` in its dispatched endpoint list
- **AND** the smoke harness SHALL assert HTTP 200 + well-formed envelope + summary card keys present

#### Scenario: Route fuzz covers malicious input

- **WHEN** `tests/routes/test_fuzz_routes.py` runs
- **THEN** `POST /api/hold-history/today-snapshot` SHALL be included in the fuzz rotation
- **AND** malicious `hold_type`, `record_type`, `reason`, `duration_range`, `page`, `per_page` values SHALL NOT produce HTTP 5xx

#### Scenario: Soak covers auto-refresh pattern

- **WHEN** the weekly soak workflow runs
- **THEN** a scenario SHALL simulate continuous 60-second interval calls to `POST /today-snapshot` for at least 30 minutes
- **AND** Oracle connection pool SHALL remain within configured bounds
- **AND** Redis cache SHALL show stable TTL behavior
