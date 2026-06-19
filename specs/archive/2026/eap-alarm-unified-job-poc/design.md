# Design: eap-alarm-unified-job-poc

## 1. Architecture Summary
First-in-class POC migrating `run_eap_alarm_query_job` onto the P0 `BaseChunkedDuckDBJob`
template method. A new `EapAlarmJob` subclass owns `pre_query` (parse date/machines,
build time chunks, resolve the unchanged coarse spool key), `build_chunk_sql` (the
existing event + detail Oracle SQL, restricted to a per-chunk `LAST_UPDATE_TIME`
window), and `post_aggregate` (the existing SET/CLEAR pairing + `COPY TO` the same
spool path). Chunk Oracle fetches run in parallel via the base ThreadPoolExecutor;
each chunk acquires/releases its own connection inside `OracleArrowReader.chunk_iter`.
A new `EAP_ALARM_USE_UNIFIED_JOB` flag (default off) gates new-vs-legacy worker
selection at enqueue time. The unified enqueue entry-point replaces the route's
direct `enqueue_job` (Pattern B) and the registry `should_enqueue` (Pattern A) with a
single function carrying `always_async`/`sync_fallback_allowed` flags. This record
settles: (D1) the template contract incl. the ADR-0003 reduction-flag decision,
(D2) time-chunk decomposition with cross-chunk SET/CLEAR safety, (D3) the unified
enqueue + 503 decision tree, (D4) flag gating, (D5) connection lifecycle, (D6) the
parity-test template for all P2+ migrations. The spool parquet schema, spool key, and
all view endpoints are explicit non-goals and stay byte-for-row identical.

## 2. Affected Components
| component | file path | nature of change |
|---|---|---|
| EapAlarmJob (new) | `src/mes_dashboard/workers/eap_alarm_worker.py` | add `EapAlarmJob(BaseChunkedDuckDBJob)`; keep legacy `run_eap_alarm_query_job`; new flag-selected `worker_fn` entry |
| Job registry | `src/mes_dashboard/services/job_registry.py` | add `always_async: bool=False`, `sync_fallback_allowed: bool=True` to `JobTypeConfig` |
| Async enqueue | `src/mes_dashboard/services/async_query_job_service.py` | add unified `enqueue_query_job(...)` entry-point implementing the 503 decision tree; reuses `enqueue_job_dynamic` |
| Route dispatch | `src/mes_dashboard/routes/eap_alarm_routes.py` | read flag; ON → unified entry-point + `EapAlarmJob`; OFF → unchanged legacy path |
| Feature flag | `src/mes_dashboard/core/feature_flags.py` (helper, no edit) / `config/settings.py` | resolve `EAP_ALARM_USE_UNIFIED_JOB` (default off) |
| Env contract | `contracts/env/env-contract.md`, `.env.example`, `env.schema.json` | register flag, default `off`; pinned by env test (owned by contract-reviewer) |
| Business rules | `contracts/business/business-rules.md` | document unified routing + `always_async`⇒503-on-forced-sync (owned by contract-reviewer) |
| Service / cache | `src/mes_dashboard/services/eap_alarm_service.py`, `eap_alarm_cache.py` | no change (views + spool key unchanged) |

## 3. Key Design Decisions

**D1 — Template-method contract for EapAlarmJob**
- Override the three abstract hooks: `pre_query()` (populate `self._chunks`, resolve
  spool key via `make_eap_alarm_spool_key` — unchanged), `build_chunk_sql(chunk_params)`
  (returns `(sql, binds)` for one time window; event + detail are two SQL texts so
  `pre_query` must emit two chunk-kinds, see D2), `post_aggregate(job_duckdb_path)`
  (run the existing `_PAIR_SQL` and `COPY TO` the existing spool path). Class attrs:
  `namespace="eap_alarm"`, `chunk_strategy=ChunkStrategy.TIME`, `max_parallel=3`.
- Legal flag values (hard constraint): `chunk_strategy=TIME`, domain is in
  `_ALWAYS_ASYNC_DOMAINS` so routing-level `always_async=True`,
  `requires_cross_chunk_reduction=False`.
- **ADR-0003 applicability — non-obvious, must read carefully.** Row-level alarm
  events are safe to time-chunk, so ADR-0003 (cross-row reduction exclusion) does NOT
  force `SINGLE` strategy. BUT the SET/CLEAR pairing (`_PAIR_SQL`) IS a cross-row join
  on `(EQP_ID, ALARM_ID)` where a SET and its later CLEAR can fall in DIFFERENT time
  chunks. Setting `requires_cross_chunk_reduction=False` is therefore only correct
  because `post_aggregate` re-reads ALL chunk parquets together (one DuckDB
  `read_parquet(glob)`) and does the pairing there — the pairing is NOT done per-chunk.
  The `False` value selects the base "multi-parquet, no shared writer-lock DuckDB"
  fan-out; it does NOT mean "no cross-row reduction exists". This distinction is the
  acceptance gate for AC-2 (no duplicated/missing rows across chunk seams) and the
  single most reversal-sensitive decision in this POC → see ADR below.
- Progress bracket: base `run()` emits 5 (pre_query done) → 15 (all chunks fetched)
  → 90 (post_aggregate done) → 100 (spool registered). `EapAlarmJob` overrides
  `progress_report(pct)` to call `update_job_progress(_JOB_PREFIX, ...)` (legacy used
  5/15/30/50/90/100 finer stages; coarse 4-point bracket is the accepted target).

**D2 — Time-chunk decomposition**
- `pre_query` splits `[date_from, date_to]` into fixed daily windows (1-day chunks;
  configurable cap via `max_parallel`), each carrying both the event-SQL and detail-SQL
  bind windows. Daily granularity matches the `_DATE_MIDNIGHT_RE` / `BETWEEN ... +1`
  Oracle index predicate and keeps each chunk index-driven (EA-03). Rejected:
  row-count chunking (alarm rows have no stable ROW_NUMBER key and would split pairs
  arbitrarily); single chunk (defeats the parallelism AC-3 goal).
- Each chunk task calls `OracleArrowReader.chunk_iter(sql, binds)` once per SQL inside
  the ThreadPoolExecutor — the full date range is NOT passed; the per-chunk window is.
- The two sequential legacy queries (events + detail) BOTH go through
  `OracleArrowReader` per chunk. They are independent row sources fanned out and landed
  as separate parquet sets (events_raw, detail). The EAV pivot + JOIN + pairing all
  move into `post_aggregate` DuckDB SQL (the legacy in-Python pandas EAV pivot is
  replaced by DuckDB aggregation — this is a fidelity improvement the parity test must
  pin, see D6 / Open Risks).

**D3 — Unified enqueue entry-point**
- New `enqueue_query_job(job_type, owner, params, *, sync_fallback_allowed)` in
  `async_query_job_service`, replacing the route's inline `enqueue_job` (Pattern B) and
  `enqueue_job_dynamic`'s `should_enqueue` gate (Pattern A) for eap_alarm. It looks up
  `JobTypeConfig`, reads `config.always_async`, then applies the decision tree.
- `always_async` storage: a new `JobTypeConfig.always_async` field (per-job-class attr),
  registered `True` for eap-alarm. It mirrors `_ALWAYS_ASYNC_DOMAINS` in
  `query_cost_policy` (single source per layer; registry drives enqueue, policy drives
  classify). Rejected: per-domain dict in the service (duplicates registry ownership).
- Decision tree (AC-4/AC-5):
  1. spool hit → return SYNC result (200, existing query_id). [unchanged]
  2. `always_async=True` AND async available → enqueue, return 202.
  3. `always_async=True` AND `sync_fallback_allowed=False` AND async UNavailable
     → **HTTP 503** (`SERVICE_UNAVAILABLE`, `Retry-After`), never a partial sync result.
  4. `always_async=False` AND async unavailable AND `sync_fallback_allowed=True`
     → silent sync fallback (`mode:"sync_fallback"`) — not used by eap_alarm.
  eap_alarm is case 3: `sync_fallback_allowed=False`.

**D4 — Feature flag gating**
- `EAP_ALARM_USE_UNIFIED_JOB` (default off) resolved via `resolve_bool_flag` at the
  ROUTE enqueue site (`api_eap_alarm_spool`). Route-level keeps service/worker pure and
  makes rollback a single chokepoint.
- Flag OFF → the exact current code path: `enqueue_job(... worker_fn=run_eap_alarm_query_job ...)`.
  Zero change to legacy behavior (AC-8).
- Flag ON → unified `enqueue_query_job("eap-alarm", ...)` dispatching `EapAlarmJob.run`.
- Parity is structural, not behavioral: both paths call `make_eap_alarm_spool_key`
  (identical key), write to `get_eap_alarm_spool_path` (identical path), and emit the
  same parquet columns via the same `_PAIR_SQL` projection. No `_SCHEMA_VERSION` bump
  (ADR-0008) → a warm spool written by either path is readable by the other.

**D5 — Connection lifecycle under ThreadPoolExecutor**
- Each chunk task opens its own Oracle connection via `OracleArrowReader.chunk_iter`,
  which `self._pool.acquire()`s one connection per call.
- `finally: conn.close()` lives INSIDE `chunk_iter` (the base/reader, not EapAlarmJob),
  returning the connection to the pool on success or exception (AC-6).
- On a chunk exception, base `_fan_out_*` re-raises after `as_completed`; each in-flight
  generator's own `finally` still runs as its thread unwinds, so sibling connections are
  released independently. No partial parquet is registered because `register_spool_file`
  only runs after `post_aggregate` returns — a failed chunk aborts before registration.

**D6 — New-vs-old equivalence-test strategy (template for P2+)**
- Parity assertion (AC-1): same parquet **schema** (column names + types) AND same
  **rowcount** AND same **row-set content** (order-insensitive set equality on the
  business key `(EQP_ID, ALARM_ID, ALARM_START)`), for the same `(date_from, date_to,
  machines)`. Full row-set equality (not schema+count only) is required because the
  EAV-pivot moves from pandas to DuckDB SQL (D2) — a count-only test would miss a
  pairing regression.
- Fixtures: unit tier uses a mocked `OracleArrowReader.chunk_iter` returning fixed
  Arrow batches that straddle a chunk seam (a SET in chunk-1, its CLEAR in chunk-2) to
  prove cross-seam pairing. Integration tier (`test_eap_alarm_rq_async`,
  `test_oracle_arrow_pool_lifecycle`) runs both worker_fns against the same seeded
  Oracle/spool and diffs the two parquets directly.
- This dual-tier (mock-seam unit + real-path integration parquet diff) is the
  acceptance template every later domain migration (P2+) must reproduce.

## 4. Migration / Rollback Strategy
- Flag OFF (default): legacy `run_eap_alarm_query_job` untouched; zero migration cost;
  both code paths coexist through the P1–P4/P5 window (AC-8 is a standing gate).
- Flag ON: `EapAlarmJob` path active. Because the spool key/path/schema are identical,
  switching the flag mid-flight is safe — a query enqueued under one path is served from
  the same warm spool by the other.
- Rollback runbook: set `EAP_ALARM_USE_UNIFIED_JOB=off`, restart RQ workers. No parquet
  cleanup and no `_SCHEMA_VERSION` bump (schema is identical — ADR-0008 cleanup clause
  does NOT trigger). Orphan `{job_id}.duckdb` files (only created if a future
  reduction-path variant is used) are TTL-swept under `DUCKDB_JOB_DIR`; for the
  `requires_cross_chunk_reduction=False` path no job-temp DuckDB is created.

## 5. Open Risks / Deferred Decisions
- **R1 (high): `_fan_out_append` is incomplete in P0.** The base
  `_fan_out_append` (reduction=False) fetches batches then DISCARDS them
  (`list(self._fetch_chunk(cp))` with no sink) — it relies on a subclass mechanism that
  does not yet exist. `EapAlarmJob` MUST provide the per-chunk parquet sink (override
  `chunk_to_duckdb` or a new append hook) AND a `post_aggregate` that globs all chunk
  parquets for pairing. The implementation-planner must decide whether to (a) override
  in `EapAlarmJob` only, or (b) extend the base. Recommendation: extend the base
  minimally (write each batch to `{job_dir}/{job_id}/chunk-N.parquet`) so the pattern is
  reusable by P2 production_history — but that base edit is owned by backend-engineer,
  not this design. Flagged for the planner.
- **R2 (medium): cross-chunk pairing correctness.** SET/CLEAR spanning a chunk seam is
  only safe if `post_aggregate` reads ALL chunk parquets together. A CLEAR whose SET is
  outside the queried window is already dropped by legacy semantics; daily chunking must
  not change that boundary behavior. Pinned by the D6 seam fixture.
- **R3 (low): progress granularity regression.** Legacy emits 6 progress stages; coarse
  4-point bracket is intentional (AC progress requirement) but the frontend poller must
  tolerate fewer intermediate stages. No frontend change in scope; confirmed by E2E.
- **Deferred to implementation-planner:** exact daily-chunk count cap; whether the base
  append path is extended vs subclass-overridden (R1); whether `JobTypeConfig` gains
  `sync_fallback_allowed` as a field or it is a per-call arg (this design recommends a
  per-call arg with `always_async` as the registry field).
- No Context Expansion Request needed — all decisions were settled within the manifest's
  Allowed Paths.

## ADR
An ADR is warranted: `requires_cross_chunk_reduction=False` for a domain that performs
a genuine cross-row SET/CLEAR reduction is a non-obvious, reversal-sensitive boundary
decision. See `docs/adr/0009-eap-alarm-cross-chunk-pairing-in-post-aggregate.md`.
