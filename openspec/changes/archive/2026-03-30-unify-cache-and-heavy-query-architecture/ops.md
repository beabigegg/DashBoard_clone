# Operational Notes: Unified Cache & Heavy-Query Architecture

## New Environment Variables

| Variable | Default | Purpose |
|---|---|---|
| `REDIS_CONTROL_URL` | `REDIS_URL` | Redis URL for control-plane (locks, job meta, inflight state). Point to a `noeviction` Redis when running separate instances. |
| `DUCKDB_MEMORY_LIMIT` | `512MB` | Per-connection DuckDB memory cap (env, applied by `create_heavy_query_connection()`). |
| `DUCKDB_THREADS` | `2` | Per-connection DuckDB thread count. |
| `ANOMALY_DETECTION_SCHEDULE_HOUR` | `8` | Hour (0–23) at which daily anomaly refresh runs. |

## Redis Configuration Guidance

### Single-instance deployments (REDIS_CONTROL_URL == REDIS_URL)
No change required. Both planes share the same instance. Recommended config:

```
maxmemory-policy volatile-lru
```

This evicts only keys WITH a TTL under memory pressure. Control-plane keys (locks, job meta HSET) are excluded from eviction because they have an explicit TTL set by the application for anti-deadlock / auto-cleanup purposes — not for cache eviction.

### Dual-instance deployments (recommended for production under memory pressure)

```
# Cache Redis (REDIS_URL) — evictable spool metadata, snapshot data
maxmemory 2gb
maxmemory-policy allkeys-lru

# Control Redis (REDIS_CONTROL_URL) — locks, job status, inflight state
maxmemory 256mb
maxmemory-policy noeviction
```

Set `REDIS_CONTROL_URL` to a different Redis instance or DB for the control plane.

## Rollout Steps

1. Deploy new code — all changes are backward-compatible with old Redis keys.
2. Set `REDIS_CONTROL_URL` in environment (optional; defaults to `REDIS_URL`).
3. Monitor `heavy_query_telemetry` endpoint for spool hit/miss ratios.
4. Verify anomaly detection scheduler logs show "Source spool missing: … skipping" (not Oracle queries) when source spools are absent at startup.

## Rollback

All changes use additive patterns (new spool namespaces, new helper functions). To rollback:
1. Revert `trace_job_service.py`, `trace_lineage_job_service.py` to pre-spool versions.
2. Old Redis chunk keys (`trace:job:*:result:*`) are still read by the fallback path in `_get_chunked_result`.
3. Remove `REDIS_CONTROL_URL` from env — reverts to single-client behavior.

## Verification

```bash
# Check spool hit/miss ratio
curl http://localhost:5000/api/internal/telemetry/heavy-query

# Confirm trace events result manifest has query_id (spool-backed)
redis-cli hgetall mes_wip:trace:job:<job_id>:meta

# Confirm result manifest has no chunk keys (only lightweight manifest)
redis-cli keys "mes_wip:trace:job:<job_id>:result:*"
# Should return only: ...:result:meta  and optionally ...:result:aggregation
# Should NOT return: ...:result:<domain>:0, ...:result:<domain>:1, etc.

# Verify anomaly scheduler logs (no Oracle calls at startup)
grep "anomaly_detection_scheduler" app.log | grep -v "querying Oracle"
```
