# Yield Alert Center Rollout Runbook

## Feature Flag

- Flag: `YIELD_ALERT_CENTER_ENABLED`
- Default: `true` (in current implementation)
- Disable immediately (rollback): set `YIELD_ALERT_CENTER_ENABLED=false` and reload service.

## Required Routes / Assets

- Route: `/yield-alert-center`
- Shell route: `/portal-shell/yield-alert-center`
- Frontend dist asset: `yield-alert-center.js`

## Backend Query Guardrails

- `YIELD_ALERT_MAX_QUERY_DAYS` (default `93`)
- `YIELD_ALERT_DEFAULT_PER_PAGE` (default `50`)
- `YIELD_ALERT_MAX_PER_PAGE` (default `200`)
- `YIELD_ALERT_CACHE_TTL_SECONDS` (default `300`)
- `YIELD_ALERT_LINKAGE_WARN_RATIO` (default `0.25`)

Recommended initial production setup:

- `YIELD_ALERT_MAX_QUERY_DAYS=31`
- `YIELD_ALERT_MAX_PER_PAGE=100`
- `YIELD_ALERT_CACHE_TTL_SECONDS=300`
- `YIELD_ALERT_LINKAGE_WARN_RATIO=0.25`

## Rollout Steps

1. Deploy backend and frontend with route registered.
2. Verify `/api/yield-alert/summary`, `/api/yield-alert/trend`, `/api/yield-alert/alerts` return 200 in staging.
3. Verify drilldown endpoint returns `launch_href` and `match_status`.
4. Open `/portal-shell/yield-alert-center` and run a 7-day query.
5. Observe logs:
   - cache hit/miss (namespace + key)
   - linkage quality (`matched/partial/unmatched`, `unmatched_ratio`)
6. Expand date window gradually after baseline latency is acceptable.

## Rollback Strategy

1. Set `YIELD_ALERT_CENTER_ENABLED=false`.
2. Reload/restart workers.
3. Confirm `/api/yield-alert/*` returns disabled/404 response.
4. Existing Reject History flow remains unaffected.

## Operational Tuning Notes

- If Oracle latency rises, reduce:
  - `YIELD_ALERT_MAX_QUERY_DAYS`
  - `YIELD_ALERT_MAX_PER_PAGE`
- If repeated queries are common, increase `YIELD_ALERT_CACHE_TTL_SECONDS` cautiously.
- If linkage warning appears too often, inspect reason normalization map and unmatched workorder formats.
