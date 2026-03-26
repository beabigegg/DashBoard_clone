# Rollout Notes — Frontend View Compute Offload

## Feature-Flag Defaults

| Flag | Default | Scope |
|---|---|---|
| `RESOURCE_HISTORY_LOCAL_COMPUTE_ENABLED` | `true` | Backend: controls `spool_download_url` injection in resource-history responses |
| `HOLD_HISTORY_LOCAL_COMPUTE_ENABLED` | `true` | Backend: controls `spool_download_url` injection in hold-history responses |
| `RESOURCE_SPOOL_THRESHOLD` | `5000` | Minimum row count before local compute URL is injected |
| `HOLD_SPOOL_THRESHOLD` | `5000` | Same, for hold history |

**Recommended rollout order:**
1. Deploy with both flags set to `false` (safe, no behavior change — pages continue using server `/view`)
2. Enable `HOLD_HISTORY_LOCAL_COMPUTE_ENABLED=true` in staging; verify parity tests pass
3. Enable `RESOURCE_HISTORY_LOCAL_COMPUTE_ENABLED=true` in staging; verify parity tests pass
4. Enable both in production during low-traffic window; monitor Flask `/view` call rates
5. Lower thresholds if desired to activate for more queries

## Rollback Procedure

Rollback is instant and zero-downtime:

1. Set `RESOURCE_HISTORY_LOCAL_COMPUTE_ENABLED=false` and/or `HOLD_HISTORY_LOCAL_COMPUTE_ENABLED=false` in environment
2. Reload Gunicorn workers (`kill -HUP <gunicorn_pid>` or `./scripts/start_server.sh reload`)
3. Both pages immediately revert to full server-side `/view` behavior
4. No database migration, schema change, or client-side cache clearing needed

## What Changes with Flags Enabled

- Backend `POST /query` and `GET /view` responses for resource-history/hold-history gain three new optional fields:
  - `spool_download_url` — URL to download the Parquet spool (only when row_count ≥ threshold)
  - `total_row_count` — Dataset size (always injected when spool exists)
  - `resource_metadata` (resource-history) or `workcenter_mapping` (hold-history) — dimension lookup for local compute
- Frontend: after a successful primary query, if all activation gates pass, the page downloads the Parquet spool and switches to browser-side DuckDB computation for all subsequent filter/granularity/pagination interactions
- The server `/view` endpoint continues to exist and is used as the fallback path

## Activation Gates (client-side)

Local compute will **not** activate if any of the following are true:
- `spool_download_url` is absent from the server response
- `total_row_count < threshold` (dataset too small; server view is cheaper)
- Browser does not support `Worker` + `WebAssembly`
- Parquet download fails (network error, timeout, HTTP 4xx/5xx)
- `flagEnabled` is `false` (can be extended to per-user or per-session disabling)

## Fallback Semantics

| Trigger | Action |
|---|---|
| Parquet download failure | Deactivate DuckDB; use server `/view` for current and all future interactions |
| DuckDB query throws | Deactivate DuckDB; use server `/view` |
| `/view` returns `cache_expired` | Deactivate DuckDB; re-run primary `POST /query` with last committed filters |
| HTTP 410 during pagination | Deactivate DuckDB; re-run primary `POST /query` |

## Parity Verification

Tests in:
- `tests/test_frontend_resource_history_parity.py` — DuckDB SQL vs Pandas for KPI, trend, per-resource aggregations
- `tests/test_frontend_hold_history_parity.py` — DuckDB SQL vs Pandas for reason_pareto, duration, list ordering
- `frontend/tests/local-compute-activation-policy.test.js` — activation gate logic, threshold behavior

Run parity tests after any change to either the Python derivation functions or the frontend SQL in the composables.

## Monitoring

After enabling in production, watch:
- Flask `/api/resource/history/view` and `/api/hold-history/view` request rates — expect a drop proportional to the fraction of large-dataset queries
- Browser console for `[resource-history]`/`[hold-history]` warnings indicating fallback events
- Gunicorn worker RSS usage — should decrease as more supplementary interactions are handled client-side
