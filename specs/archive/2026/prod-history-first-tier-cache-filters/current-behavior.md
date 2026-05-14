---
change-id: prod-history-first-tier-cache-filters
schema-version: 0.1.0
last-changed: 2026-05-14
risk: high
tier: 1
---

# Current Behavior — Production History filter flow (pre-change snapshot)

Factual snapshot of today's filter pipeline. All citations are `path:line` against `main` at this change's start.

## First-tier (Type-only, mandatory)

- User must pick at least one `pj_types` value before the Query button is enabled.
  - Service rejects empty list: `production_history_service.py:88-90` (`raise ValueError("必要參數: pj_types（至少一個）")`).
- `pj_types` options for the MultiSelect are served from `container_filter_cache.get_pj_types()`.
  - Cache file: `container_filter_cache.py`.
  - SQL is a single UNION ALL covering PRODUCTLINENAME + PJ_TYPE: `container_filter_cache.py:44-52`.
  - Layout: two flat distinct lists (`packages`, `pj_types`) in a single Redis JSON blob at key
    `container_filter_cache:data` (`container_filter_cache.py:27`).
  - L1 = in-process dict guarded by `threading.Lock`; L2 = Redis JSON with TTL `CACHE_TTL_FILTER_GENERAL`
    (`container_filter_cache.py:33-39, 169-184`).
  - No schema-version field on the payload — readers blindly `dict.get("packages", [])`.
  - No multi-worker file lock; concurrent first-touch refreshers all run the Oracle UNION query.
- Frontend renders `Type` MultiSelect in row 1 of the filter panel: `production-history/App.vue:142-150`.

## Second-tier (supplementary, post-query)

Only rendered after a query has returned a `datasetId` (`App.vue:163 v-if="datasetId"`).

Six chips, all driven from the spool (DuckDB `compute_filter_options`) — values come from rows already returned:

| chip | column-of-record | source |
|---|---|---|
| 工單號 (`work_orders`) | `MFGORDERNAME` | spool |
| LOT ID (`lot_ids`) | `CONTAINERNAME` | spool |
| Package (`packages`) | `PRODUCTLINENAME` | spool |
| BOP (`bop_codes`) | `PJ_BOP` | spool |
| WorkCenter 群組 (`workcenter_groups`) | derived from `WORKCENTERNAME` via group config | spool + config |
| Equipment (`equipment_ids`) | `EQUIPMENTNAME` | spool |

Endpoint: `POST /api/production-history/options` (`production_history_routes.py:342-373`).
Frontend handler: `App.vue:163-230`, composable `useProductionHistory.ts`.
No `FIRSTNAME` (Wafer LOT) and no `PJ_FUNCTION` filters exist today.

## Main-query filter composition

- `validate_query_params` (`production_history_service.py:82-136`) normalizes `pj_types` (required)
  plus optional lists: `lot_ids`, `work_orders`, `packages`, `bop_codes`, `workcenter_groups`,
  `workcenter_names`, `equipment_ids`. Every list is a plain `IN (...)` set — no wildcard support.
- `_build_extra_filters` (`production_history_service.py:141-193`) emits `AND <cond>` fragments via
  `QueryBuilder.add_in_condition()` (`sql/builder.py:82-101`). Output is interpolated into
  `main_query.sql` at the `{{ EXTRA_FILTERS }}` placeholder (`sql/production_history/main_query.sql:46`).
- All values are bound as named oracledb parameters via `QueryBuilder._next_param()` — no string
  concatenation of user input.

## Wildcard / multi-line precedent (not used here today)

- `material_trace_service._normalize_wildcard_token` translates `*` → `%`, escapes via `ESCAPE '\'`,
  splits exact vs pattern tokens, and emits a mixed `IN + LIKE` OR-group (`material_trace_service.py:75-117`).
- Frontend `parseMultiLineInput` (`frontend/src/core/reject-history-filters.ts:234-250`) splits on
  newline/comma, trims, replaces `*` → `%`, deduplicates. Already used by `material-trace/App.vue:5,46`.
- Production History does **not** wire either pattern today.

## Multi-worker startup behavior

- `container_filter_cache.init()` is called once at app startup (`container_filter_cache.py:59-62`).
- There is no inter-process lock. If two gunicorn workers boot simultaneously and Redis is cold,
  both will independently run the Oracle UNION query — small thundering-herd risk on cold deploy.
- Precedent for multi-worker lock exists in `resource_history_duckdb_cache.py:44-65` (file-based
  `O_CREAT|O_EXCL` sentinel + 90 s polling).

## Known gaps relative to the requested change

1. No first-tier MultiSelect for Package / BOP / Function / Wafer LOT.
2. No multi-line + wildcard textarea for 工單號 / LOT ID / Wafer LOT.
3. `PJ_FUNCTION` is selected by `main_query.sql:28` but never filtered.
4. Cache cannot answer cross-filter questions ("given Package=X, which BOPs co-occur?") — the cache
   stores flat distinct lists, not the 4-tuple co-occurrence set.
5. No cache schema-version field — a future layout change cannot be rolled back without a manual
   `DEL` of the Redis key.
