## ADDED Requirements

### Requirement: WIP snapshot behavior SHALL define the baseline contract for realtime snapshot-plane datasets
The WIP cache contract SHALL act as the baseline for other realtime snapshot-plane datasets that are refreshed in the background and shared across workers through Redis.

#### Scenario: Snapshot-plane baseline
- **WHEN** another realtime dataset is normalized to the snapshot plane
- **THEN** it SHALL follow the same baseline pattern as WIP: background refresh, Redis-backed canonical payload, canonical metadata keys, and no legacy secondary payload representation

### Requirement: WIP snapshot retention SHALL remain decoupled from request-worker memory ownership
WIP freshness SHALL be governed by background refresh cadence and Redis retention, not by long-lived worker-owned full snapshot caches.

#### Scenario: Request reads WIP snapshot
- **WHEN** a worker serves a request using WIP data
- **THEN** it MAY parse the canonical Redis snapshot for request handling
- **THEN** the worker SHALL not become the long-lived authoritative owner of the full WIP snapshot in gunicorn process memory

#### Scenario: TTL and refresh alignment
- **WHEN** WIP uses a periodic background refresh cadence
- **THEN** the Redis retention window SHALL be longer than a single refresh interval
- **THEN** expiration SHALL act as a safety valve for stale data rather than the primary freshness mechanism
