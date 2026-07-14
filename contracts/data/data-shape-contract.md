---
contract: data
summary: Data schema, invalid-data handling, and row-level compatibility rules.
owner: application-team
surface: data
schema-version: 1.40.0
last-changed: 2026-07-14
breaking-change-policy: deprecate-2-minors
---

# Data Shape Contract — MES Dashboard

> 來源：掃描 `src/mes_dashboard/core/response.py`、`tests/test_api_contract.py`、`tests/test_field_contracts.py`（2026-05-05；prod-history-detail-raw-rows 2026-05-14 加入 §3.4）

---

## 1. API Envelope Shapes

### 1.1 Success Envelope

```json
{
  "success": true,
  "data": "<payload>",
  "meta": {
    "timestamp": "<ISO 8601 local>",
    "app_version": "<string>"
  }
}
```

- `meta.app_version` 由 `success_response()` 自動注入（`APP_VERSION` env 或 package metadata）。
- 額外 meta 欄位（`cache_state`、`pagination`、`cached`）為 additive，不算 breaking change。

### 1.2 Error Envelope

```json
{
  "success": false,
  "error": {
    "code": "<ERROR_CODE>",
    "message": "<user-facing string>",
    "details": "<dev-only string | omitted in production>"
  },
  "meta": {
    "timestamp": "<ISO 8601 local>",
    "app_version": "<string>"
  }
}
```

### 1.3 Async Job 202 Response

```json
{
  "success": true,
  "data": {
    "async": true,
    "job_id": "<uuid string>",
    "status_url": "/api/job/<job_id>?prefix=<namespace>",
    "query_id": "<string | optional>",
    "dataset_id": "<string | optional>"
  },
  "meta": { "timestamp": "...", "app_version": "..." }
}
```

### 1.4 Async Job Status Response

```json
{
  "success": true,
  "data": {
    "status": "queued | started | finished | failed | abandoned",
    "job_id": "<string>",
    "result": "<payload | null>",
    "error": "<string | null>",
    "pct": "<float 0.0–100.0 | omitted>",
    "stage": "<string | omitted>"
  },
  "meta": { "timestamp": "...", "app_version": "..." }
}
```

- `pct`: optional float, range `[0.0, 100.0]`; present only when the backend job service calls `update_job_progress(pct=...)`. Omitted (not `null`) when the job was enqueued by a service that does not emit progress milestones.
- `stage`: optional string; human-readable stage label emitted alongside `pct`; omitted when not set.
- These fields are additive — existing consumers that do not read them are unaffected.
- Frontend `JobStatusResponse` interface in `useAsyncJobPolling.ts` must declare `pct?: number` and `stage?: string` to match this shape.
- **downtime query jobs**: `status_url = /api/job/<job_id>?prefix=downtime`. After `status=finished`, read `result.query_id` to load `base_events` and `job_bridge` spools atomically (DA-11; §3.14).

---

## 2. Common Query Result Shapes

### 2.1 Paginated List

```json
{
  "success": true,
  "data": {
    "query_id": "<string>",
    "list": [ "<row objects>" ],
    "pagination": {
      "page": 1,
      "per_page": 50,
      "total_count": 1234,
      "total_pages": 25
    }
  },
  "meta": { "timestamp": "...", "app_version": "..." }
}
```

### 2.2 Summary + Detail Pattern（resource-history、hold-history）

```json
{
  "success": true,
  "data": {
    "query_id": "<string>",
    "summary": { "<module-specific KPIs>" },
    "detail": [ "<row objects>" ]
  },
  "meta": { "timestamp": "...", "app_version": "..." }
}
```

### 2.3 Hold-History Today Snapshot

```json
{
  "success": true,
  "data": {
    "query_id": "<string>",
    "summary": {
      "onHoldLots": 0,
      "onHoldQty": 0,
      "todayNewQty": 0,
      "todayReleaseQty": 0,
      "todayFutureHoldQty": 0,
      "repeatQualityHoldQty": 0,
      "onHoldAvgHours": 0.0,
      "onHoldMaxHours": 0.0
    },
    "reason_pareto": [ "<pareto rows>" ],
    "duration": {
      "items": [
        { "range": "<string>", "count": 0, "qty": 0, "pct": 0.0 }
      ],
      "avgReleasedHours": 0.0,
      "avgOnHoldHours": 0.0,
      "maxReleasedHours": 0.0,
      "maxOnHoldHours": 0.0
    },
    "list": [ "<lot rows>" ]
  }
}
```

### 2.5 WIP Filter-Options Response（`/api/wip/meta/filter-options`）

```json
{
  "success": true,
  "data": {
    "workorders":   ["<string>"],
    "lotids":       ["<string>"],
    "packages":     ["<string>"],
    "types":        ["<string>"],
    "firstnames":   ["<string>"],
    "waferdescs":   ["<string>"],
    "workflows":    ["<string>"],
    "bops":         ["<string>"],
    "pjFunctions":  ["<string>"]
  },
  "meta": { "timestamp": "...", "app_version": "..." }
}
```

- `workflows`、`bops`、`pjFunctions` 為 additive 新增欄位（wip-hold-drilldown-filters）。
- 各欄位均為 distinct 排序字串陣列；若無符合值則回傳 `[]`。
- 支援 cross-filter 語意：選取某過濾器時，其他欄位選項自動縮減至對應可選值。
- 接受可選查詢參數 `workflow`、`bop`、`pj_function` 以在已選取過濾器後縮減選項。

### 2.6 Resource-History Batch Query Progress（`GET /api/resource/history/query/progress`）

Response shape for an active or completed batch query (HTTP 200):

```json
{
  "success": true,
  "data": {
    "query_id": "<uuid string>",
    "total_chunks": "<integer>",
    "completed_chunks": "<integer>",
    "percent": "<float 0.0–100.0>",
    "status": "<running | done | error>"
  },
  "meta": { "timestamp": "...", "app_version": "..." }
}
```

Constraints:
- All five `data` fields are required; the endpoint MUST NOT omit any of them in a 200 response.
- `status` is a closed enum: `running | done | error` — any other value is invalid.
- `percent` is `float`, range `[0.0, 100.0]`.
- 400 and 404 responses follow the standard error envelope (Section 1.2).
- This shape is wholly separate from the query result shape (Section 2.2); do not conflate.
- Added by change `resource-history-perf`.

### 2.7 Production-History Filter-Options Response（`GET /api/production-history/filter-options`）

Response shape for cross-filter cached options (HTTP 200):

```json
{
  "success": true,
  "data": {
    "pj_types":     ["<string>"],
    "packages":     ["<string>"],
    "bops":         ["<string>"],
    "pj_functions": ["<string>"]
  },
  "meta": {
    "timestamp":      "<ISO 8601 local>",
    "app_version":    "<string>",
    "updated_at":     "<ISO 8601 UTC>",
    "schema_version": 2
  }
}
```

Constraints:
- All four `data` arrays are required and always present (may be `[]` when nothing co-occurs with the current `selected` set).
- Each array contains distinct strings sorted ascending; duplicates MUST NOT appear.
- `meta.schema_version` is an integer; current value `2`. Bumped when the underlying cache payload schema changes.
- `meta.updated_at` reflects the last cache refresh ISO timestamp.
- `selected` query param is URL-encoded JSON; unknown keys are ignored; values not present in cache are silently dropped (fail-open picker).
- Empty `selected` (or omitted) → returns the full distinct set for each field from `container_filter_cache.indices`.
- 400 on malformed `selected` JSON; 404 on cache cold-start failure; standard error envelope (Section 1.2).
- Cross-filter semantics: given a non-empty `selected`, each field's array is narrowed to values co-occurring with the selection across the cached 4-tuple set (business-rules.md PHF-01).
- Added by change `prod-history-first-tier-cache-filters`.

### 2.8 Container Filter Cache Payload (internal — `container_filter_cache:data`)

Internal Redis L2 / in-process L1 payload that backs §2.7 filter-options responses. Documented here for cache-rebuild and rollback governance.

```json
{
  "schema_version": 2,
  "tuples": [
    ["<PJ_TYPE>", "<PRODUCTLINENAME>", "<PJ_BOP>", "<PJ_FUNCTION>"]
  ],
  "indices": {
    "pj_types":     ["<string>"],
    "packages":     ["<string>"],
    "bops":         ["<string>"],
    "pj_functions": ["<string>"]
  },
  "updated_at": "<ISO 8601 UTC>"
}
```

Constraints:
- `schema_version` is required `int`; current value `2` (was implicit `1` prior to this change). Readers MUST treat a missing or mismatched `schema_version` as a cache miss and trigger a rebuild rather than deserializing the old shape (business-rules.md PHF-04).
- `tuples` is a list of 4-element arrays in fixed positional order `[PJ_TYPE, PRODUCTLINENAME, PJ_BOP, PJ_FUNCTION]`. Each tuple represents an observed co-occurrence row from `DW_MES_CONTAINER` (`SELECT DISTINCT`).
- `indices` is a denormalised convenience map: each value is the deduplicated sorted distinct list of the corresponding column across all tuples — used to satisfy the empty-`selected` case without scanning tuples.
- `updated_at` carries the Oracle refresh timestamp; rolled forward on every successful rebuild.
- TTL governed by `CACHE_TTL_FILTER_GENERAL` (24 h).
- Rollback: bump `schema_version` → `3` in a follow-up to invalidate L2 entries on next deploy without `redis-cli DEL`.
- Multi-worker rebuild lock at `tmp/container_filter_cache.loading` (`O_CREAT|O_EXCL`); losers poll Redis L2 every 5 s up to 90 s (business-rules.md PHF-05).
- Added by change `prod-history-first-tier-cache-filters`.

### 2.9 AI Session Store Shape（`_SESSION_STORE[conversation_id]`）

Internal in-process dict extended by ai-pipeline-upgrade. Keyed by `conversation_id` (string).

```json
{
  "chat_history": [
    {"role": "user", "content": "..."},
    {"role": "assistant", "content": "..."}
  ],
  "initial_question": "...",
  "slots": { "topic": null, "intent": null, "time_scope": null },
  "updated_at": 1748476800.0
}
```

- `chat_history`: list of `{"role": "user"|"assistant", "content": string}` pairs. Cap 8 pairs / 16 messages; FIFO eviction on overflow. Key may be absent for sessions created before this change.
- TTL: 1800 s (same as slot-filling keys, set via `AI_QUERY_SESSION_TTL_SECONDS`).
- `chat_history` is preserved across the `ready_to_search` slot-filling pop.

#### AI Function Parameter Schemas (D3)

**production_history_query** (`dispatch: raw_params` — receives params as a single positional dict):
```json
{
  "start_date": "YYYY-MM-DD",
  "end_date": "YYYY-MM-DD",
  "lot_ids": ["string"],
  "pj_types": ["string"]
}
```
`start_date` and `end_date` are required. `lot_ids` and `pj_types` are optional arrays. Synchronous Oracle/spool call; latency expectation documented in business-rules AI-09.

**resource_history_summary** (standard kwargs dispatch):
```json
{
  "start_date": "YYYY-MM-DD",
  "end_date": "YYYY-MM-DD",
  "granularity": "day|week|month|year",
  "workcenter_groups": ["string"]
}
```
`start_date` and `end_date` are required. `granularity` defaults to `"day"`. `workcenter_groups` is optional. Excluded params: `families`, `resource_ids`, `is_production`, `is_key`, `is_monitor`.

**qc_gate_status** (no params):
```json
{}
```
`normalize_chart_data("qc_gate_status", raw)` returns `raw.get("stations", [])` when `raw` is a dict; otherwise passes through.


### 2.13 MSD Container-Filter-Options Response（`GET /api/mid-section-defect/container-filter-options`）

Response shape for cross-filter cached Type/Package options (HTTP 200):

```json
{
  "success": true,
  "data": {
    "pj_types":     ["<string>"],
    "packages":     ["<string>"],
    "bops":         ["<string>"],
    "pj_functions": ["<string>"]
  },
  "meta": {
    "timestamp":      "<ISO 8601 local>",
    "app_version":    "<string>",
    "updated_at":     "<ISO 8601 UTC>",
    "schema_version": 2
  }
}
```

Constraints:
- All four `data` arrays are required and always present (may be `[]` when nothing co-occurs with the current `selected` set or cache is cold).
- Each array contains distinct strings sorted ascending; duplicates MUST NOT appear.
- `meta.updated_at` and `meta.schema_version` are in `meta`, NOT in `data` (mirrors §2.7 pattern — D-CR-01).
- `meta.schema_version` is an integer; current value `2` (shared with §2.8 container_filter_cache payload).
- `bops` and `pj_functions` are returned by this endpoint but are NOT consumed by the analysis filter (AC scope is Type/Package only).
- Same Redis key and 24h TTL as §2.7 production-history filter-options (shared `container_filter_cache`).
- `selected` query param is URL-encoded JSON; unknown keys are ignored; values not present in cache are silently dropped (fail-open picker).
- 400 on malformed `selected` JSON; 500 on Oracle build error.
- Added by change `msd-type-package-filter`.

### 2.4 Truncated Payload（memory pressure guard）

Large payloads that hit the memory/row limit include:

```json
{
  "_meta": {
    "truncated": true,
    "total_before_limit": 50000,
    "limit_applied": 10000
  }
}
```

---

## 3. Required Columns（Common Row Types）

### 3.0 Spool Schema Testability Rules

**`_derive_*` column-preservation guard** (applies to all §3.x spool schemas backed by a `BaseChunkedDuckDBJob`): every `_derive_*` transform method MUST preserve all upstream spool columns that it does not explicitly compute. A hardcoded output column list that omits an upstream column silently drops it from the parquet spool and breaks AC-3 parity without any error.

Enforcement: add a `test_derive_*_preserves_<column>` unit test asserting every upstream spool column appears in the output DataFrame. This test must be added in the same commit as the `_derive_*` method.

Evidence: `downtime-duckdb-join-migration` — `_derive_job_columns` dropped `fragment_count` (§3.21); fixed by `tests/test_downtime_unified_job.py:test_derive_job_columns_preserves_fragment_count`. Added by `downtime-duckdb-join-migration`.

### 3.1 Lot Row（WIP / Hold）

| column | type | nullable | notes |
|---|---|---:|---|
| lot_id | string | no | primary identifier |
| product | string | yes | may be null for some lot types |
| qty | integer | no | — |
| location | string | yes | workcenter or step name |

#### 3.1.1 WIP Detail Lot Row（`/api/wip/detail/<workcenter>` lots array）

| column | type | nullable | notes |
|---|---|---:|---|
| lotId | string | no | LOTID |
| equipment | string | yes | EQUIPMENTS |
| wipStatus | string | yes | WIP_STATUS |
| holdReason | string | yes | HOLDREASONNAME |
| qty | integer | no | QTY |
| package | string | yes | PACKAGE_LEF |
| spec | string | yes | SPECNAME |
| pjType | string | yes | PJ_TYPE；null renders as `-` in UI（additive, wip-hold-drilldown-filters）|

### 3.2 Duration Item

| column | type | nullable | notes |
|---|---|---:|---|
| range | string | no | e.g. "0-24h", "24-72h" |
| count | integer | no | lot count in this range |
| qty | integer | no | lot quantity sum |
| pct | float | no | percentage of total |

### 3.3 Pareto Row

| column | type | nullable | notes |
|---|---|---:|---|
| reason | string | no | hold/reject reason code |
| count | integer | no | occurrence count |
| qty | integer | no | quantity sum |
| pct | float | no | running cumulative % |

### 3.4 Production-History Detail Row

One row per aggregated partial-trackout group (4-tuple `CONTAINERNAME + SPECNAME + EQUIPMENTID + TRACKINTIMESTAMP`), subject to the strict guard in business-rules.md PH-06 / PH-07. TRACKINQTY is intentionally NOT part of the key because this MES records TRACKINQTY as the qty REMAINING at each partial's start (it decreases across partials of the same upload), not the original load qty. When all non-key columns are consistent within a group, the row is a single aggregated record; when any non-key column diverges, each spool row in that group is emitted individually with `partial_count = 1`. Spool parquet schema must include all columns below (aggregation is a view-layer operation; the parquet schema is unchanged).

| column | type | nullable | notes |
|---|---|---:|---|
| CONTAINERNAME | string | no | container id; multi-partial containers produce N rows in spool but ≤ N rows after view-layer aggregation |
| PJ_TYPE | string | yes | from container |
| PJ_BOP | string | yes | from container |
| PJ_FUNCTION | string | yes | from container; pre-staged for filter use (Change 3) — present in spool, not yet a user filter |
| MFGORDERNAME | string | yes | from container |
| FIRSTNAME | string | yes | from container |
| PRODUCTLINENAME | string | yes | from container |
| WORKCENTERNAME | string | yes | from LOTWIPHISTORY row |
| SPECNAME | string | yes | from LOTWIPHISTORY row |
| EQUIPMENTID | string | yes | from LOTWIPHISTORY row |
| EQUIPMENTNAME | string | yes | from LOTWIPHISTORY row |
| TRACKINTIMESTAMP | datetime | yes | shared by the 4-tuple group; per-partial in spool, identical across all rows of one group |
| TRACKOUTTIMESTAMP | datetime | yes | aggregated row → `MAX(TRACKOUTTIMESTAMP)` of the group; raw row (strict-guard fallback) → per-partial value |
| TRACKINQTY | integer | yes | aggregated row → `MAX(TRACKINQTY)` (= original load qty before any partial trackouts); raw row → per-partial value. MES stores per-partial REMAINING qty, so spool rows of one group have DIFFERENT TRACKINQTY values — MAX recovers the original load. |
| TRACKOUTQTY | integer | yes | aggregated row → `SUM(TRACKOUTQTY)` of the group; raw row (strict-guard fallback) → per-partial value |
| partial_count | integer | no | group size; `1` for unaggregated rows (single partial or strict-guard divergence); `≥ 2` for merged partial-trackout groups. Computed by the view layer; not stored in spool parquet. |

Row-grain rule: detail row count ≤ LOTWIPHISTORY row count for matched containers — equal when no groups are merged (strict-guard fallback applies to every group, e.g. divergent `PJ_FUNCTION` within the same trackin), smaller when partial track-outs are collapsed (PH-06). Detail table UI sorts by `TRACKINTIMESTAMP` (aggregated rows use the shared group `TRACKINTIMESTAMP`). The matrix view's leaf `count` cell is computed downstream in DuckDB as `COUNT(DISTINCT CONTAINERNAME)` over the raw spool source (not the aggregated view); parent-level distinct-count semantics are specified in §3.5. Aggregated aliases `TRACKIN_TS / TRACKOUT_TS / TRACKIN_QTY / TRACKOUT_QTY` are removed; consumers must read raw column names. `partial_count` is synthesized by the view layer and is not present in the spool parquet. Added by change `prod-history-detail-raw-rows`; updated by change `prod-history-detail-partial-merge`.

### 3.5 Production-History Matrix Tree Node

The Workcenter × Equipment Matrix view returns a hierarchy of nodes, each with
the shape `{label, level, count, month_counts, children}` (`level` ∈
`workcenter | spec | equipment`). This node shape is fixed; consumers
(`frontend/src/production-history/components/ProductionMatrix.vue`) read
`count` and `month_counts` per node.

| field | type | nullable | notes |
|---|---|---:|---|
| label | string | no | node display name |
| level | string | no | closed enum: `workcenter \| spec \| equipment` |
| count | integer | no | `COUNT(DISTINCT CONTAINERNAME)` re-evaluated at this node's grain |
| month_counts | object | no | `{ "<YYYY-MM>": integer }`; each value is `COUNT(DISTINCT CONTAINERNAME)` re-evaluated at this node's grain × month |
| children | array | yes | child nodes; absent/empty at the `equipment` (leaf) level |

Distinct-count grain rule: `count` and `month_counts` at the `workcenter` and
`spec` levels are `COUNT(DISTINCT CONTAINERNAME)` **independently evaluated at
that grain** — they are **NOT** the sum of child-node `count` / `month_counts`.
Distinct counts are non-additive across hierarchy levels: one CONTAINERNAME
passing through multiple specs (or multiple equipment under one spec) must be
counted once at each ancestor node, not once per child path. The `equipment`
(leaf) grain is the directly-grouped `COUNT(DISTINCT CONTAINERNAME)` by
`(workcenter, spec, equipment, month)` and is unchanged. See business-rules.md
PH-05. Added by change `fix-matrix-distinct-count`.

### 3.6 Query-Tool Lot-History / Equipment-Lots / Adjacent-Lots Row

One row per aggregated partial-trackout group for `GET /api/query-tool/lot-history`, `POST /api/query-tool/equipment-period` (`query_type=lots`), and `GET /api/query-tool/adjacent-lots`. Aggregation semantics mirror §3.4 (PH-06 / QT-05): TRACKINQTY is NOT a key because MES stores per-partial REMAINING qty (decreasing); MAX recovers the original load qty. A strict guard (QT-06) applies: if any non-key column diverges within a group, raw rows are emitted instead, each with `partial_count = 1`.

| column | type | nullable | notes |
|---|---|---:|---|
| CONTAINERID | string | no | internal Oracle container ID |
| CONTAINERNAME | string | yes | display lot ID |
| WORKCENTERNAME | string | yes | from LOTWIPHISTORY row (absent in adjacent_lots output) |
| EQUIPMENTID | string | no | key column — part of grouping 4-tuple (lot_history, equipment_lots) or 3-tuple (adjacent_lots) |
| EQUIPMENTNAME | string | yes | non-key column |
| SPECNAME | string | yes | key column for lot_history and equipment_lots; non-key for adjacent_lots (adjacent_lots groups by 3-tuple without SPECNAME) |
| TRACKINTIMESTAMP | datetime | yes | key column — shared by all partials of one upload session |
| TRACKOUTTIMESTAMP | datetime | yes | aggregated row → `MAX(TRACKOUTTIMESTAMP)`; raw row (strict-guard fallback) → per-partial value |
| TRACKINQTY | integer | yes | aggregated row → `MAX(TRACKINQTY)` (original load qty before any partial trackouts); raw row → per-partial remaining qty |
| TRACKOUTQTY | integer | yes | aggregated row → `SUM(TRACKOUTQTY)`; raw row (strict-guard fallback) → per-partial value |
| FINISHEDRUNCARD | string | yes | from LOTWIPHISTORY row |
| PJ_WORKORDER | string | yes | from LOTWIPHISTORY row |
| PJ_TYPE | string | yes | from DW_MES_CONTAINER |
| PJ_BOP | string | yes | from DW_MES_CONTAINER |
| WAFER_LOT_ID | string | yes | FIRSTNAME from DW_MES_CONTAINER |
| PRODUCTLINENAME | string | yes | from DW_MES_CONTAINER; `null` when LEFT JOIN returns no match; Oracle CHAR trailing-space trimmed. Not present in adjacent_lots output (adjacent_lots SQL does not SELECT PRODUCTLINENAME). **Added add-package-detail-tables.** |
| RELATIVE_POSITION | integer | yes | adjacent_lots only — lot position relative to target lot (negative = before, 0 = target, positive = after) |
| partial_count | integer | no | group size; `1` for unaggregated rows (single partial or strict-guard divergence); `≥ 2` for merged partial-trackout groups. Computed by service layer; not stored in Oracle. |

**Prior behavior (before `query-tool-partial-trackout`):** `ROW_NUMBER() OVER (PARTITION BY ... ORDER BY TRACKOUTTIMESTAMP DESC) WHERE rn = 1` was used in all three SQL files. This returned only the last partial row, emitting the wrong TRACKINQTY (remaining qty of the last partial, not original load) and wrong TRACKOUTQTY (only the last partial's output, not cumulative). The `partial_count` column did not exist. Added by change `query-tool-partial-trackout`. `PRODUCTLINENAME` column added by change `add-package-detail-tables`; `_PARTIAL_NONKEY_COLS_LOT` in `query_tool_sql_runtime.py` must be extended to include `"PRODUCTLINENAME"` so the strict guard (QT-06) treats it as a non-key column.

**CSV export column order** (for `export_type=lot_history`): CONTAINERID, CONTAINERNAME, WORKCENTERNAME, EQUIPMENTID, EQUIPMENTNAME, SPECNAME, TRACKINTIMESTAMP, TRACKOUTTIMESTAMP, TRACKINQTY, TRACKOUTQTY, FINISHEDRUNCARD, PJ_WORKORDER, PJ_TYPE, PJ_BOP, WAFER_LOT_ID, **PRODUCTLINENAME**, partial_count. **CSV export column order** (for `export_type=equipment_lots`): same minus RELATIVE_POSITION, plus PRODUCTLINENAME before partial_count.

### 3.7 Query-Tool Equipment-Lot-Rejects Row

One row per reject event for `POST /api/query-tool/equipment-period` (`query_type=rejects`) and `POST /api/query-tool/export-csv` (`export_type=equipment_rejects`). Replaces the previous aggregate row shape (EQUIPMENTNAME, LOSSREASONNAME, TOTAL_REJECT_QTY, TOTAL_DEFECT_QTY, AFFECTED_LOT_COUNT) as of 2026-05-18 (`equipment-rejects-by-lots`).

**Cross-station note**: `EQUIPMENTNAME` reflects the reject event's equipment, which may differ from the queried equipment IDs (a lot processed on Furnace-A may have its reject logged under Furnace-B). This is intentional per QT-07 and not a bug. `LOTREJECTHISTORY` has no `EQUIPMENTID`; `CONTAINERID` is the only correct join key.

| column | type | nullable | notes |
|---|---|---:|---|
| CONTAINERID | string | no | internal Oracle container ID |
| CONTAINERNAME | string | yes | display lot ID |
| WORKCENTERNAME | string | yes | from LOTREJECTHISTORY row, resolved via DW_MES_SPEC_WORKCENTER_V |
| WORKCENTER_GROUP | string | yes | from DW_MES_SPEC_WORKCENTER_V |
| WORKCENTERSEQUENCE_GROUP | integer | yes | from DW_MES_SPEC_WORKCENTER_V; 999 if unknown |
| PRODUCTLINENAME | string | yes | from DW_MES_CONTAINER |
| PJ_FUNCTION | string | yes | from DW_MES_CONTAINER |
| PJ_TYPE | string | yes | from DW_MES_CONTAINER |
| PRODUCTNAME | string | yes | from DW_MES_CONTAINER |
| SPECNAME | string | yes | from LOTREJECTHISTORY row |
| LOSSREASONNAME | string | yes | from LOTREJECTHISTORY row; `(未填寫)` if null |
| EQUIPMENTNAME | string | yes | reject event's equipment — may differ from queried equipment (cross-station case, see QT-07) |
| REJECTCOMMENT | string | yes | free-text comment from LOTREJECTHISTORY |
| REJECT_QTY | integer | yes | `REJECTQTY` from LOTREJECTHISTORY |
| STANDBY_QTY | integer | yes | `STANDBYQTY` from LOTREJECTHISTORY |
| QTYTOPROCESS_QTY | integer | yes | `QTYTOPROCESS` from LOTREJECTHISTORY |
| INPROCESS_QTY | integer | yes | `INPROCESSQTY` from LOTREJECTHISTORY |
| PROCESSED_QTY | integer | yes | `PROCESSEDQTY` from LOTREJECTHISTORY |
| REJECT_TOTAL_QTY | integer | yes | sum of the five qty fields above |
| DEFECT_QTY | integer | yes | `DEFECTQTY` from LOTREJECTHISTORY |
| TXN_TIME | datetime | yes | `TXNDATE` from LOTREJECTHISTORY |
| TXNDATE | datetime | yes | same as TXN_TIME |
| TXN_DAY | date | yes | `TRUNC(TXNDATE)` — date portion only |

**Prior aggregate fields removed**: `TOTAL_REJECT_QTY`, `TOTAL_DEFECT_QTY`, `AFFECTED_LOT_COUNT` — these were present in the old `equipment_rejects.sql` aggregate shape and are no longer returned. See §10 of api-contract.md for the compatibility note.

**CSV export column order** (for `export_type=equipment_rejects`): mirrors the table above — CONTAINERID, CONTAINERNAME, WORKCENTERNAME, WORKCENTER_GROUP, WORKCENTERSEQUENCE_GROUP, PRODUCTLINENAME, PJ_FUNCTION, PJ_TYPE, PRODUCTNAME, SPECNAME, LOSSREASONNAME, EQUIPMENTNAME, REJECTCOMMENT, REJECT_QTY, STANDBY_QTY, QTYTOPROCESS_QTY, INPROCESS_QTY, PROCESSED_QTY, REJECT_TOTAL_QTY, DEFECT_QTY, TXN_TIME, TXNDATE, TXN_DAY.

---

### 3.8 Admin Performance-Detail Payload（`GET /admin/api/performance-detail`）

首次記錄於 `fix-admin-dashboard`（2026-05-19）。以下 baseline keys 於首次文件化前已在 production 運行。

#### 頂層 `data` keys

| key | type | nullable | description |
|---|---|---|---|
| `redis` | object \| null | yes | Redis 監控子物件；Redis 不可達時為 `null` 或 `{"error":"..."}` |
| `duckdb` | object \| null | yes | DuckDB 監控子物件；**新增於 fix-admin-dashboard**；telemetry 不可用時為 `null` |
| `process_caches` | object | no | Process-level L1/L2 route cache 統計 |
| `route_cache` | object | no | Route cache hit/miss rates |
| `db_pool` | object | no | DB connection pool 狀態 |
| `direct_connections` | object | no | 直連（non-pool）連線數 |
| `worker_memory_guard` | object | no | Worker memory guard 狀態 |
| `heavy_query_telemetry` | object | no | Heavy query slot 使用狀態 |
| `async_workers` | object | no | RQ async worker 摘要 |
| `spool_disk_usage` | object | no | Spool temp dir 磁碟用量 |
| `redis_namespace_memory` | object \| null | yes | Redis namespace key count 分析 |

#### `data.redis` 子物件 keys

| key | type | nullable | description |
|---|---|---|---|
| `used_memory_human` | string | no | Redis 已用記憶體（human readable） |
| `used_memory` | integer | no | Redis 已用記憶體（bytes） |
| `peak_memory_human` | string | no | Redis 峰值記憶體（human readable） |
| `peak_memory` | integer | no | Redis 峰值記憶體（bytes） |
| `maxmemory_human` | string | no | Redis 上限（human readable） |
| `maxmemory` | integer | no | Redis 上限（bytes） |
| `connected_clients` | integer | no | 已連線 client 數 |
| `hit_rate` | float | no | Keyspace hit rate（0.0–1.0） |
| `keyspace_hits` | integer | no | Cache hit 累計數 |
| `keyspace_misses` | integer | no | Cache miss 累計數 |
| `namespaces` | object | no | Per-namespace key count |
| `evicted_keys` | integer | no | 記憶體壓力下被驅逐的 key 數；**新增於 fix-admin-dashboard** |
| `expired_keys` | integer | no | TTL 到期被清除的 key 數；**新增於 fix-admin-dashboard** |
| `mem_fragmentation_ratio` | float | no | 記憶體碎片率（> 1.5 表示碎片嚴重）；**新增於 fix-admin-dashboard** |
| `slowlog` | array | no | 最慢 top-5 指令列表；每筆 `{id: int, duration_us: int, command: string}`；**新增於 fix-admin-dashboard** |

#### `data.duckdb` 子物件 keys（新增於 fix-admin-dashboard）

| key | type | nullable | description |
|---|---|---|---|
| `temp_dir_bytes` | integer \| null | yes | DuckDB temp dir 目前磁碟用量（bytes）；目錄不存在時為 `null` |
| `memory_limit_state` | string \| null | yes | 設定的 memory limit（如 `"512MB"`）；不可用時為 `null` |

#### Nullability rules
- 當 `REDIS_ENABLED=false` 或 Redis client 不可達，`data.redis` 整個為 `null`（不是空物件）。
- 當 DuckDB temp dir 不可讀或 runtime 未初始化，`data.duckdb` 整個為 `null`。
- 前端對 `data.redis` 與 `data.duckdb` 的所有 key 應以 defensive optional chaining 讀取。

---

## Invalid Data Behavior

<!--
Heading MUST be exactly "## Invalid Data Behavior" (no numeric prefix) --
cdd-kit gate's ADR 0012 §2 data-shape citation resolver
(`data-shape: <condition>`) matches this heading text verbatim
(`sectionBody(body, "Invalid Data Behavior")`); a numbered heading like
"## 4. Invalid Data Behavior" silently resolves zero rows from this table,
failing every `data-shape:` citation project-wide with "no matching row"
even though the table itself is populated. Previously numbered "4." in the
surrounding §1-§7 sequence; found and fixed 2026-07-13 while unblocking
fix-equipment-lots-trim/query-tool-subtab-cache archival (ADR 0012 gate).
-->

| condition | expected behavior | error code / UI state | test |
|---|---|---|---|
| missing required column | service raises ValueError → 500 INTERNAL_ERROR | INTERNAL_ERROR | `tests/test_field_contracts.py` |
| wrong type (e.g. string qty) | type coercion or 400 VALIDATION_ERROR | VALIDATION_ERROR | `tests/test_field_contracts.py` |
| empty dataset | returns empty list `[]`; UI shows EmptyState | — | `frontend/tests/playwright/data-boundary/empty-result.spec.js` |
| non-empty dataset | returns ≥1 row; UI renders the populated row set | — | `tests/acceptance/test_fix_equipment_lots_trim_acceptance.py` |
| over max row limit | truncated; adds `_meta.truncated=true` to payload | — | `tests/test_interactive_memory_guard.py` |
| unexpected enum value | 400 VALIDATION_ERROR | VALIDATION_ERROR | `tests/routes/test_fuzz_routes.py` |
| malicious input (SQL/XSS/100k) | 400 VALIDATION_ERROR (never 500) | VALIDATION_ERROR | `tests/routes/test_fuzz_routes.py` |
| DB unavailable | 503 SERVICE_UNAVAILABLE | SERVICE_UNAVAILABLE | `tests/test_degraded_responses.py` |
| Spool expired | 410 CACHE_EXPIRED or dataset_expired | CACHE_EXPIRED | resilience tests |
| Date range > 730 days | 400 VALIDATION_ERROR | VALIDATION_ERROR | route tests |
| BondUPH/fHCM_UPH parameter returns zero rows for the requested window/family | returns empty result set (not an error); UI shows EmptyState with a family/parameter-specific message | — | `tests/integration/test_uph_performance_data_boundary.py` |

---

## 5. Export / Import Format

- **CSV export**：`Content-Type: text/csv; charset=utf-8`；`Content-Disposition: attachment; filename=<module>_<date>.csv`；header row 必須存在。
- **Parquet download**（spool）：`Content-Type: application/octet-stream`；binary Parquet format。
- **NDJSON stream**（trace）：`Content-Type: application/x-ndjson`；每行一個 JSON object。

---

### 3.9 Material-Consumption Spool Schemas

#### 3.9.1 Summary Spool (`tmp/query_spool/material_consumption/summary-*.parquet`)

One row per `(txn_date, material_part, pj_type, primary_category)` grouping. Stored at day-level granularity; the `POST /query` response and `GET /view?granularity=` response are computed by re-grouping this spool in DuckDB. The summary spool cache key **excludes** granularity — one spool file serves all three granularity views (week/month/quarter). See ADR `docs/adr/0001-material-consumption-summary-spool-granularity-key.md`.

| column | type | nullable | notes |
|---|---|---|---|
| txn_date | DATE | no | `TRUNC(DWH.DW_MES_LOTMATERIALSHISTORY.TXNDATE)` — date portion only, not datetime |
| material_part | VARCHAR | no | MATERIALPARTNAME |
| pj_type | VARCHAR | yes | `DWH.DW_MES_CONTAINER.PJ_TYPE`; null when LEFT JOIN returns no match |
| primary_category | VARCHAR | yes | PRIMARY_CATEGORY from LOTMATERIALSHISTORY; null when not applicable |
| total_consumed | FLOAT | no | `SUM(QTYCONSUMED)` for this (txn_date, material_part, pj_type, primary_category) cell |
| total_required | FLOAT | no | `SUM(QTYREQUIRED)` for this cell |
| lot_count | INT | no | `COUNT(DISTINCT CONTAINERID)` for this cell |
| workorder_count | INT | no | `COUNT(DISTINCT PJ_WORKORDER)` for this cell |

**Breaking-change surface**: any column rename, addition, or removal orphans existing files → `rm -f tmp/query_spool/material_consumption/*.parquet` required on both deploy and rollback (see ci-gate-contract.md §material-part-consumption worker gate).

#### 3.9.2 Detail Spool (`tmp/query_spool/material_consumption/detail-*.parquet`)

One row per raw lot-material event from `DWH.DW_MES_LOTMATERIALSHISTORY`, with `PJ_TYPE` joined from `DWH.DW_MES_CONTAINER`. Produced by `POST /api/material-consumption/detail`; paginated and exported via DuckDB.

| column | type | nullable | notes |
|---|---|---|---|
| CONTAINERID | CHAR | no | Batch container ID |
| CONTAINERNAME | VARCHAR | yes | LOT ID resolved via DWH.DW_MES_CONTAINER JOIN |
| PJ_WORKORDER | VARCHAR | yes | Production work order number |
| WORKCENTERNAME | VARCHAR | yes | Consumption work center |
| MATERIALPARTNAME | VARCHAR | no | Material part number |
| MATERIALLOTNAME | VARCHAR | yes | Material batch number |
| VENDORLOTNUMBER | VARCHAR | yes | Vendor/supplier batch number |
| QTYREQUIRED | FLOAT | yes | Required quantity |
| QTYCONSUMED | FLOAT | yes | Actual consumption quantity |
| EQUIPMENTNAME | VARCHAR | yes | Consumption equipment |
| TXNDATE | DATE | yes | Consumption transaction date |
| PRIMARY_CATEGORY | VARCHAR | yes | Material primary category |
| SECONDARY_CATEGORY | VARCHAR | yes | Material secondary category |
| pj_type | VARCHAR | yes | `DWH.DW_MES_CONTAINER.PJ_TYPE`; null when JOIN returns no match |
| PRODUCTLINENAME | VARCHAR | yes | `DWH.DW_MES_CONTAINER.PRODUCTLINENAME`; null when LEFT JOIN returns no match. Oracle CHAR trailing-space trimmed. **Added add-package-detail-tables.** Breaking-change surface: adding this column requires `rm -f tmp/query_spool/material_consumption/detail-*.parquet` on deploy and rollback. |

Same breaking-change surface rule as summary spool.

**Multi-worker detail spool write**: uses idempotency-check-before-write pattern from `material_trace_service.execute_to_spool()` — check `get_spool_file_path()` exists before executing Oracle query. Last-write-wins is NOT acceptable for detail (potentially slow Oracle query).

**Async threshold**: `POST /api/material-consumption/detail` is synchronous when rows ≤ `SYNC_ROW_LIMIT` (env, default 30000); async Type B (RQ queue `material-consumption`) for larger sets (business-rules.md MC-04).

---

### 3.10 Resource-Status Merged Record（`GET /api/resource/status`）

Each element in the `data` array returned by `/api/resource/status` is a merged record combining three cache layers (resource-cache, realtime-equipment-cache, workcenter-mapping). Fields are sourced and merged in `resource_service.py::get_merged_resource_status()`.

#### 3.10.1 Field table

| field | type | nullable | source | notes |
|---|---|---|---|---|
| RESOURCEID | string \| integer | no | resource-cache | Primary resource identifier |
| RESOURCENAME | string | yes | resource-cache | Display name |
| WORKCENTERNAME | string | yes | resource-cache | |
| RESOURCEFAMILYNAME | string | yes | resource-cache | |
| PJ_DEPARTMENT | string | yes | resource-cache | |
| PJ_ASSETSSTATUS | string | yes | resource-cache | |
| PJ_ISPRODUCTION | boolean | yes | resource-cache | |
| PJ_ISKEY | boolean | yes | resource-cache | |
| PJ_ISMONITOR | boolean | yes | resource-cache | |
| VENDORNAME | string | yes | resource-cache | |
| VENDORMODEL | string | yes | resource-cache | |
| LOCATIONNAME | string | yes | resource-cache | |
| PACKAGEGROUPNAME | string \| null | yes | DW_MES_RESOURCE_PACKAGEGROUP lookup | **Added resource-status-package-group.** Resolved via 46-row in-process dict keyed by PACKAGEGROUPID (CHAR). NULL when PACKAGEGROUPID is null (~91% of resources) or has no match. Frontend MUST hide the display row when null. |
| WORKCENTER_GROUP | string | yes | workcenter-mapping | |
| WORKCENTER_GROUP_SEQ | integer | yes | workcenter-mapping | |
| WORKCENTER_SHORT | string | yes | workcenter-mapping | |
| EQUIPMENTASSETSSTATUS | string | yes | realtime-equipment-cache | |
| EQUIPMENTASSETSSTATUSREASON | string | yes | realtime-equipment-cache | |
| STATUS_CATEGORY | string | yes | realtime-equipment-cache | Closed enum used for status filter |
| JOBORDER | string | yes | realtime-equipment-cache | |
| JOBMODEL | string | yes | realtime-equipment-cache | |
| JOBSTAGE | string | yes | realtime-equipment-cache | |
| JOBID | string | yes | realtime-equipment-cache | |
| JOBSTATUS | string | yes | realtime-equipment-cache | |
| CREATEDATE | datetime | yes | realtime-equipment-cache | |
| CREATEUSERNAME | string | yes | realtime-equipment-cache | |
| CREATEUSER | string | yes | realtime-equipment-cache | |
| TECHNICIANUSERNAME | string | yes | realtime-equipment-cache | |
| TECHNICIANUSER | string | yes | realtime-equipment-cache | |
| SYMPTOMCODE | string | yes | realtime-equipment-cache | |
| CAUSECODE | string | yes | realtime-equipment-cache | |
| REPAIRCODE | string | yes | realtime-equipment-cache | |
| LOT_COUNT | integer | yes | realtime-equipment-cache | |
| LOT_DETAILS | array | yes | realtime-equipment-cache | |
| TOTAL_TRACKIN_QTY | integer | yes | realtime-equipment-cache | |
| LATEST_TRACKIN_TIME | datetime | yes | realtime-equipment-cache | |

#### 3.10.2 PACKAGEGROUPNAME NULL semantics

- `PACKAGEGROUPID` originates from `DWH.DW_MES_RESOURCE` (already in the 24h resource_cache full-table load; no extra Oracle query at request time).
- Lookup is performed against an in-process dict populated from `DWH.DW_MES_RESOURCE_PACKAGEGROUP` (46 rows). Dict TTL = 7 days, independent of the 24h `resource_cache` cycle; no new Redis key.
- `PACKAGEGROUPID` is Oracle CHAR type. Dict key must use `str(pgid).strip()` normalization on both sides to handle CHAR padding.
- A dict load failure degrades gracefully: all records return `PACKAGEGROUPNAME = null` rather than raising a 500.
- Frontend contract: when `PACKAGEGROUPNAME is null`, the EquipmentCard row MUST NOT render. When non-null, render as a text row alongside WORKCENTERNAME / RESOURCEFAMILYNAME.

#### 3.10.3 `package_groups` filter semantics

- Query param: `package_groups` (comma-separated string, optional). Parsed as `package_groups_param.split(',') if package_groups_param else None`.
- Filter logic in `get_merged_resource_status()`: records with `PACKAGEGROUPNAME not in package_groups` (or `PACKAGEGROUPNAME = null`) are excluded when a `package_groups` filter is active.
- Applied on both the warm-cache path and any Oracle-fallback path (per CLAUDE.md Test Coverage Discipline).

Added by change `resource-status-package-group`.

---

### 3.11 Hold-History Detail Row（`GET /api/hold-history/detail/page`）

One row per hold/release event returned by `hold_history/list.sql` and the DuckDB spool view. Columns are aliased to lowercase in the `ranked` CTE of `list.sql` and mapped to camelCase JSON keys by the hold-history service.

| SQL alias | JSON key | type | nullable | notes |
|---|---|---|---|---|
| lot_id | lotId | string | yes | `NVL(c.CONTAINERNAME, TRIM(f.CONTAINERID))` |
| workorder | workorder | string | yes | `f.PJ_WORKORDER` |
| product | product | string | yes | `c.PRODUCTNAME` |
| workcenter | workcenter | string | yes | WORKCENTERNAME resolved to workcenter group |
| hold_reason | holdReason | string | yes | HOLDREASONNAME |
| qty | qty | integer | no | NVL(QTY, 0) |
| hold_date | holdDate | datetime | yes | HOLDTXNDATE |
| hold_emp | holdEmp | string | yes | HOLDEMP |
| hold_comment | holdComment | string | yes | HOLDCOMMENTS |
| release_date | releaseDate | datetime | yes | RELEASETXNDATE; null if still on hold |
| release_emp | releaseEmp | string | yes | RELEASEEMP |
| release_comment | releaseComment | string | yes | RELEASECOMMENTS |
| hold_hours | holdHours | float | no | computed; rounded to 2 decimal places |
| ncr_id | ncr | string | yes | NCRID |
| future_hold_comment | futureHoldComment | string | yes | FUTUREHOLDCOMMENTS; may decay after MES lot release |
| package | package | string | yes | `c.PRODUCTLINENAME`; null when LEFT JOIN returns no match or PRODUCTLINENAME is null; Oracle CHAR trailing-space trimmed via `_clean_text()`. **Added add-package-detail-tables.** |

**CSV/Excel export column order**: lotId, workorder, product, workcenter, holdReason, qty, holdDate, holdEmp, holdComment, releaseDate, releaseEmp, releaseComment, holdHours, ncr, futureHoldComment, **package** (appended; additive).

Added by change `add-package-detail-tables`.

---

## 6. Row Limit / Truncation Policy

| scope | limit | behavior |
|---|---|---|
| DuckDB spool paged query | `per_page` max 200 | hard cap per request |
| `/api/production-history/options` | memory guard | 503 on pressure |
| Trace events | `EVENT_FETCHER_MAX_TOTAL_ROWS=500000` | partial results if `EVENT_FETCHER_ALLOW_PARTIAL_RESULTS=true` |
| Material trace export | `MATERIAL_TRACE_MAX_RESULT_MB=256` | 413 if exceeded |
| Any JSON payload | internal soft cap | `_meta.truncated=true` added |

---

## 7. Breaking Change Policy

Removing a required column, changing a column type, or removing a key from the envelope requires:
1. Marking the field as `deprecated` for at least one minor version.
2. Adding a compatibility note to `contracts/api/api-contract.md`.
3. Updating related tests before removing the field.

### 3.12 Downtime Analysis Response Shapes

Added by change `downtime-analysis-page`. All shapes wrapped in standard `success_response` envelope (§1.1). Spool namespace: `tmp/query_spool/downtime_analysis/`.

#### 3.12.1 DowntimeKpiShape (`data.summary` in `POST /api/downtime-analysis/query`)

| field | type | nullable | notes |
|---|---|---|---|
| total_hours | float | no | Sum of HOURS across all events (UDT+SDT+EGT) |
| udt_hours | float | no | Sum of HOURS for OLDSTATUSNAME='UDT' |
| sdt_hours | float | no | Sum of HOURS for OLDSTATUSNAME='SDT' |
| egt_hours | float | no | Sum of HOURS for OLDSTATUSNAME='EGT' |
| event_count | integer | no | Count of logical events after cross-shift merge (DA-02) |
| avg_event_min | float | no | `(total_hours / event_count) * 60`; 0.0 when event_count=0 |

#### 3.12.2 DailyTrendRow (`data.daily_trend` array)

| field | type | nullable | notes |
|---|---|---|---|
| date | string | no | ISO 8601 `YYYY-MM-DD`; granularity-bucketed by DuckDB |
| udt_hours | float | no | UDT hours for this bucket |
| sdt_hours | float | no | SDT hours for this bucket |
| egt_hours | float | no | EGT hours for this bucket |
| total_hours | float | no | Sum of three buckets |

#### 3.12.3 BigCategoryRow (`data.big_category` array)

| field | type | nullable | notes |
|---|---|---|---|
| category | string | no | One of eight categories per DA-04 |
| hours | float | no | Total hours for this category |
| event_count | integer | no | Count of logical events |
| pct | float | no | category.hours / total_hours * 100; 0.0 when total_hours=0 |

#### 3.12.4 TopReasonRow (`data.top_reasons` array)

| field | type | nullable | notes |
|---|---|---|---|
| reason | string | no | OLDREASONNAME after strip(); `"(未填寫)"` when null/blank |
| status | string | no | OLDSTATUSNAME of dominant status for this reason |
| hours | float | no | Total hours for this reason |
| event_count | integer | no | Count of logical events |
| avg_min | float | no | `(hours / event_count) * 60`; 0.0 when event_count=0 |

#### 3.12.5 EquipmentDetailRow (`GET /api/downtime-analysis/equipment-detail`)

| field | type | nullable | notes |
|---|---|---|---|
| resource_id | string | no | HISTORYID from SHIFT table |
| resource_name | string | yes | RESOURCENAME from resource lookup |
| workcenter | string | yes | WORKCENTERNAME from resource lookup |
| family | string | yes | RESOURCEFAMILYNAME from resource lookup |
| udt_hours | float | no | UDT hours for this equipment |
| sdt_hours | float | no | SDT hours for this equipment |
| egt_hours | float | no | EGT hours for this equipment |
| total_hours | float | no | Sum of udt+sdt+egt |
| event_count | integer | no | Count of logical events |
| top_reason | string | yes | OLDREASONNAME with highest hours; null if no events |

**Response wrapper key:** `data.equipment_detail` (array). The route returns `success_response(equipment_detail=rows)`, not a bare array and not `data.rows`. Frontend composables must index `data.equipment_detail`. (AC-8; design.md DQ-1). When optional filter params (`big_category`, `status_types`) are applied, per-row schema is unchanged — only the row set is narrowed.

#### 3.12.6 EventDetailRow (`GET /api/downtime-analysis/event-detail`)

| field | type | nullable | notes |
|---|---|---|---|
| event_id | string | no | Stable composite key: `(HISTORYID, OLDSTATUSNAME, OLDREASONNAME, event_start_iso)` |
| resource_id | string | no | HISTORYID |
| resource_name | string | yes | RESOURCENAME from resource lookup |
| status | string | no | OLDSTATUSNAME |
| reason | string | yes | OLDREASONNAME after strip(); null when blank/unset |
| category | string | no | Big-category per DA-04 |
| start_ts | string | no | event_start ISO 8601 UTC |
| end_ts | string | no | event_end ISO 8601 UTC |
| hours | float | no | Merged event duration (SUM(HOURS) after DA-02 merge) |
| match_source | string | no | Closed enum `'jobid' \| 'overlap' \| 'none'`; always present at top level |
| job | object\|null | yes | JobEnrichment sub-object; null when match_source='none'. Frontend MUST render all job-derived fields as `—` when null. |

Paginated: `page` (default 1), `page_size` (default 50, max 200). Response includes `pagination: {page, page_size, total_rows, total_pages}`.

**Response wrapper key:** `data.events` (array). The route returns `success_response(events=rows)`, not `data.rows` and not a bare array. Frontend composables must index `data.events`. (AC-8; design.md DQ-3). When optional filter params (`big_category`, `status_types`, `resource_id`) are applied, per-row schema is unchanged.

#### 3.12.7 JobEnrichment (sub-object of EventDetailRow.job — null when match_source='none')

| field | type | nullable | notes |
|---|---|---|---|
| job_order_name | string | yes | JOB.JOBORDERNAME |
| job_model | string | yes | JOB.JOBMODELNAME |
| symptom | string | yes | JOB.SYMPTOMCODENAME |
| cause | string | yes | JOB.CAUSECODENAME |
| repair | string | yes | JOB.REPAIRCODENAME |
| wait_min | float | yes | (FIRSTCLOCKONDATE − CREATEDATE) × 60; null when FIRSTCLOCKONDATE null (DA-05) |
| repair_min | float | yes | (LASTCLOCKOFFDATE − FIRSTCLOCKONDATE) × 60; null when either null (DA-05) |
| handler | string | yes | JOB.COMPLETE_FULLNAME |
| match_ambiguous | boolean | no | true when runner-up Path-B overlap ≥ 80% of winner; false otherwise |

**Oracle DATE midnight-UTC handling:** `start_ts` and `end_ts` derive from `OLDLASTSTATUSCHANGEDATE`/`LASTSTATUSCHANGEDATE`. Frontend formatters must apply midnight-UTC detection (raw H/M/S check before `new Date()`) per CLAUDE.md Frontend Date Formatting Notes.

**Spool schema breaking-change surface:** column rename/add/remove to `tmp/query_spool/downtime_analysis/*.parquet` requires `rm tmp/query_spool/downtime_analysis/*.parquet` on deploy/rollback. IT JOBID backfill uses `DOWNTIME_BRIDGE_VERSION` constant to force cache-key change without manual parquet deletion (DA-06). Migration of `downtime_analysis_service` to `BatchQueryEngine → execute_plan → merge_chunks_to_spool` (change `batch-rowcount-unification`) does not alter the parquet column schema or namespace; no parquet cleanup is required for this migration alone.

**Note on §3.12.1–3.12.4 (DowntimeKpiShape, DailyTrendRow, BigCategoryRow, TopReasonRow):** These shapes are no longer returned by the primary `POST /api/downtime-analysis/query` endpoint when `DOWNTIME_BROWSER_DUCKDB=true`. They are computed in-browser by `useDowntimeDuckDB.ts` from the raw spool parquets (§3.13). The flag-off (legacy) path continues to return them unchanged. The shapes remain documented here as the parity reference for browser-side aggregation.

### 3.13 Downtime Analysis Raw Spool Schemas (browser-DuckDB path)

Added by change `downtime-browser-duckdb` (2026-06-12). These are the raw parquet namespaces written by `query_downtime_dataset_raw()` when `DOWNTIME_BROWSER_DUCKDB=true`. Both files are downloaded by `useDowntimeDuckDB.ts` and processed entirely in-browser by DuckDB-WASM. No server-side pandas reductions run on the request path for these namespaces.

**Spool namespace split:**
- `downtime_analysis_base_events` → `tmp/query_spool/downtime_analysis_base_events/<query_id>.parquet`
- `downtime_analysis_job_bridge` → `tmp/query_spool/downtime_analysis_job_bridge/<query_id>.parquet`
- Enriched namespace `downtime_analysis_events` retained for flag-off fallback (unchanged).

**SCHEMA_VERSION:** integer constant in `downtime_analysis_cache.py`; participates in raw-spool `query_id` hash. Bumping `SCHEMA_VERSION` orphans old raw parquets by key so readers miss-and-rewrite without a manual `rm`. Schema-breaking rollback requires: `rm -f tmp/query_spool/downtime_analysis_base_events/*.parquet tmp/query_spool/downtime_analysis_job_bridge/*.parquet`.

#### 3.13.1 `base_events` Parquet Schema

Source: `sql/downtime_analysis/base_events.sql`. DuckDB types as stored.

| column | DuckDB type | nullable | description |
|---|---|---|---|
| HISTORYID | VARCHAR | no | Equipment history ID (RESOURCEID equivalent) |
| OLDSTATUSNAME | VARCHAR | no | Status type: UDT, SDT, or EGT (DA-01) |
| OLDREASONNAME | VARCHAR | yes | Downtime reason (TRIM applied at SQL layer; null allowed) |
| OLDLASTSTATUSCHANGEDATE | TIMESTAMP | no | Event start timestamp |
| LASTSTATUSCHANGEDATE | TIMESTAMP | no | Event end timestamp |
| HOURS | DOUBLE | no | Duration in hours (CAST AS FLOAT in SQL) |
| JOBID | VARCHAR | yes | Direct JOBID if available (Path A bridge); null for Path B candidates |

**Cross-shift merge:** browser DuckDB-WASM runs the equivalent of `_merge_cross_shift_events` as SQL (60s contiguity rule, DA-02) on the full parquet before any view aggregation. The complete parquet must be loaded before running the merge — no chunk-seam split (ADR-0003).

#### 3.13.2 `job_bridge` Parquet Schema

Source: `sql/downtime_analysis/job_bridge.sql`. DuckDB types as stored.

| column | DuckDB type | nullable | description |
|---|---|---|---|
| JOBID | VARCHAR | no | Job ID |
| RESOURCEID | VARCHAR | no | Equipment ID (TRIM applied at SQL layer) |
| CREATEDATE | TIMESTAMP | no | Job creation timestamp |
| COMPLETEDATE | TIMESTAMP | yes | Job completion timestamp (null = open job) |
| SYMPTOMCODENAME | VARCHAR | yes | Symptom code (TRIM applied) |
| CAUSECODENAME | VARCHAR | yes | Cause code (TRIM applied) |
| REPAIRCODENAME | VARCHAR | yes | Repair code (TRIM applied) |
| COMPLETE_FULLNAME | VARCHAR | yes | Handler full name (TRIM applied) |
| FIRSTCLOCKONDATE | TIMESTAMP | yes | First clock-on (DA-05 wait calculation basis) |
| LASTCLOCKOFFDATE | TIMESTAMP | yes | Last clock-off (DA-05 repair calculation basis) |
| JOBORDERNAME | VARCHAR | yes | Job order name (TRIM applied) |
| JOBMODELNAME | VARCHAR | yes | Job model name (TRIM applied) |
| ASSIGNED_DATE | TIMESTAMP | yes | First ASSIGNED txn date |
| ACK_DATE | TIMESTAMP | yes | First ACKNOWLEDGED txn date |
| INSPECT_START | TIMESTAMP | yes | First inspection-stage txn date |
| INSPECT_END | TIMESTAMP | yes | Last inspection-stage txn date |

**Job overlap bridge:** browser DuckDB-WASM runs the equivalent of `_bridge_jobid` (Path A direct match + Path B overlap tiebreak + no-match; DA-03) on the full parquet after cross-shift merge. Ambiguity rule (≥80% runner-up) and tiebreak order (overlap DESC, CREATEDATE ASC, JOBID ASC) must match Python reference exactly (parity test: `TestCrossShiftMerge` + `TestJobidBridge`).

#### 3.13.3 Taxonomy JSON Shape

Returned as `taxonomy` key in the `POST /api/downtime-analysis/query` response (flag ON). Server-authoritative (DA-04); browser applies as SQL join/CASE without a rebuild on taxonomy change.

```json
{
  "map": [["EE Repair", "維修"], ["EE_PM", "保養"], ...],
  "prefixes": [["TMTT_", "檢查"]],
  "egt_category": "工程",
  "fallback": "其他/未分類"
}
```

| field | type | description |
|---|---|---|
| map | `[[reason: string, category: string], …]` | Exact-match rows from `_BIG_CATEGORY_MAP` |
| prefixes | `[[prefix: string, category: string], …]` | Prefix-match rules from `_PREFIX_CATEGORIES` |
| egt_category | string | Category applied to all EGT events (constant: `"工程"`) |
| fallback | string | Category for unknown/null reasons (constant: `"其他/未分類"`) |

**Two-parquet atomicity (AC-7):** server writes both `base_events` and `job_bridge` parquets or neither. A `base_events` spool hit with a missing/expired `job_bridge` spool is a server-side error (500); the service must not silently return empty job enrichment. Browser raises a visible error banner if either parquet fetch returns 404/410; never a silent empty table (CLAUDE.md Type-A rule).

---

### 3.14 Downtime Analysis Async Job Response

#### 3.14.1 HTTP 202 Async Envelope (long-range query)

When `DOWNTIME_ASYNC_ENABLED=true` and date range ≥ `DOWNTIME_ASYNC_DAY_THRESHOLD` (default 30 days):

```json
{
  "success": true,
  "data": {
    "async": true,
    "job_id": "<uuid string>",
    "status_url": "/api/job/<job_id>?prefix=downtime"
  },
  "meta": { "timestamp": "...", "app_version": "..." }
}
```

Follows generic shape §1.3. `prefix=downtime` routes status polls to `downtime_query_job_service`.

#### 3.14.2 Job Result Payload (`status=finished`)

```json
{
  "query_id": "<uuid string>"
}
```

`result.query_id` is used to load both parquet spools atomically (DA-11):
- `GET /api/spool/downtime_analysis_base_events/<query_id>.parquet`
- `GET /api/spool/downtime_analysis_job_bridge/<query_id>.parquet`

Both spool schemas: see §3.13 (`downtime_analysis_base_events`, `downtime_analysis_job_bridge`).

#### 3.14.3 Progress Milestones (`pct`)

| pct | stage | meaning |
|---|---|---|
| 5 | starting | job received by worker; Oracle query not yet issued |
| 15 | querying | Oracle BatchQueryEngine query in progress |
| 60 | writing | `base_events` parquet write in progress |
| 90 | finalizing | `job_bridge` parquet write + atomic commit in progress |
| 100 | complete | both spools written; `result.query_id` available |

Extends ASYNC-05 canonical milestone map. Both parquets are written before `pct` reaches 100 (DA-11).

#### 3.14.4 Path Decision Table

| condition | response | rule |
|---|---|---|
| `DOWNTIME_ASYNC_ENABLED=false` OR worker unavailable | HTTP 200 sync | ASYNC-DA-01 |
| date range < `DOWNTIME_ASYNC_DAY_THRESHOLD` | HTTP 200 sync | ASYNC-DA-01 |
| date range ≥ threshold + flag=true + worker available | HTTP 202 async | ASYNC-DA-01 |

Short-range (HTTP 200) response shape: unchanged from §3.12 (flag ON synchronous path returns `{base_spool_url, jobs_spool_url, query_id, taxonomy}`).

### 3.15 Hold-Overview Lots Export Column Set

Client-side CSV assembled from `data.lots[]` returned by `GET/POST /api/hold-overview/lots?export=true`. 13 columns in display order, matching the JSON key names in the lot row object:

| position | CSV header | JSON key | type | nullable | notes |
|---|---|---|---|---|---|
| 1 | Lot ID | lotId | string | yes | LOTID |
| 2 | Work Order | workorder | string | yes | WORKORDER |
| 3 | Qty | qty | integer | no | NVL(QTY,0) |
| 4 | Product | product | string | yes | PRODUCTNAME |
| 5 | Package | package | string | yes | PACKAGE_LEF |
| 6 | Work Center | workcenter | string | yes | WORKCENTER_GROUP |
| 7 | Hold Reason | holdReason | string | yes | HOLDREASONNAME |
| 8 | Spec | spec | string | yes | SPECNAME |
| 9 | Age (days) | age | float | no | AGEBYDAYS |
| 10 | Hold By | holdBy | string | yes | HOLDEMP |
| 11 | Dept | dept | string | yes | DEPTNAME |
| 12 | Hold Comment | holdComment | string | yes | COMMENT_HOLD |
| 13 | Future Hold Comment | futureHoldComment | string | yes | COMMENT_FUTURE; may decay after MES lot release |

**CSV format rules:**
- UTF-8 BOM prefix (`\uFEFF`) so Excel renders non-ASCII correctly (mirrors hold-history pattern).
- Header row required; values follow the JSON key order above.
- Values containing commas, double-quotes, or newlines must be RFC 4180 escaped.
- `null` / `None` values render as empty string in CSV (not the string `"null"`).
- Missing/malformed fields in a lot row must NOT abort CSV assembly; emit empty string for that cell.
- Filename: `hold-overview-<YYYY-MM-DD>.csv` (date = export day in client locale).

**Row boundary (AC-7):**
Maximum rows returned by the server in export mode: `HOLD_OVERVIEW_EXPORT_MAX_ROWS` env var, default **10,000**. Cap is enforced server-side on both snapshot and Oracle-fallback paths (`wip_service.get_hold_detail_lots` + `_get_hold_detail_lots_from_oracle`). See `contracts/env/env-contract.md §Hold Overview Export`. If the production hold-dataset regularly exceeds 10,000 rows after filtering, raise the cap and consider adding a warning banner.

**Client-side assembly:** CSV is assembled in the frontend from the `data.lots` array, not server-side streamed. The server returns a standard `success_response` JSON envelope; the frontend converts it to a Blob download. No `Content-Disposition` header is set by the server for this endpoint in export mode.

Added by change `hold-overview-export-csv`.


### 3.16 Yield-Alert Dataset Spool Schema (`yield_alert_dataset`)

Added by change `yield-alert-spool-refactor`. Spool namespace: `tmp/query_spool/yield_alert_dataset/`. All four views (trend, summary, heatmap, alerts) are computed in-browser or by DuckDB from this single spool; no separate Oracle trend/summary query runs on the view-serve path.

**Data source:** `ERP_WIP_MOVETXN_DETAIL` joined with reject linkage. Replaces `ERP_WIP_MOVETXN` for GA% aggregation; verified totals identical (TX=70,494,377, SCRAP=81,972 for GA%).

**`_SCHEMA_VERSION`** constant in `yield_alert_dataset_cache.py` participates in the spool cache key. Bumping it orphans stale parquets by key without a manual `rm`. Schema-breaking rollback requires: `rm -f tmp/query_spool/yield_alert_dataset/*.parquet`.

#### 3.16.1 Spool Column Schema

| column | type | nullable | description |
|---|---|---|---|
| WIP_ENTITY_NAME | VARCHAR | no | Workorder entity name; prefix determines process scope — see §3.16.4 for the full `process_type` → prefix → `WIP_CLASS_CODE` mapping |
| LINE | VARCHAR | yes | Production line identifier |
| TYPE | VARCHAR | yes | Product type |
| PACKAGE | VARCHAR | yes | Package type; may be `null` — `PACKAGE IS NOT NULL` filter is NOT applied (removed: 0 GA% rows have PACKAGE=NA; GC% PACKAGE=NA is valid data) |
| TXN_DATE | DATE | no | Transaction date |
| TX_QTY | INTEGER | no | Move transaction quantity (yield denominator); SOURCE_CODE NOT NULL rows always contribute TX_QTY = 0 |
| SCRAP_QTY | INTEGER | no | Scrap quantity (yield numerator) |
| SOURCE_CODE | VARCHAR | yes | LOT ID (`DW_MES_WIP.CONTAINERNAME` equivalent; format `GA26020192-A00-003-01`); null for workorder-level rows. When NOT NULL, TX_QTY = 0 (scrap-only row; does not inflate the TX numerator). |
| REJECT_LINKED | BOOLEAN | no | True when this row has a matching reject record from the reject linkage join (folded into initial spool pull; no separate Oracle `_compute_reject_linkage` query). |
| process_type | VARCHAR | no | Process scope applied at query time: one of `'GA%'`, `'GC%'`, `'GD%'`, `'F%'`, `'W%'`, `'D%'`. Derived from the `process_type` request parameter. |

#### 3.16.2 SOURCE_CODE Invariant

`SOURCE_CODE NOT NULL ⇒ TX_QTY = 0` always (verified by direct Oracle query; 100% of SOURCE_CODE NOT NULL rows are scrap-only). This invariant means:
- LOT-level scrap attribution (non-null SOURCE_CODE) adds precision to the alert list display but does NOT alter the TX denominator or yield formula.
- The yield formula remains `SCRAP_QTY / TX_QTY` at the workorder grain, unchanged from the prior implementation.

#### 3.16.3 PACKAGE Filter Removal Invariant

`PACKAGE IS NOT NULL` was previously applied to GA% queries. Verified by direct Oracle query: GA% workorders have zero rows where PACKAGE=NA. The filter was redundant and has been removed. For GC% (wafer-sort), PACKAGE=NA is valid data and was never filtered. No change to result sets for any process type.

#### 3.16.4 process_type Scope

Added by change `yield-alert-filter-expansion`: 4 new `process_type` values (`GD%`, `F%`, `W%`, `D%`), expanding the closed enum from 2 to 6. Verified mutually exclusive via direct Oracle query against `DWH.ERP_WIP_MOVETXN` (6-month sample; see business-rules.md YA-02 for the full prefix census and `WIP_CLASS_CODE` cross-tab).

| process_type | WIP_ENTITY_NAME pattern | domain | primary WIP_CLASS_CODE |
|---|---|---|---|
| `GA%` | `LIKE 'GA%'` | Packaging / assembly | 量產 (+ 9 minor classes, not split — see business-rules.md YA-02a) |
| `GC%` | `LIKE 'GC%'` | Wafer-sort / point-test | 點測 |
| `GD%` | `LIKE 'GD%'` | Rework | 重工RW |
| `F%` | `LIKE 'F%'` | Outsourcing (covers `F2`/`FA`/`FB` prefixes) | 委外 |
| `W%` | `LIKE 'W%'` | WIP (covers `W2` prefix) | 量產 (majority) + PJ_NST_A (minor) |
| `D%` | `LIKE 'D%'` | Other (covers `D2` prefix) | PJ_NST_A |

**Breaking-change surface:** column add/remove/rename to `yield_alert_dataset` parquet orphans existing files. `rm -f tmp/query_spool/yield_alert_dataset/*.parquet` required on both deploy and rollback.

#### 3.16.5 workcenter_groups Payload Shape Change (yield-alert-center only)

Added by change `yield-alert-filter-expansion`. Applies to `data.filter_options.workcenter_groups` in `GET /api/yield-alert/view` and `data.workcenter_groups` in `GET /api/yield-alert/cross-filter-options`.

| aspect | before | after |
|---|---|---|
| source | global `filter_cache.get_workcenter_groups()` (`DWH.DW_MES_SPEC_WORKCENTER_V`) | `SELECT DISTINCT DEPARTMENT_NAME` against the `query_id` spool parquet (same mechanism as `lines`/`packages`/`types`/`functions`) |
| display transform | `_YIELD_WORKCENTER_GROUP_ORDER` / `_DEPT_SEQ_MAP` grouping + fixed ordering | none — raw spool `DEPARTMENT_NAME` string values, sorted alphabetically (same convention as the other filter dimensions) |
| query-dependence | independent of `query_id` / `process_type` — identical across all queries | scoped to the current `query_id`; varies by `process_type` because each process_type has its own spool |
| empty-spool / zero-row behavior | N/A (always non-empty; independent source) | empty array when the spool has zero matching rows (e.g. a new process_type with no data yet) — not an error |
| column source | n/a | `DEPARTMENT_NAME` (raw, trimmed-only spool column) — explicitly **not** `DEPARTMENT_GROUP` (the separately normalized column already used by `_normalize_yield_department_group()` for heatmap/station_summary aggregation elsewhere in this module) |

**Not affected:** `GET /api/yield-alert/filter-options` (the initial-load dropdown-seed endpoint) continues to read `filter_cache.get_workcenter_groups()` unchanged. Every other page/consumer of `filter_cache.get_workcenter_groups()` (e.g. `material_trace_routes.py`, `downtime_worker.py`) is unaffected — this change re-points only the two yield-alert-center endpoints named above.

**Breaking-change note:** the JSON key `workcenter_groups` is unchanged in both endpoints, but its value semantics change (raw vs. grouped, query-dependent vs. static). Any caller that cached these values across a `process_type` switch, or matched them against the old grouped display names, will observe different values after this change ships. Sole known consumer: `frontend/src/yield-alert-center/App.vue`, updated in the same change (atomic cutover, no deprecation window — same precedent as `nav-config-to-code`).

#### 3.16.6 DuckDB-WASM Client Parity Gap (flag for implementation)

`frontend/src/yield-alert-center/useYieldAlertDuckDB.ts` independently reimplements filter-options computation for the browser-side large-dataset path (used when row count crosses the DuckDB-WASM threshold). As of `yield-alert-filter-expansion`, this client-side path must gain the same `SELECT DISTINCT DEPARTMENT_NAME` dimension as the server-side `_query_filter_options()` / `compute_cross_filter_options()`, or large queries that switch to WASM mode mid-session will silently lose `workcenter_groups` cross-filtering. Implementation must keep both paths in parity.

#### 3.16.7 Alerts CSV Numeric Export Formatting

Added by change `yield-alert-kpi-csv-parity`. Applies to the client-side CSV built by `_buildAlertsCSV()` in `frontend/src/yield-alert-center/App.vue` from alert-candidate rows (server-paginated `GET /api/yield-alert/alerts` fallback, or the DuckDB-WASM `computeView()` full-export path — row source differs, but both feed the same CSV builder).

**Problem:** `transaction_qty`/`scrap_qty` are stored in Oracle as K-PCS values that are always exact multiples of 0.001 (1 pcs). DuckDB DOUBLE arithmetic across multi-CTE SUM/ROUND leaves binary floating-point residue (e.g. `4.012` becomes `4.0119999999999996`). The frontend `toPcs()` helper (`frontend/src/yield-alert-center/utils.ts`) multiplies by 1000 to convert K-PCS → pcs, amplifying the residue into values like `4011.9999999999995`. The on-screen table masks this via `.toLocaleString()` (`App.vue`), but the CSV path wrote `String(v)` directly with no rounding — writing the raw float-noise string into the exported file.

**Rule:** `_buildAlertsCSV()` MUST round `toPcs(r.transaction_qty)` and `toPcs(r.scrap_qty)` to whole pcs (`Math.round(...)`) before writing to the CSV cell — pcs is the real-world data granularity (Oracle source values are exact multiples of 0.001 K-PCS = 1 pcs), so no sub-pcs fractional part is ever meaningful. This mirrors the existing `.toFixed()` treatment already applied to `yield_pct` (4 decimals) and `risk_score` (2 decimals) in the same function — every numeric CSV cell in this export must be deterministically formatted, none left as raw `String(floatValue)`.

**Column formatting summary (`_buildAlertsCSV`):**

| CSV column | source field | format |
|---|---|---|
| 轉出數(pcs) | `toPcs(r.transaction_qty)` | `Math.round(...)` — whole pcs, no decimal |
| 報廢量(pcs) | `toPcs(r.scrap_qty)` | `Math.round(...)` — whole pcs, no decimal |
| 良率(%) | `r.yield_pct` | `.toFixed(4)` (unchanged) |
| 風險分數 | `r.risk_score` | `.toFixed(2)` (unchanged) |

**Excel-parseability invariant:** rounded whole-pcs values written as plain numeric strings (no trailing decimal noise) must not be misread by Excel as "number stored as text" — long float-noise strings were the second contributing cause (alongside the KPI/CSV scope divergence fixed by business-rules.md YA-13) of user-reported `SUM()` mismatches on the exported CSV.

---

### §3.17 EAP ALARM Spool Schema

Added by change `eap-alarm-analysis`. Updated by `eap-alarm-coarse-filter` (schema_version 2→3), `eap-alarm-product-dims` (schema_version 3→4: product-dim spool columns + product-dim fine filters + pareto `dim` / trend `group_by`) and `eap-event-alarm-semantics` (schema_version 4→5: Shape B alarm-alias inclusion + `ALARM_SOURCE` column; the parquet column table below was also corrected — it had drifted, still describing the retired v1 event-level layout instead of the occurrence-level rows shipped since v2). Spool namespace: `tmp/query_spool/eap_alarm/`. Governed by `_SCHEMA_VERSION` in `eap_alarm_cache.py`. All shapes wrapped in standard `success_response` envelope (§1.1).

#### Spool key dimensions (schema_version 5)

`make_eap_alarm_spool_key()` canonical repr covers **all five** coarse dims (sorted): `eqp_types`, `lot_ids` (whitespace-stripped), `pj_types`, `product_lines`, `pj_bops`. Identical full parameter sets produce identical keys; any dimension change produces a different key. `_SCHEMA_VERSION = 5` participates in the key — all v4 (Shape-A-only) spool parquet is auto-invalidated on first key-miss after deploy.

#### Oracle coarse-filter mapping

| filter dim | Oracle predicate | source column | join |
|---|---|---|---|
| `eqp_types` | `EQUIPMENT_ID IN (...)` (full equipment-identifier strings per EA-07; `1=1` no-op when axis absent) | EAP_EVENT.EQUIPMENT_ID | direct |
| `lot_ids` | `LOT_ID IN (...)` | EAP_EVENT.LOT_ID | direct |
| `pj_types` | `EXISTS (SELECT 1 FROM DWH.DW_MES_CONTAINER c WHERE c.CONTAINERNAME = e.LOT_ID AND NVL(TRIM(c.PJ_TYPE),'(NA)') IN (...))` | DWH.DW_MES_CONTAINER | EXISTS semi-join — no row explosion |
| `product_lines` | `EXISTS (SELECT 1 FROM DWH.DW_MES_CONTAINER c WHERE c.CONTAINERNAME = e.LOT_ID AND NVL(TRIM(c.PRODUCTLINENAME),'(NA)') IN (...))` | DWH.DW_MES_CONTAINER | EXISTS semi-join — no row explosion |
| `pj_bops` | `EXISTS (SELECT 1 FROM DWH.DW_MES_CONTAINER c WHERE c.CONTAINERNAME = e.LOT_ID AND NVL(TRIM(c.PJ_BOP),'(NA)') IN (...))` | DWH.DW_MES_CONTAINER | EXISTS semi-join — no row explosion |

Index relied upon: `DW_C_CONTAINERNAME` on `DWH.DW_MES_CONTAINER.CONTAINERNAME`. When multiple product_dims are supplied together, each produces a separate EXISTS clause (AND-semantics). Empty/whitespace `lot_ids` entries are stripped before key-build and Oracle bind.

**Event-type predicate (EA-ALCD / EA-EVT):** every coarse query additionally filters

```sql
(e.EVENT_TYPE = 'EQP_SECS_ALARM'
 OR (e.EVENT_TYPE = 'EQP_SECS_EVENT'
     AND e.EVENT_NAME IN ('AlarmDetected', 'AlarmCleared')))
```

`ProcessAlarm` and `AlarmNeedCountIntoStatistics(MTBA/MTBF)` are deliberately excluded (see EA-EVT). The driving predicate remains `LAST_UPDATE_TIME BETWEEN` (EA-03); the event-type clause is a filter, not an access path.

**Cross-channel dedup (EA-EVT):** dual-channel equipment report most physical alarms on BOTH channels (production-measured 2026-07-07, GDBA 2-day window: 70.43% of Shape B `AlarmDetected` had a Shape A counterpart within ±60s). At spool-write time, after per-shape SET/CLEAR pairing, a Shape B occurrence is dropped when a Shape A occurrence exists with the same `(EQP_ID, ALARM_ID)` (string equality) and `ALARM_START` within ±60s (`_SHAPE_B_DEDUP_TOLERANCE_SECONDS`). Shape A wins — including when unpaired. Text-`EVENT_NAME` families (GWBA-style) are outside this rule's reach (identity spaces don't compare); their overlap is unmeasured. Dedup happens in DuckDB on the already-fetched window, never in Oracle.

#### Spool product-dim enrichment (schema_version 4)

At spool-write time the worker runs one chunked lookup (`CONTAINERNAME IN (...)`, ≤999 binds/chunk, deduped on LOT_ID) over `DWH.DW_MES_CONTAINER` for the distinct LOT_IDs in the result set and LEFT JOINs it into the parquet as `PJ_TYPE` / `PRODUCT_LINE` / `PJ_BOP`. Lookup values are `NVL(TRIM(col), '(NA)')` — mirroring the coarse EXISTS semantics — so a lot whose container row has a NULL dim reads back `'(NA)'`; events with no LOT_ID (or no container row) carry NULL product dims. Lookup failure degrades to NULL product columns and never fails the job.

#### Parquet column schema (schema_version 5 — one row = one alarm occurrence)

| column | type | nullable | notes |
|---|---|---|---|
| ALARM_ID | VARCHAR | yes | Alarm identity. Shape A: raw `EVENT_NAME` (numeric code or descriptive text per equipment family). Shape B: `AlarmID` detail param (fallback raw `EVENT_NAME` when detail missing) |
| EQP_ID | VARCHAR | no | Equipment ID (EQUIPMENT_ID from EAP_EVENT) |
| EQP_TYPE | VARCHAR | no | `SUBSTR(EQUIPMENT_ID, 1, 4)` prefix (e.g. GDBA, GCBA) |
| LOT_ID | VARCHAR | yes | LOT_ID from EAP_EVENT; NULL if no lot in context |
| ALARM_TEXT | VARCHAR | yes | `AlarmText` detail param; fallback = alarm identity (Shape B falls back `AlarmText` → `AlarmID` → raw `EVENT_NAME`) |
| ALARM_CATEGORY_CODE | INTEGER | yes | Shape A only: `ABS(AlarmCode) & 127`; always NULL for Shape B (no ALCD byte → "未知" per EA-05) |
| ALARM_START | TIMESTAMP | no | SET event LAST_UPDATE_TIME |
| ALARM_END | TIMESTAMP | yes | Earliest matching CLEAR after ALARM_START on `(EQP_ID, ALARM_ID, ALARM_SOURCE)`; NULL = unresolved in window |
| DURATION_SECONDS | DOUBLE | yes | `epoch(ALARM_END) - epoch(ALARM_START)`; NULL when unresolved |
| DETAIL_PARAMS | VARCHAR | yes | JSON string of ALL EAP_EVENT_DETAIL params of the SET event; NULL if no detail rows |
| PJ_TYPE | VARCHAR | yes | Product dim from DW_MES_CONTAINER lookup by LOT_ID (v4); `'(NA)'` when container row has NULL dim; NULL when no lot / no container row |
| PRODUCT_LINE | VARCHAR | yes | PRODUCTLINENAME from DW_MES_CONTAINER lookup (v4); same NULL/`'(NA)'` semantics as PJ_TYPE |
| PJ_BOP | VARCHAR | yes | PJ_BOP from DW_MES_CONTAINER lookup (v4); same NULL/`'(NA)'` semantics as PJ_TYPE |
| ALARM_SOURCE | VARCHAR | no | **v5** — raw `EVENT_TYPE`: `EQP_SECS_ALARM` (Shape A) or `EQP_SECS_EVENT` (Shape B alarm-alias). Part of the pairing key; lets dual-channel duplicates be told apart |
| eqp_types_filter | VARCHAR | no | Coarse-filter hash covering all 5 dims (eqp_types, lot_ids, pj_types, product_lines, pj_bops); for partition reuse validation |

**Breaking-change surface:** column add/remove/rename to `eap_alarm` parquet orphans existing files. Bump `_SCHEMA_VERSION` in the same commit. The schema_version 4→5 bump auto-invalidates all v4 spool files via key-miss; no manual `rm` needed on deploy, and on rollback the orphaned v5 files expire by TTL/cleanup daemon (v4 code never resolves their keys). `GET /api/eap-alarm/detail` DESCRIBE-detects `ALARM_SOURCE` so in-flight v4 query_ids keep working across the deploy window (`alarm_source: null`).

#### Product-filter-options payload shape

`GET /api/eap-alarm/product-filter-options` — served from `container_filter_cache` (shared with production-history and other pages). No Oracle at request time. Cold cache returns empty arrays (mirrors §2.7 fail-open behavior).

```json
{
  "pj_types":      ["string", "..."],
  "product_lines": ["string", "..."],
  "pj_bops":       ["string", "..."],
  "updated_at":    "ISO-8601 string | null"
}
```

Cold-cache invariant: when `container_filter_cache` is unpopulated, all three arrays are `[]` and `updated_at` is `null`. A cache build failure must not crash the options endpoint — return last-good cache or empty arrays.

#### Response shapes (DuckDB-derived; all fine-filter aware)

Fine-filter axes (all views): `alarm_text[]` (ILIKE), plus exact-match `equipment_id[]`, `lot_id[]`, `pj_type[]`, `product_line[]`, `pj_bop[]` (v4).

**Filter options** (`GET /api/eap-alarm/filter-options`): `data` = `{alarm_text_options: string[], equipment_id_options: string[], lot_id_options: string[], pj_type_options: string[], product_line_options: string[], pj_bop_options: string[]}`. All derived from DuckDB spool; no Oracle re-query. NULL column values are excluded from option lists.

**Summary** (`GET /api/eap-alarm/summary`): `data` = `{total_alarm_count: int, affected_equipment_count: int, affected_lot_count: int, affected_product_line_count: int, unresolved_count: int, avg_duration_minutes: float | null}`.

**Pareto** (`GET /api/eap-alarm/pareto`): `data` = `{items: [{name: string, alarm_text: string, count: int, cumulative_pct: float}], dim: string, total: int}`. Sorted descending by count; top-50 returned. `dim` param (closed enum, 400 on unknown): `alarm_text` (default) | `eqp_id` | `eqp_type` | `lot_id` | `pj_type` | `product_line` | `pj_bop`. `items[].alarm_text` mirrors `items[].name` for backward compatibility; new consumers read `name`.

**Trend** (`GET /api/eap-alarm/trend`): `data` = `{labels: string[], series: [{name: string, alarm_text: string, data: int[]}], group_by: string}`. `labels` length matches `data` length per series; top-10 groups. `granularity` param: `day` (ISO date YYYY-MM-DD) or `hour` (ISO datetime YYYY-MM-DD HH:00). `group_by` param: same closed enum as pareto `dim` (default `alarm_text`, 400 on unknown). `series[].alarm_text` mirrors `series[].name` for backward compatibility.

**Detail** (`GET /api/eap-alarm/detail`): `data` = `{rows: [{alarm_id: string, eqp_id: string, eqp_type: string, lot_id: string | null, pj_type: string | null, product_line: string | null, pj_bop: string | null, alarm_text: string | null, alarm_category_code: int | null, alarm_start: string (ISO 8601), alarm_end: string | null, duration_seconds: float | null, detail_params: object | null, alarm_source: string | null}], meta: {page: int, per_page: int, total_count: int, total_pages: int}}`. `detail_params` is null or a JSON object of extra ALARM DETAIL parameters. `alarm_source` (v5, additive) is the raw `EVENT_TYPE`; null when served from a pre-v5 spool (DESCRIBE fallback). Pagination: `per_page` max 200.


## Oracle → pyarrow RecordBatch → DuckDB/parquet Streaming Boundary

This section documents the row-level invariants and type-coercion semantics for
the unified streaming pipeline introduced by `unified-query-core-infra`.

### Pipeline Stages

```
Oracle cursor.fetchmany()
    → per-row CHAR strip + null passthrough
    → pyarrow.RecordBatch.from_arrays()
    → [requires_cross_chunk_reduction=True]  DuckDB INSERT INTO raw (writer_lock)
      [requires_cross_chunk_reduction=False] pyarrow.parquet.ParquetWriter append
    → post_aggregate DuckDB SQL → COPY TO canonical parquet spool
    → frontend read_parquet() in-memory DuckDB → JSON
```

### Invariants

**No pandas in path.** Neither `OracleArrowReader` nor `BaseChunkedDuckDBJob` imports
pandas. Data stays in Arrow / DuckDB format from Oracle fetch to parquet spool.
The `test_no_pandas_import_in_new_modules` test enforces this (AC-7).

**No row duplication across chunks.** Each row appears in exactly one chunk; chunk
boundaries are defined by non-overlapping time ranges, ID batches, or row-count
windows. Cross-chunk deduplication is NOT performed — chunk design must prevent
overlap (enforced at `build_chunk_sql()` time by the subclass).

**No row loss.** The Oracle cursor is exhausted fully within each chunk's connection
context. Partial fetches (e.g. a mid-chunk connection drop) propagate as exceptions,
leaving no orphaned rows. The caller retries the entire chunk or fails the job.

**Empty chunk → zero RecordBatch yields.** When `cursor.fetchmany()` returns `[]`
on the first call, `chunk_iter()` yields nothing and returns without error.
Empty chunks are legal and do not indicate a failure condition.

**Null values passthrough without error.** Oracle `None` values are passed to
`pa.array()` which maps them to Arrow null. No row is dropped due to null fields.
Columns with all-null values produce a valid `pa.array` of the inferred type or
`pa.null()` if type cannot be inferred.

**Oracle CHAR strip applied at boundary.** All `str` values returned by the Oracle
cursor are `.strip()`-ed inside `OracleArrowReader.chunk_iter()` before the
RecordBatch is built. This removes trailing space-padding from fixed-width CHAR
columns. The strip is applied column-by-column regardless of declared SQL type;
non-str values are passed through unchanged.

**Oracle DATE midnight-UTC handling.** Oracle DATE columns carry no timezone
information. A DATE value of `2024-01-15 00:00:00` is returned by the Oracle
driver as a Python `datetime` with no tzinfo. Callers must NOT assume midnight
means UTC midnight when displaying as a date — inspect H/M/S components via
regex (per `frontend-patterns.md`) before converting to a display date. This
boundary contract does NOT perform timezone conversion; that remains the
responsibility of the frontend display layer.

**DuckDB single-writer discipline.** When `requires_cross_chunk_reduction=True`,
all RecordBatch INSERT operations into the job-temp `.duckdb` file are serialized
under `BaseChunkedDuckDBJob._writer_lock`. Oracle fetch (I/O-bound) is the
parallel stage; DuckDB write is serialized. Concurrent writes to a single DuckDB
file without the lock will corrupt the file — this invariant must be preserved
in any subclass override of `chunk_to_duckdb()`.

**Job-temp DuckDB isolation.** The job-temp `.duckdb` file at
`{DUCKDB_JOB_DIR}/{namespace}/{job_id}.duckdb` is deleted in a `finally` block
on both success and failure. Crash survivors are reaped by TTL orphan cleanup.
The job-temp directory (`DUCKDB_JOB_DIR`) must NOT overlap with the canonical
parquet spool directory (`QUERY_SPOOL_DIR`).

**Canonical spool format unchanged.** The parquet file produced by `post_aggregate()`
uses the same schema and path convention as all existing spool namespaces. Frontend
`/view` endpoints continue to read spool via in-memory DuckDB; no frontend changes
are required by this pipeline change.

### Breaking-Change Surface

Adding, removing, or renaming columns in the `raw` table written by `chunk_to_duckdb()`
is a breaking change for any domain using `requires_cross_chunk_reduction=True` —
the `post_aggregate()` SQL must be updated atomically with the schema change, and
the job-temp DuckDB directory must be cleared of any stale files. For the canonical
parquet spool, the existing breaking-change policy (`_SCHEMA_VERSION` bump +
`rm {namespace}/*.parquet`) applies unchanged.

---

### §3.18 Production History and Reject Dataset Spool Schema — UNCHANGED Assertion (P2 Migration)

**Change: production-reject-history-migration (P2 BaseChunkedDuckDBJob migration)**

The `production_history` and `reject_dataset` spool parquet schemas are **explicitly unchanged** by this migration. The unified job workers (`ProductionHistoryJob`, `RejectHistoryJob`) write the identical column set as the legacy pandas BQE path. This is a non-goal and is verified by data-boundary parity tests (AC-1, AC-2).

- `production_history` spool (§3.4): columns `CONTAINERNAME`, `PJ_TYPE`, `PJ_BOP`, `PJ_FUNCTION`, `MFGORDERNAME`, `FIRSTNAME`, `PRODUCTLINENAME`, `WORKCENTERNAME`, `SPECNAME`, `EQUIPMENTID`, `EQUIPMENTNAME`, `TRACKINTIMESTAMP`, `TRACKOUTTIMESTAMP`, `TRACKINQTY`, `TRACKOUTQTY` — unchanged. No `_SCHEMA_VERSION` bump required; no parquet cleanup on deploy/rollback.
- `reject_dataset` spool: primary query columns (TXN_TIME, TXN_DAY, TXN_MONTH, WORKCENTER_GROUP, etc.) — unchanged. No parquet cleanup on deploy/rollback.

Any future column rename, addition, or removal in either namespace **must** bump `_SCHEMA_VERSION` (or equivalent) and require parquet cleanup per the standard breaking-change policy.

**Cache-key composition update (rh-remove-supplementary-filter):** `query_id_input` for `reject_dataset` now includes a `reasons` key (alongside the existing `pj_types`, `packages`, `pj_functions` from rh-primary-prefilter). The parquet column schema is unchanged. Adding `reasons` to the cache key prevents cross-selection cache bleed. Existing cache entries keyed without `reasons` are distinct from new entries keyed with `reasons` (even empty `reasons=[]`); production cache entries from before this change will miss and regenerate naturally — no forced purge required, as the key format changes.

---

### §3.19 Resource History Base and OEE Dataset Spool Schema — UNCHANGED Assertion (P3 Migration)

**Change: resource-history-migration (P3 BaseChunkedDuckDBJob migration)**

The `resource_dataset` and `resource_oee` spool parquet schemas are **explicitly unchanged** by this migration. The unified job workers (`ResourceHistoryBaseJob`, `ResourceHistoryOeeJob`) write the identical column sets as the legacy `_query_and_store_canonical_dataset` / `execute_primary_query` pandas ThreadPool path. This is a non-goal verified by data-boundary parity tests (AC-6).

- `resource_dataset` spool: columns `HISTORYID`, `DATA_DATE`, `PRD_HOURS`, `SBY_HOURS`, `UDT_HOURS`, `SDT_HOURS`, `EGT_HOURS`, `NST_HOURS`, `TOTAL_HOURS` — unchanged. No `_SCHEMA_VERSION` bump required; no parquet cleanup on deploy/rollback.
- `resource_oee` spool: **legacy** columns `EQUIPMENTID`, `SHIFT_DATE`, `TRACKOUT_QTY`, `NG_QTY`; **unified path** columns `EQUIPMENTID`, `TRACKOUT_QTY`, `NG_QTY` (SHIFT_DATE absent — `post_aggregate` groups by EQUIPMENTID only; no consumer reads SHIFT_DATE from this spool, so removing it is non-breaking). AC-6 `_OEE_LEGACY_COLS = {EQUIPMENTID, TRACKOUT_QTY, NG_QTY}` reflects the unified output. No parquet cleanup on deploy/rollback.

Any future column rename, addition, or removal in either namespace **must** bump `_SCHEMA_VERSION` (or equivalent) and require parquet cleanup per the standard breaking-change policy.

---

### §3.20 Material Trace Spool Schema — UNCHANGED Assertion (P4 Migration)

**Change: material-trace-streaming-migration (P4 BaseChunkedDuckDBJob migration)**

The `material_trace` spool parquet schema is **explicitly unchanged** by this migration. The unified `MaterialTraceJob` streaming path writes the identical column set as the legacy `_execute_batched_query` + `pd.concat` path. This is a non-goal verified by AC-4 parity tests.

`material_trace` spool columns (13, both legacy and unified paths):
`CONTAINERNAME`, `PJ_WORKORDER`, `WORKCENTER_GROUP`, `WORKCENTERNAME`, `MATERIALPARTNAME`, `MATERIALLOTNAME`, `VENDORLOTNUMBER`, `QTYREQUIRED`, `QTYCONSUMED`, `EQUIPMENTNAME`, `TXNDATE`, `PRIMARY_CATEGORY`, `SECONDARY_CATEGORY`.

The unified path uses `_EXPORT_COLS` in `material_trace_duckdb_runtime.py`; the legacy path uses `_CSV_COLUMNS.keys()` in `material_trace_service.py`. Both lists contain the same 13 columns in the same order (confirmed by AC-4 set-equality test). No `_SCHEMA_VERSION` bump required; no parquet cleanup on deploy/rollback.

Any future column rename, addition, or removal **must** bump `_SCHEMA_VERSION` (or equivalent) and require parquet cleanup per the standard breaking-change policy.

---

### §3.21 Downtime Analysis Enriched Spool Schema — UNCHANGED Assertion (P5 Migration)

**Change: downtime-duckdb-join-migration (P5 BaseChunkedDuckDBJob migration)**

The `query_downtime_dataset` enriched bridged-spool parquet schema is **explicitly unchanged** by this migration. The unified `DowntimeJob` path writes the identical column set as the legacy `_bridge_jobid` Path B `pd.merge` path via `query_downtime_dataset`. This is a non-goal verified by data-boundary parity tests (AC-1, AC-3).

**Path scope:** This assertion covers ONLY the `query_downtime_dataset` enriched spool written by `query_downtime_dataset()` (in-Python bridge path). The `query_downtime_dataset_raw` two-spool path (`downtime_analysis_base_events` 7-col + `downtime_analysis_job_bridge` 16-col, browser-DuckDB path) is OUT OF SCOPE for this migration (design D6) and has a different column set; both spool schemas are documented in §3.13.

`query_downtime_dataset` enriched spool columns (both legacy and unified paths must produce identically):

| column | DuckDB type | nullable | description |
|---|---|---|---|
| event_id | VARCHAR | no | Stable composite key derived by cross-shift merge |
| resource_id | VARCHAR | no | HISTORYID from base_events |
| status | VARCHAR | no | OLDSTATUSNAME (UDT/SDT/EGT; DA-01) |
| reason | VARCHAR | yes | OLDREASONNAME after strip(); null when blank/unset |
| category | VARCHAR | no | Big-category per DA-04 taxonomy |
| start_ts | VARCHAR | no | event_start ISO 8601 UTC (from cross-shift merge, DA-02) |
| end_ts | VARCHAR | no | event_end ISO 8601 UTC (from cross-shift merge, DA-02) |
| hours | DOUBLE | no | Merged event duration SUM(HOURS) after DA-02 |
| fragment_count | INTEGER | no | Number of raw SHIFT fragments merged into this logical event by DA-02; 1 = single fragment (no cross-shift merge occurred) |
| match_source | VARCHAR | no | Closed enum `'jobid' \| 'overlap' \| 'none'` (DA-03) |
| match_ambiguous | BOOLEAN | no | true when runner-up Path-B overlap ≥ 80% of winner; false otherwise |
| job_id | VARCHAR | yes | JOB.JOBID string; null when match_source='none' |
| job_order_name | VARCHAR | yes | JOB.JOBORDERNAME; null when match_source='none' |
| job_model | VARCHAR | yes | JOB.JOBMODELNAME; null when match_source='none' |
| symptom | VARCHAR | yes | JOB.SYMPTOMCODENAME; null when match_source='none' |
| cause | VARCHAR | yes | JOB.CAUSECODENAME; null when match_source='none' |
| repair | VARCHAR | yes | JOB.REPAIRCODENAME; null when match_source='none' |
| handler | VARCHAR | yes | JOB.COMPLETE_FULLNAME; null when match_source='none' |
| wait_min | DOUBLE | yes | (FIRSTCLOCKONDATE − CREATEDATE) × 60; null when FIRSTCLOCKONDATE null or match_source='none' (DA-05) |
| repair_min | DOUBLE | yes | (LASTCLOCKOFFDATE − FIRSTCLOCKONDATE) × 60; null when either null or match_source='none' (DA-05) |

No `_SCHEMA_VERSION` bump required; no parquet cleanup on deploy/rollback. Switching `DOWNTIME_USE_UNIFIED_JOB` between `on` and `off` mid-flight is safe — a spool written by either path is readable by the other because the column set is identical.

Any future column rename, addition, or removal in the `query_downtime_dataset` namespace **must** bump `DOWNTIME_BRIDGE_VERSION` (DA-06 cache invalidation) and document the change here.

---

---

### §2.10 `GET /admin/api/pages` Slimmed Payload

Admin-only. Returns only route + status per registered page. Name, drawer_id, and order fields are absent (structure moved to the frontend manifest).

```json
{
  "success": true,
  "data": {
    "pages": [
      { "route": "/wip-overview", "status": "released" },
      { "route": "/admin/dashboard", "status": "dev" }
    ]
  },
  "meta": { "app_version": "unknown", "timestamp": "2026-06-24T00:00:00" }
}
```

One row per registered route. Absent route = unregistered (do not infer released).

---

### §2.11 `GET /api/portal/navigation` Status Feed Payload

Status-only navigation feed. No drawers/names/order. Structure lives in `navigationManifest.js` (§3.11b). Absent route in `statuses` defaults to `released`.

```json
{
  "statuses": { "/admin/dashboard": "dev" },
  "is_admin": true,
  "admin_user": {
    "displayName": "Admin",
    "username": "admin",
    "mail": null,
    "department": null
  },
  "admin_links": {
    "logout": "/api/auth/logout",
    "pages": "/admin/pages",
    "dashboard": "/admin/dashboard",
    "performance": "/admin/performance"
  },
  "features": { "ai_query_enabled": false },
  "diagnostics": {}
}
```

---

### §3.11a Writable Page-Status Store (`data/page_status.json`)

Target shape after nav-config-to-code shrink:

```json
{
  "api_public": true,
  "statuses": {
    "/admin/dashboard": "dev"
  }
}
```

- `api_public` (bool, **REQUIRED**): read by `is_api_public()`; MUST NOT be dropped; default `false` if key absent. Dropping it silently disables the site-wide auth-bypass gate.
- `statuses` (object, optional): map of `route → "released"|"dev"`. Absent route → `released` (fail-safe). Only non-default (`dev`) pages need explicit entries — currently only `/admin/dashboard`.
- **REMOVED keys:** `pages`, `drawers`, `db_scan`.
- **Back-compat read:** If file has legacy full-CMS shape (`pages[]` array present), `_load()` derives statuses from `pages[].status` and ignores `drawers`/`db_scan`; no error, no forced rewrite.
- **Write path:** `set_page_status(route, status)` writes only to `statuses`. No drawer or name fields written.
- **Rollback-safe:** Restored `_migrate_navigation_schema` rebuilds drawer array from `DEFAULT_DRAWERS` on first post-rollback read.

---

### §3.11b Navigation Manifest (`frontend/src/portal-shell/navigationManifest.js`)

Frontend code-owned, single source of truth for navigation **structure** (drawer grouping, ordering, display names). No runtime write path.

**Exports:**

- `drawers`: array of `{id: string, name: string, order: int, admin_only: bool}`
- `routes`: map of `route → {drawerId: string|null, order: int, displayName: string, defaultStatus?: string}`

**Drawer id mapping (post-rename):**

| id | display name | order | admin_only |
|---|---|---|---|
| reports | 即時報表 | 1 | false |
| history-reports | 歷史報表 | 2 | false |
| query-tools | 查詢工具 | 3 | false |
| trace-tools | 追溯工具 | 4 | false |
| dev-tools | 開發工具 | 5 | true |
| eap-analysis | EAP | 6 | false |

**Constraints:**
- Every manifest route MUST exist in `nativeModuleRegistry.js` (mount gate).
- `orders` MUST be distinct within a drawer.
- `displayName` MUST match current live names exactly (AC-1/AC-5).
- Standalone routes (`/`, `/wip-detail`, `/hold-detail`, `/anomaly-overview`) have `drawerId: null` (or absent).
- Only `/admin/dashboard` has `defaultStatus: 'dev'`; all others `'released'` or omitted.
- Manifest must NOT duplicate `nativeModuleRegistry` or `routeContracts` policy fields.

---


### §2.12 Reject-History Primary Query — Request-Side Filter Params (`POST /api/reject-history/query`)

Four optional prefilter fields that inject into the `{{ BASE_WHERE }}` placeholder of the `reject_raw` CTE
in `performance_daily_lot.sql`, BEFORE the GROUP BY clause. The supplementary `{{ WHERE_CLAUSE }}` layer
(workcenter_groups, packages, reasons, types) is fully removed as of change `rh-remove-supplementary-filter`.

```json
{
  "start_date": "YYYY-MM-DD",
  "end_date": "YYYY-MM-DD",
  "pj_types":     ["<string>"],
  "packages":     ["<string>"],
  "pj_functions": ["<string>"],
  "reasons":      ["<string>"]
}
```

#### Field Specifications

| field | type | required | SQL column | SQL form |
|---|---|---|---|---|
| `pj_types` | `string[]` | no | `DWH.DW_MES_CONTAINER.PJ_TYPE` | `NVL(TRIM(c.PJ_TYPE), '(NA)') IN (:bind_list)` |
| `packages` | `string[]` | no | `DWH.DW_MES_CONTAINER.PRODUCTLINENAME` | `NVL(TRIM(c.PRODUCTLINENAME), '(NA)') IN (:bind_list)` |
| `pj_functions` | `string[]` | no | `DWH.DW_MES_CONTAINER.PJ_FUNCTION` | `NVL(TRIM(c.PJ_FUNCTION), '(NA)') IN (:bind_list)` |
| `reasons` | `string[]` | no | `DWH.DW_MES_LOTREJECTHISTORY.LOSSREASONNAME` | `NVL(TRIM(r.LOSSREASONNAME), '(未填寫)') IN (:bind_list)` |

#### NULL / `(NA)` Sentinel Semantics — container-level fields

- Source columns come from a `LEFT JOIN DWH.DW_MES_CONTAINER c`; when a lot has no container record,
  `c.PJ_TYPE / c.PRODUCTLINENAME / c.PJ_FUNCTION` is Oracle NULL.
- `NVL(TRIM(col), '(NA)')` maps every Oracle NULL (or blank-after-trim) to the literal string `(NA)`.
- Rows whose container is absent from `DW_MES_CONTAINER` are **not silently dropped** — they receive the
  sentinel and participate in the `IN (...)` match.
- Selecting `(NA)` in the UI returns exactly those rows where the container lookup yielded no match.

#### NULL / `(未填寫)` Sentinel Semantics — `reasons[]`

- Source column is `LOTREJECTHISTORY.LOSSREASONNAME` (not a container column; no LEFT JOIN miss scenario).
- `NVL(TRIM(r.LOSSREASONNAME), '(未填寫)')` maps every Oracle NULL or blank-after-trim to `(未填寫)`.
- Sentinel `(未填寫)` is distinct from `(NA)` — they cannot be confused.
- Selecting `(未填寫)` in the UI returns reject records where LOSSREASONNAME is null or blank.
- Options for `reasons[]` are sourced from `GET /api/reject-history/options` (via `reason_filter_cache.get_reject_reasons()`). No new endpoint required.
- Bind param prefix: `reason_0`, `reason_1`, … (distinct from `pt_`, `pkg_`, `pf_` used by container fields).

#### Injection Point

- All four fields are injected into `{{ BASE_WHERE }}` — the primary CTE clause applied **before** Oracle
  executes the `GROUP BY` inside `reject_raw`. This reduces I/O and GROUP BY cardinality at the Oracle layer.
- The supplementary filter layer (`{{ WHERE_CLAUSE }}`) is fully removed by change `rh-remove-supplementary-filter`.
  `workcenter_groups` is no longer a valid request parameter.

#### Parity Rule

- The same four fields (`pj_types`, `packages`, `pj_functions`, `reasons`) must be present and forwarded
  identically by both the sync (HTTP 200) and async/RQ (HTTP 202) job paths.
- Spool/cache keys for the `reject_dataset` namespace must include all four fields (even when empty —
  empty encodes as no-restriction, but the key must reflect the effective filter state).

#### Supplementary Filter Layer Removal

The `{{ WHERE_CLAUSE }}` supplementary filter layer (previously applied to the materialized base result at the
DuckDB/cache layer) is removed by change `rh-remove-supplementary-filter`. The following fields are no longer
accepted as request params: `workcenter_groups`, and the supplementary forms of `packages`, `reasons`, `types`.
The `{{ BASE_WHERE }}` layer (documented above) is now the sole filter injection point for reject-history queries.

#### Scope Exclusions

- `PJ_BOP` is explicitly excluded: `performance_daily_lot.sql` does not JOIN or SELECT `PJ_BOP`.
- Options for `pj_types`/`packages`/`pj_functions` from shared `container_filter_cache`.
- Options for `reasons` from `reason_filter_cache` via `GET /api/reject-history/options`.

Added by changes `rh-primary-prefilter` (fields 1–3) and `rh-remove-supplementary-filter` (field 4 + supplementary removal).


### §3.22 DB Scheduling Queue Row (`GET /api/db-scheduling/queue`)

Added by change `add-db-scheduling-page`. One row per recommended equipment per D/B-START lot. Source: `DWH.DW_MES_LOT_V` (5-min WIP cache). Sort: `PACKAGE_LEF ASC → PJ_TYPE ASC → WAFERLOT ASC → UTS ASC` (NULLS LAST on all sort keys). Sync-only; no spool.

| column | type | nullable | notes |
|---|---|---|---|
| lotId | string | no | `LOTID` — lot display ID |
| workflowName | string | no | `WORKFLOWNAME` — used for primary equipment match (DB-02) |
| packageLef | string | yes | `PACKAGE_LEF` — sort key 1; null sorted last |
| pjType | string | yes | `PJ_TYPE` — sort key 2; null sorted last |
| waferLot | string | yes | `WAFERLOT` — sort key 3; null sorted last |
| uts | string | yes | `UTS` — sort key 4; format `YYYY/MM/DD`; null sorted last |
| qty | integer | no | `QTY` — lot quantity |
| bop | string | yes | `BOP` — used for fallback routing (DB-03); null if not set |
| eqpPackageLef | string | yes | Running lot's `PACKAGE_LEF` on candidate equipment — priority-column key (primary) |
| eqpPjType | string | yes | Running lot's `PJ_TYPE` on candidate equipment — priority-column key (secondary) |
| eqpWaferLot | string | yes | Running lot's `WAFERLOT` on candidate equipment — priority-column key (tertiary) |
| eqpUts | string | yes | Running lot's `UTS` on candidate equipment — priority-column key (quaternary) |
| targetSpec | string | no | DB process SPEC on which the recommended equipment was found (DB-00 list) |
| equipment | string | no | Single equipment ID from `EQUIPMENTS`; one row per equipment |
| matchSource | string | no | Closed enum: `"workflow"` (DB-02) / `"bop-fallback"` (DB-03) / `"none"` (no recommendation) |

**Cardinality:** One D/B-START lot may produce multiple rows (one per distinct recommended equipment). A lot with no recommendation produces zero rows (not an error). Consumers must group by `lotId` for per-lot views.

**Null handling:** Null `bop` → fallback not taken → `matchSource = "none"`, no row emitted. Null sort keys → row emitted normally; sort treats null as NULLS LAST. Null `EQUIPMENTS` at DB process SPECs → excluded from primary match pool (DB-02).

---

## CHANGELOG
## [data 1.40.0] — 2026-07-14
### Changed (BREAKING)
- production-achievement-overhaul: §3.28.1 SPECNAME-grain parquet schema widens to SPECNAME+PACKAGE_LF grain (`(output_date, shift_code, SPECNAME, PACKAGE_LF)`) — new nullable `PACKAGE_LF` column; `_PA_SPOOL_SCHEMA_VERSION` 1→2 (stale v1 parquets self-heal by key-mismatch; optional `rm -f tmp/query_spool/production_achievement/*.parquet` fast-forward). §3.28.4 envelope's `data` grows from 2 to 5 inline arrays (breaking under the same `ProductionAchievementReportResponse` schema name — see api-contract.md Compatibility Notes).

### Added
- production-achievement-overhaul: New §3.30 (`production_achievement_package_lf_map` MySQL table — D1 sparse/fallback-to-self default). New §3.31 (`production_achievement_workcenter_merge_map` MySQL table — D2 explicit-inclusion/exclude-by-absence default; explicitly the OPPOSITE of §3.30). New §3.32 (`production_achievement_daily_plans` MySQL table — keyed `(workcenter_group, package_lf_group)`, no shift dimension; independent of and additive to §3.26/`production_achievement_targets`). New §3.33 (`package_lf_map`/`workcenter_merge_map` inline array shapes, injected in the §3.28.4 envelope) and §3.34 (`daily_plan_map` inline array shape). §3.25/§3.26/§3.27/§3.28.2/§3.28.3 unchanged. See business-rules.md PA-09..PA-15 and ADR-0016's Extension section (production-achievement-overhaul) for the full current client-side join chain.

## [data 1.36.0] — 2026-07-07
### Changed
- eap-event-alarm-semantics: §3.17 schema_version 4→5 — new `ALARM_SOURCE` column (raw `EVENT_TYPE`, part of the SET/CLEAR pairing key); Oracle event-type predicate widened to include Shape B alarm-alias rows (`EQP_SECS_EVENT` + `AlarmDetected`/`AlarmCleared`; `ProcessAlarm`/MTBA-MTBF excluded); cross-channel dedup at spool-write drops Shape B occurrences duplicating a Shape A occurrence on `(EQP_ID, ALARM_ID)` within ±60s (measured 70.43% GDBA overlap). Parquet column table corrected to the actual occurrence-level layout (documented table had drifted, still describing the retired v1 event-level column set). Detail response gains additive `alarm_source` field (null for pre-v5 spools via DESCRIBE fallback); stale `eqp_types` coarse-filter mapping row corrected to `EQUIPMENT_ID IN` (EA-07). Deploy: no manual parquet rm (key bump orphans v4); rollback: orphaned v5 files expire by TTL/cleanup daemon.

## [data 1.34.0] — 2026-07-02
### Added
- production-achievement-kanban: §3.25 Production-Achievement Rate Row (grouped by output_date + shift_code + workcenter_group; actual_output_qty, target_qty nullable, achievement_rate nullable-never-Infinity). §3.26 new MySQL target-value table `production_achievement_targets` (shift_code + workcenter_group keyed, no date dimension, direct mysql_client read/write, MYSQL_OPS_ENABLED=false degrades reads to null-target not 500, writes 503 when disabled). §3.27 new MySQL permission table `production_achievement_edit_permissions` (single-flag whitelist, absence = default-deny, fail-closed on MySQL unavailability). Additive; no existing schemas changed.

## [data 1.33.0] — 2026-07-01
### Added
- yield-alert-kpi-csv-parity: §3.16.7 Alerts CSV Numeric Export Formatting — `_buildAlertsCSV()` must round `transaction_qty`/`scrap_qty` (post-`toPcs()`) to whole pcs instead of writing raw `String(floatValue)`, eliminating DuckDB-DOUBLE float-noise (e.g. `4011.9999999999995`) that caused Excel to treat cells as text and skip them in `SUM()`. See business-rules.md YA-13 for the related KPI/alert-candidate scope unification.

## [data 1.32.0] — 2026-07-01
### Changed
- yield-alert-filter-expansion: §3.16.4 `process_type` scope table expands from 2 to 6 rows (`GA%`/`GC%`/`GD%`/`F%`/`W%`/`D%`) with `WIP_CLASS_CODE` domain mapping. New §3.16.5 documents the `workcenter_groups` payload shape change for `GET /api/yield-alert/view` and `GET /api/yield-alert/cross-filter-options` (global `filter_cache` → per-query_id spool `SELECT DISTINCT DEPARTMENT_NAME`; breaking value semantics, JSON key unchanged). New §3.16.6 flags the DuckDB-WASM client parity requirement. `GET /api/yield-alert/filter-options` and other `filter_cache` consumers unaffected.

## [data 1.28.0] — 2026-06-29
### Added
- msd-type-package-filter: §2.13 (MSD Container-Filter-Options Response — GET /api/mid-section-defect/container-filter-options). Shape mirrors §2.7 (production-history filter-options): data={pj_types, packages, bops, pj_functions} arrays; meta={updated_at, schema_version} (D-CR-01: not in data). Same Redis key and 24h TTL as §2.7 (shared container_filter_cache). bops/pj_functions returned but not consumed by analysis endpoint. Analysis response shape unchanged under pj_types[]/packages[] filtering. Additive; no existing schemas changed.

## [data 1.27.0] — 2026-06-26
### Added
- add-db-scheduling-page: §3.22 DB Scheduling Queue Row — 15-column shape (11 lot/dispatch fields + 4 eqp* priority-column keys from running lot on candidate equipment: `eqpPackageLef`, `eqpPjType`, `eqpWaferLot`, `eqpUts`). One row per equipment per D/B-START lot; sort keys PACKAGE_LEF/PJ_TYPE/WAFERLOT/UTS (NULLS LAST); matchSource closed enum; sync-only; null BOP → zero rows. Additive; no existing schemas changed.

## [data 1.26.0] — 2026-06-25
### Added
- rh-remove-supplementary-filter: §2.12 extended — added `reasons[]` as the 4th BASE_WHERE prefilter field. SQL form: `NVL(TRIM(r.LOSSREASONNAME), '(未填寫)') IN (:reason_0, ...)`. Sentinel `(未填寫)` for null/blank LOSSREASONNAME is distinct from container-level `(NA)`. Bind prefix `reason_`. Options from `reason_filter_cache` via `GET /api/reject-history/options`. Updated JSON example (4 fields), field table (4 rows), parity rule (now covers all 4 fields). Added `(未填寫)` sentinel subsection. Added supplementary filter layer removal note (`{{ WHERE_CLAUSE }}` layer removed; `workcenter_groups` no longer a valid param). §3.18 cache-key composition note: `reject_dataset` `query_id_input` gains `reasons` key; parquet column schema unchanged; no forced purge needed. Additive to §2.12; supplementary-layer removal is a behavioral change with no data schema impact.

## [data 1.25.0] — 2026-06-25
### Added
- rh-primary-prefilter: §2.12 (Reject-History Primary Query request-side filter params). Documents three new
  optional JSON body fields (`pj_types[]`, `packages[]`, `pj_functions[]`) on `POST /api/reject-history/query`.
  Specifies `{{ BASE_WHERE }}` injection point (Oracle-layer, before GROUP BY in `reject_raw` CTE),
  `NVL(TRIM(col), '(NA)')` NULL-sentinel semantics (NULL container → `(NA)`, not silently dropped;
  selecting `(NA)` returns NULL-container rows), distinction from `{{ WHERE_CLAUSE }}` supplementary filter
  layer, parity rule (sync+async paths identical), spool/cache key inclusion rule, and `PJ_BOP` explicit
  exclusion. Additive; no existing schemas changed.


## [data 1.24.0] — 2026-06-24
### Changed (BREAKING)
- nav-config-to-code: `data/page_status.json` shrunk from full-CMS shape (`{pages, drawers, db_scan, api_public}`) to `{api_public, statuses}`. `api_public` preserved (MUST NOT drop — gates `is_api_public()` site-wide auth bypass). Back-compat read: legacy full-CMS file derives statuses from `pages[].status`, no error.

### Added
- nav-config-to-code: §3.11a (Writable Page-Status Store shape — `{api_public, statuses}`; back-compat read; write path; rollback-safe semantics). §3.11b (Navigation Manifest — frontend code-owned structure SOT; drawer id map with renamed ids, distinct orders, display names verbatim; constraints). §2.10 (`GET /admin/api/pages` slimmed payload — route+status only). §2.11 (`GET /api/portal/navigation` status feed payload — statuses map + auth fields, no drawers).

## [data 1.23.0] — 2026-06-19
### Added
- downtime-duckdb-join-migration: §3.21 (Downtime Analysis Enriched Spool Schema — UNCHANGED Assertion for P5 migration). Documents the `query_downtime_dataset` enriched bridged-spool column set (20 columns: event_id, resource_id, status, reason, category, start_ts, end_ts, hours, fragment_count, match_source, match_ambiguous, job_id, job_order_name, job_model, symptom, cause, repair, handler, wait_min, repair_min). Asserts both legacy `_bridge_jobid` Path B and unified `DowntimeJob` paths produce identical column sets. Explicitly scopes assertion to `query_downtime_dataset` only — `query_downtime_dataset_raw` two-spool path (§3.13) has a different column set and is OUT OF SCOPE for this migration (design D6). No parquet cleanup required on deploy/rollback. Additive; no existing schemas changed.

## [data 1.22.0] — 2026-06-19
### Added
- material-trace-streaming-migration: §3.20 (spool-schema-UNCHANGED assertion for `material_trace` namespace). Explicit non-goal: P4 migration does not change spool parquet schema. 13-column set identical between legacy and unified paths (AC-4). No parquet cleanup required on deploy/rollback. Additive; no existing schemas changed.

## [data 1.21.0] — 2026-06-19
### Added
- resource-history-migration: §3.19 (spool-schema-UNCHANGED assertion for `resource_dataset` and `resource_oee` namespaces). Explicit non-goal: P3 migration does not change spool parquet schemas. No parquet cleanup required on deploy/rollback. Standard breaking-change policy (schema-version bump + cleanup) applies to any future column change. Additive; no existing schemas changed.

## [data 1.31.0] — 2026-06-30
### Changed
- eap-alarm-coarse-filter: §3.17 updated — schema_version 2→3; added spool-key dimensions table (all 5 coarse dims); Oracle coarse-filter mapping table (EXISTS semi-join semantics, DW_C_CONTAINERNAME index); updated eqp_types_filter column notes; product-filter-options payload shape `{pj_types, product_lines, pj_bops, updated_at}` with cold-cache empty-arrays invariant. Additive; no existing parquet columns removed.

## [data 1.20.0] — 2026-06-19
### Added
- production-reject-history-migration: §3.18 (spool-schema-UNCHANGED assertion for `production_history` and `reject_dataset` namespaces). Explicit non-goal: P2 migration does not change spool parquet schemas. No parquet cleanup required on deploy/rollback. Standard breaking-change policy (schema-version bump + cleanup) applies to any future column change. Additive; no existing schemas changed.

## [data 1.18.0] — 2026-06-18
### Added
- eap-alarm-analysis: Added §3.17 (EAP ALARM Spool Schema) documenting 10-column parquet schema (EVENT_ID, EQP_ID, EQP_TYPE, LOT_ID, ALARM_TEXT, ALARM_CATEGORY_CODE, ALARM_CATEGORY, ALARM_TIME, DETAIL_PARAMS, eqp_types_filter), breaking-change surface rule (parquet cleanup + _SCHEMA_VERSION bump on schema change), and 5 DuckDB-derived response shapes (filter-options, summary, pareto, trend, detail). Additive; no existing spool schemas changed.

## [data 1.17.0] — 2026-06-16
### Added
- yield-alert-spool-refactor: Added §3.16 (Yield-Alert Dataset Spool Schema) documenting the `yield_alert_dataset` spool column schema (10 columns: WIP_ENTITY_NAME, LINE, TYPE, PACKAGE, TXN_DATE, TX_QTY, SCRAP_QTY, SOURCE_CODE, REJECT_LINKED, process_type), SOURCE_CODE invariant (NOT NULL ⇒ TX_QTY=0), PACKAGE filter removal invariant (GA% has 0 NA rows), process_type scope table, and breaking-change surface rule (parquet cleanup on deploy/rollback). Additive; no existing spool schemas changed.

## [data 1.16.0] — 2026-06-16
### Added
- hold-overview-export-csv: Added §3.15 (Hold-Overview Lots Export Column Set) — 13-column CSV schema (lotId, workorder, qty, product, package, workcenter, holdReason, spec, age, holdBy, dept, holdComment, futureHoldComment), display order, CSV format rules (UTF-8 BOM, RFC 4180 escaping, null-as-empty), filename convention, client-side assembly note, and row boundary placeholder (TBD ≤ 10,000; env var `HOLD_OVERVIEW_EXPORT_MAX_ROWS`). Additive; no existing schemas changed.

## [data 1.11.0]
- ai-pipeline-upgrade (2026-05-29): Added §2.9 (AI Session Store Shape including `chat_history` pairs, cap 8/16, TTL, pop-preservation semantics) and three new AI function param schemas (`production_history_query` raw_params dispatch, `resource_history_summary` kwargs, `qc_gate_status` no-params). Added `normalize_chart_data` output for `qc_gate_status` (→ stations list) and pass-through for `production_history_query`/`resource_history_summary`. Additive; no existing schemas changed.

## [data 1.10.0]
- add-package-detail-tables (2026-05-22): Added §3.11 documenting hold-history detail row schema with new `package: string | null` field. Updated §3.6 (query-tool lot-history / equipment-lots) with new `PRODUCTLINENAME: string | null` field, `_PARTIAL_NONKEY_COLS_LOT` extension note, and CSV export column order. Updated §3.9.2 (material-consumption detail spool) with new `PRODUCTLINENAME: VARCHAR | null` column (detail spool schema breaking-change surface — parquet cleanup required on deploy/rollback). §3.7 (equipment-rejects) already had PRODUCTLINENAME documented — no change. All additive; no existing columns removed or renamed.

## [data 1.9.0]
- resource-status-package-group (2026-05-21): Added §3.10 documenting the merged resource-status record shape (all 35+ fields). New field PACKAGEGROUPNAME (string | null) added to each record; NULL for ~91% of resources (PACKAGEGROUPID is null in DWH.DW_MES_RESOURCE). Lookup via 46-row in-process dict (DW_MES_RESOURCE_PACKAGEGROUP, 7-day TTL, independent of 24h resource_cache cycle). No existing fields removed or renamed.

## [data 1.8.0]
- material-part-consumption (2026-05-20): Added §3.9 with summary spool schema (8 columns: txn_date, material_part, pj_type, primary_category, total_consumed, total_required, lot_count, workorder_count) and detail spool schema (mirrors forward_by_lot.sql columns + pj_type). New spool namespaces only; no existing schemas changed.


### §3.23 MSD Forward Lineage Stage Spool

**namespace**: `msd-events`  **path pattern**: `tmp/query_spool/msd-events/<trace_query_id>_lineage.parquet`

| column | type | nullable | notes |
|---|---|---|---|
| SEED_ID | VARCHAR | N | Detection defect-lot CONTAINERID; BFS root of children_map |
| DESCENDANT_ID | VARCHAR | N | Every descendant including self |

**Invariants:**
- Self-edge `(SEED_ID, SEED_ID)` always emitted (even when children_map is empty — "degraded-lineage" path).
- No duplicate `(SEED_ID, DESCENDANT_ID)` rows (seen-set deduplication during BFS traversal).
- SEED_ID is denormalized at write time (spool write), NOT computed at query time via JOIN.
- `get_summary(direction="forward")` MUST NOT return None when events spool exists, even if lineage spool is absent — degrades to self-edge-only logic.

**Schema change policy:**  
`_STAGE_FORWARD_LINEAGE` version bump required (`_TRACE_QUERY_ID_SCHEMA_VERSION += 1`) + `rm -f tmp/query_spool/msd-events/*_lineage.parquet` on both deploy and rollback runbook.

**Registration**: `register_stage_spool_file(trace_query_id, _STAGE_FORWARD_LINEAGE, path)` via `query_spool_store`.

### §3.24 Forward Cause-Effect Aggregation Payloads

These payloads are computed in `mid_section_defect_service.py` and returned by `GET /api/mid-section-defect/analysis?direction=forward`.

#### §3.24.1 by_detection_loss_reason

Array of `{loss_reason: str, reject_qty: int, input_qty: int, lot_count: int, reject_rate: float[0..1]}` sorted descending by `reject_qty`. TOP_N=10; rows beyond TOP_N are folded into a synthetic `"其他"` row. Per reason, `input_qty` = Σ trackinqty over the lots carrying that reason and `lot_count` = number of such lots (**membership cohort** — a lot with multiple front reasons counts toward each, so Σ input_qty across reasons can exceed the detection-cohort total). `reject_rate = reject_qty / input_qty` (defect rate among lots that had that reason, NOT ÷ whole-cohort total). The `"其他"` row's `input_qty`/`lot_count` are over the UNION of folded reasons' lots (no double-count).

#### §3.24.2 loss_reason_workcenter_crosstab

Sparse cross-tab:
```
{
  loss_reasons: string[],        # TOP_N detection loss reasons (ascending by crosstab order)
  workcenter_groups: string[],   # downstream stations seen in forward attribution
  cells: [{loss_reason, workcenter_group, reject_qty: int, reject_rate: float}]
}
```
Zero-count cells omitted (sparse). `reject_rate` = workcenter-specific reject_qty / total_trackinqty for that loss_reason cohort.

#### §3.24.3 downstream_trend

Array of `{date: "YYYY-MM-DD", reject_qty: int, reject_rate: float}` sorted ascending by date. Covers downstream reject events over the same date-range query window. `reject_rate = downstream_reject_qty / detection_input_qty` (normalized to detection cohort size so rates are comparable across dates).

#### §3.24.4 amplification

`float | null` — downstream_reject_rate ÷ detection_reject_rate over the SAME SEED_ID flagged cohort.

| condition | value | display |
|---|---|---|
| detection_reject_rate = 0 | null | "—" |
| downstream = 0 AND detection > 0 | 0.0 | "0.0x" |
| both > 0 | downstream_rate / detection_rate | "Nx" |

Within-cohort ratio, NOT flagged-vs-clean lift.

#### §3.24.5 by_front_downstream_reason_matrix

前段報廢原因 × 下游報廢原因 關聯矩陣. Built by `_build_front_downstream_reason_matrix`. For every downstream reject (re-keyed to its detection SEED via the forward lineage spool), the downstream `LOSSREASONNAME` is attributed to EACH front-stage loss reason the seed lot was scrapped for (**cohort-membership** semantics — a lot scrapped for both NSOP and NSOL contributes its descendants' downstream rejects to BOTH rows, so the sum of cells can exceed the physical downstream reject total).

```
{
  rows: [{name: str, total: int}, ...],   # front-stage loss reasons, TOP_N=10 + synthetic "其他", desc by total
  cols: [{name: str, total: int}, ...],   # downstream loss reasons, TOP_N=10 + synthetic "其他", desc by total
  cells:   int[][],     # rows.length × cols.length, raw downstream reject qty
  row_pct: float[][],   # same shape, each row normalized to 100% across its columns (0.0 when row total = 0)
}
```

Empty result (no defect seeds / no downstream rejects) → `{rows: [], cols: [], cells: [], row_pct: []}`. Additive field on `direction=forward`; absent on `direction=backward`. `row_pct` is the primary display (frontend heat-table shades by row %) so cohort-overlap double-counting does not distort within-row reading.

### §3.25 Production-Achievement Rate Row (`GET /api/production-achievement/report`)

One row per `(output_date, shift_code, workcenter_group)` group. Rows are produced by grouping PA-05-qualifying `DW_MES_LOTWIPHISTORY` trackout events (business-rules.md PA-06) and joining against the target-value table (§3.26) on `(shift_code, workcenter_group)`.

| field | type | required |
|---|---|---|
| output_date | string | yes |
| shift_code | string | yes |
| workcenter_group | string | yes |
| actual_output_qty | integer | yes |
| target_qty | integer | yes |
| achievement_rate | number | yes |

Notes: `output_date` is `YYYY-MM-DD`, with business-rules.md PA-03/PA-04 cross-night attribution already applied. `shift_code` is a closed enum: `N | D` (current two-shift regime) or `A | B | C` (historical three-shift regime, only for rows in the 2020/01/01–2020/03/29 window) — business-rules.md PA-01/PA-02. `workcenter_group` is the 大站點/PACKAGE dimension sourced from `filter_cache.get_spec_workcenter_mapping()` `WORK_CENTER_GROUP` (business-rules.md PA-06) — no new SPECNAME→station mapping is introduced. `actual_output_qty` is `SUM(TRACKOUTQTY)` over PA-05-qualifying rows in this group; `0` when no qualifying rows (not null). `target_qty` is nullable in practice (see §3.26) even though marked required — it is `null` when no target row exists for this `(shift_code, workcenter_group)` combination. `achievement_rate` is nullable — `actual_output_qty / target_qty`, `null` when `target_qty` is missing or `0` (business-rules.md PA-07); never `Infinity`.

Row-grain rule: one row per distinct `(output_date, shift_code, workcenter_group)` combination observed in the qualifying trackout set for the requested date range — NOT a dense cross-product with target rows that have no matching output (a `(shift_code, workcenter_group)` target with zero output in the date range does not synthesize a zero-output row; only groups with ≥1 qualifying trackout event in range appear). Sort order: `output_date ASC, shift_code ASC, workcenter_group ASC`.

**Compute-location note (production-achievement-async-spool, ADR-0016):** As of this change, `GET /api/production-achievement/report` no longer returns this row shape directly — see §3.28 for the actual server response (async spool + inline maps). This section (`ProductionAchievementReportRow`) is retained as (a) the shape the frontend computes client-side in DuckDB-WASM from the §3.28 spool + maps, and (b) the test-only golden-reference shape produced by `build_achievement_rows()` for the dual-tier parity gate (business-rules.md PA-06/PA-07). Row-grain, nullability, and formula semantics are unchanged — only the computation LOCATION and the wire format changed.

### §3.26 Production-Achievement Target-Value Table (MySQL, `production_achievement_targets`)

New independent MySQL table, read/written directly via `core/mysql_client.py` (NOT via the SQLite `core/sync_worker.py` dual-layer path — see the change's design.md for the immediate-consistency rationale). No date dimension: one row per `(shift_code, workcenter_group)`; the same target value is reused for every `output_date`.

| field | type | required |
|---|---|---|
| id | integer | yes |
| shift_code | string | yes |
| workcenter_group | string | yes |
| target_qty | integer | yes |
| updated_at | string | yes |
| updated_by | string | yes |

Notes: `id` is the primary key (auto-increment). `shift_code` is a closed enum `N \| D \| A \| B \| C` (business-rules.md PA-01/PA-02); part of a unique key with `workcenter_group`. `workcenter_group` must match a value producible by `filter_cache.get_spec_workcenter_mapping()`; part of the same unique key. `target_qty` is a non-negative integer — the denominator for achievement-rate calculation (business-rules.md PA-06/PA-07); negative or non-numeric input is rejected with 400 `VALIDATION_ERROR` at the API layer before reaching MySQL. `updated_at` is a server-side ISO-8601 timestamp updated on every write. `updated_by` is the username/account of the last editor (audit trail).

Constraints: unique constraint on `(shift_code, workcenter_group)` — exactly one target row per combination; writes are upsert (`INSERT ... ON DUPLICATE KEY UPDATE`), never append-only history. No `output_date` column — this table is explicitly date-independent (目標值固定值，重複使用於每天). When `MYSQL_OPS_ENABLED=false`, read endpoints MUST degrade to returning `target_qty: null` for all groups (achievement_rate becomes null via PA-07), NOT a 500. Write endpoints MUST return 503 `SERVICE_UNAVAILABLE` when MySQL OPS is disabled (write cannot degrade gracefully — there is nowhere else to persist it).

### §3.27 Production-Achievement Permission Table (MySQL, `production_achievement_edit_permissions`)

New independent MySQL table, read/written directly via `core/mysql_client.py`. Single-flag whitelist: presence of a row for a user with `can_edit_targets = true` = that user may edit target values. This is NOT a general permission framework — one boolean-shaped capability only, and is independent of the existing `is_admin`/`admin_required` gate in `core/permissions.py`.

| field | type | required |
|---|---|---|
| id | integer | yes |
| user_identifier | string | yes |
| can_edit_targets | boolean | yes |
| granted_at | string | yes |
| granted_by | string | yes |

Notes: `id` is the primary key (auto-increment). `user_identifier` is the account/username matching the auth session identity (e.g. LDAP username); unique. `can_edit_targets` is the single flag this table exists to hold. `granted_at` is when the whitelist entry was created (ISO-8601). `granted_by` is the admin account that granted the permission (audit trail).

Constraints: unique constraint on `user_identifier`. Absence of a row for a user is the default-deny state — permission check MUST fail closed (deny) both when the table has no row for the user AND when MySQL is unreachable/`MYSQL_OPS_ENABLED=false` (never fail-open to allow). This table is managed exclusively via the new Admin permission-management endpoints (api-contract.md); no direct end-user-facing read of this table beyond "am I allowed" resolved server-side.

### §3.28 Production-Achievement Async Spool Schema (`GET /api/production-achievement/report`, browser-DuckDB path)

Added by change `production-achievement-async-spool` (ADR-0016); extended by change `production-achievement-overhaul` to a PACKAGE_LF-aware grain plus three additional inline maps (§3.33/§3.34) — see ADR-0016's Extension section for the full current join chain. Replaces the synchronous Oracle-backed row response (§3.25 is retained as the frontend-computed / parity-golden-reference row shape only). The RQ worker (`ProductionAchievementJob`, `BaseChunkedDuckDBJob` subclass, `chunk_strategy=TIME`, `requires_cross_chunk_reduction=False` with a re-aggregating `post_aggregate`) writes one SPECNAME+PACKAGE_LF-grain parquet per canonical spool key. PA-06 (SPECNAME→workcenter_group rollup), PA-09/PA-10 (PACKAGE_LF/workcenter_group merge-mapping), and PA-07/PA-12/PA-13 (target/daily-plan join + achievement_rate, both shift-keyed and daily/cumulative variants) are computed entirely client-side in DuckDB-WASM from this spool plus the five inline maps below (§3.28.2, §3.28.3, §3.33 ×2, §3.34); no server-side Python performs this computation on the request path.

**Canonical spool key**: `(start_date, end_date, _PA_SPOOL_SCHEMA_VERSION)` — **date-range only**. `shift_code`/`workcenter_group` request query params do NOT participate in the spool key and do NOT filter the spooled dataset server-side; the full PA-05-qualifying dataset for the date range is always spooled, and any shift_code/workcenter_group narrowing is applied client-side after download (ADR-0016), so changing these two filters never requires a new Oracle fetch or a new spool file.

**`_PA_SPOOL_SCHEMA_VERSION`**: integer constant, participates in the spool key. Bumping it orphans stale parquets by key (no manual `rm` needed on ordinary bumps). Schema-breaking rollback additionally requires `rm -f tmp/query_spool/production_achievement/*.parquet` in the same commit as the version bump (cache-spool-patterns.md).

#### §3.28.1 SPECNAME+PACKAGE_LF-grain Parquet Schema

Source: `sql/production_achievement.sql` (PA-05 predicate preserved verbatim), fanned out per TIME chunk, re-aggregated in `post_aggregate` via `GROUP BY output_date, shift_code, SPECNAME, PACKAGE_LF` `SUM(actual_output_qty)` (seam-safe — ADR-0016; grain widened from 3 to 4 dimensions by change `production-achievement-overhaul`, business-rules.md PA-09).

| column | DuckDB type | nullable | description |
|---|---|---|---|
| output_date | DATE | no | PA-03/PA-04 cross-night-attributed output date (already shifted) |
| shift_code | VARCHAR | no | Closed enum `N \| D` (current) or `A \| B \| C` (historical 2020/01/01–2020/03/29 window) — PA-01/PA-02 |
| SPECNAME | VARCHAR | no | Raw station spec name (`WC.SPECNAME`); NOT yet rolled up to `workcenter_group` — that join happens client-side via §3.28.2/§3.33 |
| PACKAGE_LF | VARCHAR | yes | Raw `DW_MES_LOTWIPHISTORY.PACKAGE_LF` value (`VARCHAR2(60)` at Oracle; 37 distinct non-null values observed year-to-date at the time of this change); NULL when the source row's PACKAGE_LF is null/blank. NOT yet rolled up to `package_lf_group` — that join happens client-side via §3.33 (business-rules.md PA-09). Added by change `production-achievement-overhaul`. |
| actual_output_qty | BIGINT | no | `SUM(TRACKOUTQTY)` over PA-05-qualifying rows for this `(output_date, shift_code, SPECNAME, PACKAGE_LF)` group, re-aggregated across chunk seams |

Row-grain: one row per distinct `(output_date, shift_code, SPECNAME, PACKAGE_LF)` combination with ≥1 PA-05-qualifying trackout event in range — same "no dense cross-product" rule as §3.25, now two levels finer (SPECNAME and PACKAGE_LF instead of workcenter_group and package_lf_group, since neither rollup has happened yet). NULL `PACKAGE_LF` is its own distinct GROUP BY bucket (SQL NULL-grouping semantics), separate from any non-null value — it resolves to the `"(未分類)"` sentinel client-side (business-rules.md PA-09), not at spool-write time. A `SPECNAME` with no entry in `spec_workcenter_map` (§3.28.2) is still present in this parquet — unmapped-SPECNAME exclusion (PA-06) happens client-side during the rollup join, not at spool-write time.

**Empty-result invariant**: a date range with zero PA-05-qualifying rows (or all-unmapped SPECNAMEs) still writes a valid empty parquet with this schema (0 rows) — never omits the file or errors. The browser must render an empty table, never an error, for a 200 response whose parquet has 0 rows.

**Breaking parquet-schema change**: `_PA_SPOOL_SCHEMA_VERSION` bumps `1` → `2` in this change (new `PACKAGE_LF` column) — stale v1 parquets self-heal by key mismatch (no manual `rm` required on ordinary bumps); an optional `rm -f tmp/query_spool/production_achievement/*.parquet` fast-forward is documented in ci-gates.md §Rollback Policy.

#### §3.28.2 `spec_workcenter_map` (inline-injected, HTTP 200 spool-hit response)

Array of rows, sourced from `services/filter_cache.get_spec_workcenter_mapping()` (same source as the retired server-side PA-06). Injected inline in the `GET /report` 200 response (§3.28.4) — not a separate endpoint (Q2 design decision).

| field | type | required |
|---|---|---|
| SPECNAME | string | yes |
| workcenter_group | string | yes |

Notes: `workcenter_group` is `get_spec_workcenter_mapping()`'s `WORK_CENTER_GROUP` field, renamed for consistency with §3.25. Field name `SPECNAME` (uppercase) is deliberate — it must exactly match the §3.28.1 spool column name so the browser can `JOIN spool.SPECNAME = map.SPECNAME` without aliasing. This is the FULL current mapping (not scoped to SPECNAMEs present in this spool); a spool `SPECNAME` with no match is excluded from the client-computed rollup (PA-06 unmapped-SPECNAME exclusion, now applied client-side).

#### §3.28.3 `targets_map` (inline-injected, HTTP 200 spool-hit response)

Array of rows, sourced from `services/production_achievement_target_service.get_targets_map()` (same source as `GET /api/production-achievement/targets`). Injected inline alongside `spec_workcenter_map` (Q2 design decision, mirrors `resource_history`'s `resource_metadata` inline-injection pattern).

| field | type | required |
|---|---|---|
| shift_code | string | yes |
| workcenter_group | string | yes |
| target_qty | integer \| null | yes |

Notes: One row per `(shift_code, workcenter_group)` with a stored target row (§3.26) — a combination with NO target row is simply absent from this array; the browser's LEFT JOIN naturally yields `target_qty = null` for any rolled-up `(shift_code, workcenter_group)` absent from this array (PA-07 missing-target-row semantics unchanged). When `MYSQL_OPS_ENABLED=false`, `get_targets_map()` degrades to an empty array (never 500) — every client-computed row gets `target_qty = null` / `achievement_rate = null`, consistent with §3.26's flag-off degradation rule.

#### §3.28.4 `GET /api/production-achievement/report` Envelope

**HTTP 200 — spool-hit** (canonical spool for `(start_date, end_date)` already exists — including immediately after a poll-completion re-fetch, see api-contract.md Compatibility Notes):

```json
{
  "success": true,
  "data": {
    "query_id": "<string>",
    "spool_download_url": "/api/spool/production_achievement/<query_id>.parquet",
    "spec_workcenter_map": [ { "SPECNAME": "...", "workcenter_group": "..." } ],
    "targets_map": [ { "shift_code": "...", "workcenter_group": "...", "target_qty": 500 } ],
    "package_lf_map": [ { "raw_package_lf": "...", "merged_group": "..." } ],
    "workcenter_merge_map": [ { "raw_workcenter_group": "...", "merged_workcenter_group": "..." } ],
    "daily_plan_map": [ { "workcenter_group": "...", "package_lf_group": "...", "daily_plan_qty": 300 } ]
  },
  "meta": { "timestamp": "...", "app_version": "..." }
}
```

Injection is unconditional whenever the canonical spool exists — NOT row-count-gated (unlike `resource_history`'s `total_row_count >= threshold` gate; Q1 overrides the local-compute activation threshold to 0 for this page). `data` grows from 2 to 5 inline arrays as of change `production-achievement-overhaul` — `package_lf_map` (§3.33, D1), `workcenter_merge_map` (§3.33, D2), and `daily_plan_map` (§3.34) are new; `spec_workcenter_map`/`targets_map` (§3.28.2/§3.28.3) are unchanged in shape.

**HTTP 202 — spool-miss** (generic §1.3 async-job envelope):

```json
{
  "success": true,
  "data": {
    "async": true,
    "job_id": "<uuid string>",
    "status_url": "/api/job/<job_id>?prefix=production-achievement"
  },
  "meta": { "timestamp": "...", "app_version": "..." }
}
```

`status_url` reuses the generic `GET /api/job/<job_id>?prefix=<namespace>` endpoint (§1.4) — no domain-specific `/api/production-achievement/job/<job_id>` route, mirroring `resource-history-rq-async`/`downtime-rq-async`/`hold-history-rq-async`.

On `status=finished`, the job `result` payload is `{"query_id": "<string>"}` only (mirrors §3.14.2's downtime pattern) — it does NOT carry `spool_download_url`/`spec_workcenter_map`/`targets_map` directly. The frontend must re-issue the identical `GET /api/production-achievement/report` request; the canonical spool now exists, so this second call takes the 200 spool-hit path above at zero Oracle cost. **Implementation must confirm this against the actual `useProductionAchievementDuckDB.ts` completion handler** — if the job result instead carries the injected fields directly, update this subsection to match.

**HTTP 503 — worker unavailable** (spool miss + `always_async=True` + no RQ worker; `sync_fallback_allowed=False`): standard error envelope (§1.2), `error.code = "SERVICE_UNAVAILABLE"`.

**HTTP 400 — validation** (missing/invalid `start_date`/`end_date`, range > 730d per SYS-04): standard error envelope (§1.2).

---

### §3.29 UPH-Performance Spool Schema

Added by change `add-uph-performance-page`. Spool namespace: `tmp/query_spool/uph_performance/`. Governed by `_SCHEMA_VERSION` in `uph_performance_cache.py`. Mirrors `eap-alarm-analysis`'s always-async (Type B) coarse-spool + DuckDB-derived-views pattern (§3.17).

#### Spool key composition

`make_uph_performance_spool_key()` canonical repr covers (sorted): `date_from`, `date_to`, `families` (closed enum subset of `{GDBA, GWBA}`; empty/absent = both), `workcenter_names`, `packages` (PRODUCTLINENAME), `pj_types` (PJ_TYPE), `equipment_ids` (whitespace-stripped). `_SCHEMA_VERSION = 1` participates in the key.

#### Oracle coarse-filter mapping

| filter dim | Oracle predicate | source column | join |
|---|---|---|---|
| families | `EQUIPMENT_ID LIKE 'GDBA%'` and/or `EQUIPMENT_ID LIKE 'GWBA%'` (both when absent/empty — UPH-02 restricts the domain to these two families only; never any other prefix) | EAP_EVENT.EQUIPMENT_ID | direct |
| equipment_ids | `EQUIPMENT_ID IN (...)` | EAP_EVENT.EQUIPMENT_ID | direct |
| pj_types | `EXISTS (SELECT 1 FROM DWH.DW_MES_CONTAINER c WHERE c.CONTAINERNAME = e.LOT_ID AND NVL(TRIM(c.PJ_TYPE),'(NA)') IN (...))` | DWH.DW_MES_CONTAINER | EXISTS semi-join (mirrors EA-10) |
| packages | `EXISTS (SELECT 1 FROM DWH.DW_MES_CONTAINER c WHERE c.CONTAINERNAME = e.LOT_ID AND NVL(TRIM(c.PRODUCTLINENAME),'(NA)') IN (...))` | DWH.DW_MES_CONTAINER | EXISTS semi-join |
| workcenter_names | `EXISTS (SELECT 1 FROM DWH.DW_MES_RESOURCE r WHERE r.RESOURCENAME = e.EQUIPMENT_ID AND r.OBJECTCATEGORY = 'ASSEMBLY' AND NVL(TRIM(r.WORKCENTERNAME),'(NA)') IN (...))` | DWH.DW_MES_RESOURCE | EXISTS semi-join |

Mandatory index filter (UPH-01, mirrors EA-03): `LAST_UPDATE_TIME BETWEEN :date_from AND :date_to`. Every chunk window is ≤6h (`BaseChunkedDuckDBJob`, `chunk_strategy=TIME`) — the detail JOIN against this ~12M-row/day table has previously timed out at >180s over a 24h window (docs/architecture/eap-event-uph-collection-investigation.md); a single unchunked full-range query is forbidden. Event-type predicate: `EVENT_TYPE LIKE '%_M[60]' AND LOT_ID IS NOT NULL`.

#### Detail JOIN + PARAMETER_NAME mapping (UPH-03)

`EAP_EVENT_DETAIL` joined on `SEQ_ID`. `PARAMETER_NAME` selected by equipment-family prefix — **family-conditional, must not be swapped**:

| family prefix | PARAMETER_NAME |
|---|---|
| GDBA | `BondUPH` |
| GWBA | `fHCM_UPH` |

`PARAMETER_VALUE` is used as-is for the UPH column — **NO scale conversion** (UPH-04; e.g. no `×100`/`÷100`). This is a deliberate product decision, not an oversight — do not "fix" it without a new contract change.

#### Product-dim + workcenter enrichment

- `LOT_ID` → `DW_MES_CONTAINER.CONTAINERNAME` bridge (mirrors `eap_alarm_worker.py`'s pattern — `DW_MES_WIP` has no `CONTAINERID` index) → `PRODUCTLINENAME` (displayed as **Package**), `PJ_TYPE` (displayed as **Type**), `PJ_BOP`, `PJ_FUNCTION`. No container match → all four `NULL`.
- `EQUIPMENT_ID` → `DW_MES_RESOURCE.RESOURCENAME` bridge (`OBJECTCATEGORY = 'ASSEMBLY'`) → `WORKCENTERNAME`. No resource match → `WORKCENTERNAME` `NULL`.
- `WORKCENTERNAME` → `src/mes_dashboard/config/workcenter_groups.py` 焊接_DB/焊接_WB mapping → DB/WB label (UPH-05). **MUST use this mapping — MUST NOT use `EQUIPMENT_ID` prefix enumeration** (a prior prefix-enumeration approach for a similar classification was retired because it never matched real production data; business-rules.md EA-07). Unmapped/NULL `WORKCENTERNAME` → DB/WB label `NULL` (not an error).

#### Parquet column schema (schema_version 1)

| column | type | nullable | notes |
|---|---|---|---|
| LOT_ID | VARCHAR | no | EAP_EVENT.LOT_ID; event-type predicate requires `LOT_ID IS NOT NULL` at Oracle query time |
| EQUIPMENT_ID | VARCHAR | no | EAP_EVENT.EQUIPMENT_ID |
| EQUIPMENT_FAMILY | VARCHAR | no | `SUBSTR(EQUIPMENT_ID, 1, 4)`; closed enum `GDBA \| GWBA` (UPH-02) |
| EVENT_TIME | TIMESTAMP | no | `LAST_UPDATE_TIME` of the `_M[60]` event |
| PARAMETER_NAME | VARCHAR | no | `BondUPH` (GDBA) or `fHCM_UPH` (GWBA) — family-conditional (UPH-03) |
| UPH_VALUE | DOUBLE | yes | raw `PARAMETER_VALUE`, no scale conversion (UPH-04); `NULL` when the detail join finds no matching parameter row for this event |
| WORKCENTERNAME | VARCHAR | yes | `DW_MES_RESOURCE` bridge; `NULL` if no resource match |
| DB_WB_LABEL | VARCHAR | yes | `焊接_DB \| 焊接_WB` via `workcenter_groups` mapping (UPH-05); `NULL` if `WORKCENTERNAME` is `NULL` or unmapped |
| PACKAGE | VARCHAR | yes | `DW_MES_CONTAINER.PRODUCTLINENAME`, displayed as **Package**; `NULL` if no container match |
| PJ_TYPE | VARCHAR | yes | `DW_MES_CONTAINER.PJ_TYPE`, displayed as **Type**; `NULL` if no container match |
| PJ_BOP | VARCHAR | yes | `DW_MES_CONTAINER.PJ_BOP`; `NULL` if no container match |
| PJ_FUNCTION | VARCHAR | yes | `DW_MES_CONTAINER.PJ_FUNCTION`; `NULL` if no container match |
| coarse_filter_hash | VARCHAR | no | hash of the 5 coarse dims (mirrors EA-01's `eqp_types_filter`); used for partition-reuse validation |

**Breaking-change surface:** column add/remove/rename to the `uph_performance` parquet orphans existing files — bump `_SCHEMA_VERSION` in the same commit. Rollback: `rm -f tmp/query_spool/uph_performance/*.parquet`.

#### Response shapes (DuckDB-derived; all fine-filter aware; no Oracle re-query after spool build)

Fine-filter axes (filter-options / trend / detail — global-filter-scoped): `equipment_id[]`, `workcenter_name[]`, `package[]`, `pj_type[]` (all exact-match against the spool).

**Filter-options** (`GET /api/uph-performance/filter-options?query_id=`): `data = {equipment_id_options: string[], workcenter_name_options: string[], package_options: string[], pj_type_options: string[]}`. Derived from the DuckDB spool only; `NULL` column values excluded from option lists.

**Product-filter-options** (`GET /api/uph-performance/product-filter-options`, no `query_id`): Oracle-free, sourced from `container_filter_cache` cross-filter narrowing (mirrors eap-alarm's `/product-filter-options`) — `data = {pj_types: string[], product_lines: string[]}` populated before the user has run any query, so the Package/Type global-filter dropdowns are not empty pre-first-query.

**Trend** (`GET /api/uph-performance/trend`): `data = {labels: string[], series: [{name: string, data: (number|null)[]}], group_by: string}`. `group_by` closed enum (400 on unknown): `equipment_id` | `family` | `package` (default `family`). Native `M[60]` hourly granularity — no day/hour granularity switch (unlike eap-alarm trend). A group's missing hour bucket is `null` in `data[]`, never `0` — a gap must not visually imply zero output.

**Ranking** (`GET /api/uph-performance/ranking`): `data = {items: [{equipment_id: string, workcenter_name: string | null, db_wb_label: string | null, pj_type: string | null, avg_uph: number | null, sample_count: integer}], pj_types: string[]}`. `items` grouped by `equipment_id` (further groupable by `pj_type` client-side), sorted **ascending** by `avg_uph` (lowest-UPH equipment first — the point is finding underperformers). No threshold/alert coloring (explicit non-goal). The `pj_type[]` query param on this endpoint is a **fine filter independent of the page's global filters** — it re-queries the DuckDB spool with its own selection state and does not read or write the global `pj_type` filter; it is NOT part of the spool key (the spool is already built at global scope). `avg_uph` is `null` for an equipment/pj_type combination with zero rows carrying a non-null `UPH_VALUE` (never a divide-by-zero `0`).

**Detail** (`GET /api/uph-performance/detail`): `data = {rows: [{lot_id: string, equipment_id: string, event_time: string (ISO 8601), uph_value: number | null, package: string | null, pj_type: string | null}], meta: {page: int, per_page: int, total_count: int, total_pages: int}}`. Pagination: `per_page` max 200 (mirrors EA-04 detail pagination).

#### Async envelope (mirrors §3.17 / EA-ASYNC; `POST /api/uph-performance/spool`)

**HTTP 200 — spool-hit** (canonical spool for the coarse-filter key already exists):
```json
{ "success": true, "data": { "async": false, "query_id": "<string>" }, "meta": { "timestamp": "...", "app_version": "..." } }
```

**HTTP 202 — spool-miss** (worker available; generic §1.3 async-job envelope):
```json
{ "success": true, "data": { "async": true, "job_id": "<string>", "status_url": "/api/uph-performance/spool/status?job_id=<job_id>", "query_id": "<string>" }, "meta": { "timestamp": "...", "app_version": "..." } }
```

**HTTP 503 — worker unavailable** (`always_async=True`, `sync_fallback_allowed=False` — UPH-ASYNC/ASYNC-06): standard error envelope (§1.2), `error.code = "SERVICE_UNAVAILABLE"`, `Retry-After` header.

**HTTP 400 — validation**: missing/invalid `date_from`/`date_to`, range > 730d (SYS-04), or a `families[]` value outside `{GDBA, GWBA}` (UPH-02).

---

### §3.30 Production-Achievement PACKAGE_LF Merge-Mapping Table (MySQL, `production_achievement_package_lf_map`)

Added by change `production-achievement-overhaul`. Sparse EXCEPTIONS-ONLY table (D1): stores a row only for a raw `PACKAGE_LF` value that must be merged into a differently-named group. Seeded with the ~9 rows behind the 4 confirmed merges (SOD-123FL OP1 + SOD-123FL → SOD-123FL; SOT23-5L + SOT23-6L → SOT23-5L/6L; SOT-543 + SOT-553 + SOT-563 → SOT-543/553/563; TO-277 + TO-277B → TO-277(B)) — NOT all ~37 raw values observed in Oracle year-to-date.

| field | type | required |
|---|---|---|
| id | integer | yes |
| raw_package_lf | string | yes |
| merged_group | string | yes |
| updated_at | string | yes |
| updated_by | string | yes |

Notes: `id` is the primary key (auto-increment); not exposed via the API response row shape (`ProductionAchievementPackageLfMapRow`, api-contract.md) — `DELETE` identifies a row by `raw_package_lf` in the URL path, not by `id`. `raw_package_lf` is the Oracle `DW_MES_LOTWIPHISTORY.PACKAGE_LF` value (`VARCHAR2(60)`); unique. `merged_group` is the display group name this raw value rolls up to. `updated_at`/`updated_by` follow the same audit-trail convention as §3.26/§3.27.

Constraints: unique constraint on `raw_package_lf`. **Default-on-absence (D1 — sparse, fallback-to-self):** a raw `PACKAGE_LF` value with NO row in this table is NOT excluded from the report — it groups under itself (its own raw value becomes its own `package_lf_group`). Client-side resolution is a `LEFT JOIN` (never `INNER JOIN`) plus `COALESCE(merged_group, raw_package_lf, '(未分類)')` — NULL/blank raw `PACKAGE_LF` resolves to the sentinel group `"(未分類)"`. Every raw value Oracle has ever emitted appears in the report under some group — new raw values that appear in Oracle in the future require zero code or table changes to show up (they simply appear as their own group until an admin explicitly adds a merge row). When `MYSQL_OPS_ENABLED=false`, both the CRUD read endpoint and the inline `package_lf_map` (§3.33) degrade to an empty array (never 500) — an empty table under D1's fallback-to-self default means every raw value groups under itself, a valid (if maximally-fragmented) report, not an error state. Write endpoints return 503 `SERVICE_UNAVAILABLE` when MySQL OPS is disabled (same as §3.26/§3.27).

### §3.31 Production-Achievement Workcenter Merge-Mapping Table (MySQL, `production_achievement_workcenter_merge_map`)

Added by change `production-achievement-overhaul`. **Default-on-absence is the OPPOSITE of §3.30**: this table is explicit-inclusion (D2) — it must contain one row for EVERY raw `workcenter_group` (the `WORK_CENTER_GROUP` field from `filter_cache.get_spec_workcenter_mapping()`, business-rules.md PA-06) that should appear in the report at all. Seeded with exactly 12 rows: 焊接_WB→焊接_WB, 焊接_DW→焊接_WB (merge), 焊接_DB→焊接_DB, plus 9 other 1:1 groups (成型/去膠/移印/水吹砂/電鍍/切彎腳/TMTT/品檢/FQC).

| field | type | required |
|---|---|---|
| id | integer | yes |
| raw_workcenter_group | string | yes |
| merged_workcenter_group | string | yes |
| updated_at | string | yes |
| updated_by | string | yes |

Notes: `id` is the primary key (auto-increment); not exposed via the API response row shape (`ProductionAchievementWorkcenterMergeMapRow`, api-contract.md) — `DELETE` identifies a row by `raw_workcenter_group` in the URL path. `raw_workcenter_group` is a `WORK_CENTER_GROUP` value as produced by `filter_cache.get_spec_workcenter_mapping()`; unique. `merged_workcenter_group` is the display group name.

Constraints: unique constraint on `raw_workcenter_group`. **Default-on-absence (D2 — explicit-inclusion, exclude-by-absence — the OPPOSITE default from §3.30's D1 sparse/fallback-to-self):** a raw `workcenter_group` value with NO row in this table is EXCLUDED from the report entirely — it does not appear as its own group, unlike §3.30's fallback behavior. The 15 raw groups intentionally left out (切割/PKG_SAW/點測/可靠性/補鍍/預備站/成品倉/IST/CP線邊倉/成品入庫/已CP入庫/已CP倉/DS線邊倉/MA/TCT) never appear in the production-achievement report as a result. Client-side resolution is an `INNER JOIN` (never `LEFT JOIN`) — mirrors the existing default-deny idiom already used by the permission table (§3.27: absence of a row = fail-closed/deny) rather than the target table's reuse-missing-as-null idiom (§3.26). **This opposite-default pairing with §3.30 is deliberate and must not be "fixed" by copy-pasting one table's join kind onto the other** — see business-rules.md PA-09/PA-10 and ADR-0016's Extension section. When `MYSQL_OPS_ENABLED=false`, the CRUD read endpoint and the inline `workcenter_merge_map` (§3.33) degrade to an empty array (never 500) — but the DOWNSTREAM effect differs from §3.30's degrade: an empty `workcenter_merge_map` means the INNER JOIN matches zero rows, so the ENTIRE report renders empty (not "every raw value shows as its own group" — that fallback behavior belongs to §3.30 only). Write endpoints return 503 `SERVICE_UNAVAILABLE` when MySQL OPS is disabled.

### §3.32 Production-Achievement Daily-Plan Table (MySQL, `production_achievement_daily_plans`)

Added by change `production-achievement-overhaul`. New independent MySQL table, read/written directly via `core/mysql_client.py` (same immediate-consistency rationale as §3.26/§3.27). Keyed by `(workcenter_group, package_lf_group)` — both already-MERGED/resolved values (post §3.30/§3.31 mapping) — with NO shift dimension, unlike `production_achievement_targets` (§3.26, keyed by `(shift_code, workcenter_group)`). The two tables are fully independent: this table is an ADDITIVE new denominator concept for the DailyView/CumulativeView report modes; `production_achievement_targets` and its PA-06/PA-07 formula are completely unaffected and continue to serve whatever other consumer relies on the shift-keyed target.

| field | type | required |
|---|---|---|
| id | integer | yes |
| workcenter_group | string | yes |
| package_lf_group | string | yes |
| daily_plan_qty | integer | yes |
| updated_at | string | yes |
| updated_by | string | yes |

Notes: `id` is the primary key (auto-increment); not exposed via the API response row shape (`ProductionAchievementDailyPlanRow`, api-contract.md). `workcenter_group` must match a `merged_workcenter_group` value produced by §3.31. `package_lf_group` must match a `merged_group` value produced by §3.30 (or a raw fallback-to-self value, per D1). `daily_plan_qty` is a non-negative integer — the denominator for business-rules.md PA-12 (daily achievement rate) and the elapsed-days-scaled denominator for PA-13 (cumulative achievement rate); negative or non-numeric input is rejected with 400 `VALIDATION_ERROR` before reaching MySQL (mirrors §3.26's `target_qty` validation). `updated_at`/`updated_by` follow the same audit-trail convention as §3.26/§3.27. No `output_date` column — this table is explicitly date-independent; the same value is reused for every calendar day (same idiom as §3.26).

Constraints: unique constraint on `(workcenter_group, package_lf_group)` — exactly one plan row per resolved-dimension combination; writes are upsert (`INSERT ... ON DUPLICATE KEY UPDATE`), never append-only history. When `MYSQL_OPS_ENABLED=false`, read endpoints and the inline `daily_plan_map` (§3.34) degrade to an empty array/`daily_plan_qty: null` (never 500) — every client-computed daily/cumulative `achievement_rate` becomes `null`, consistent with §3.26's flag-off degradation rule (PA-12/PA-13). Write endpoints return 503 `SERVICE_UNAVAILABLE` when MySQL OPS is disabled.

### §3.33 `package_lf_map` and `workcenter_merge_map` (inline-injected, HTTP 200 spool-hit response)

Added by change `production-achievement-overhaul`. Two additional arrays injected inline in the `GET /report` 200 response (§3.28.4), alongside the pre-existing `spec_workcenter_map`/`targets_map` (§3.28.2/§3.28.3) — same "inline injection, not a separate endpoint" precedent. Consumed together by the client-side rollup Stage 2 (`pa_rollup`, ADR-0016 Extension).

**`package_lf_map`** — sourced from `services/production_achievement_package_lf_service.get_package_lf_map()` (§3.30).

| field | type | required |
|---|---|---|
| raw_package_lf | string | yes |
| merged_group | string | yes |

Notes: FULL current mapping table content (not scoped to PACKAGE_LF values present in this spool). A spool `PACKAGE_LF` value with no matching row is NOT excluded — client resolves it via `LEFT JOIN` + `COALESCE(merged_group, raw_package_lf, '(未分類)')` (D1, business-rules.md PA-09). When `MYSQL_OPS_ENABLED=false`, this array is empty — every raw value falls back to itself (D1's own default, not an error state).

**`workcenter_merge_map`** — sourced from `services/production_achievement_workcenter_merge_service.get_workcenter_merge_map()` (§3.31).

| field | type | required |
|---|---|---|
| raw_workcenter_group | string | yes |
| merged_workcenter_group | string | yes |

Notes: FULL current mapping table content. A rolled-up `workcenter_group` (from Stage 1, `spec_workcenter_map`) with no matching row here IS excluded from the final rollup — client resolves via `INNER JOIN` (D2, business-rules.md PA-10) — the OPPOSITE join kind from `package_lf_map` above; see ADR-0016's Extension section. When `MYSQL_OPS_ENABLED=false`, this array is empty — the INNER JOIN then matches nothing and the report renders empty for every workcenter_group (D2's own default, not an error state; contrast with `package_lf_map`'s empty-array behavior above).

### §3.34 `daily_plan_map` (inline-injected, HTTP 200 spool-hit response)

Added by change `production-achievement-overhaul`. Sourced from `services/production_achievement_daily_plan_service.get_daily_plans_map()` (§3.32); injected inline alongside the other four maps (§3.28.2/§3.28.3/§3.33).

| field | type | required |
|---|---|---|
| workcenter_group | string | yes |
| package_lf_group | string | yes |
| daily_plan_qty | integer \| null | yes |

Notes: One row per `(workcenter_group, package_lf_group)` with a stored plan row (§3.32) — a combination with NO plan row is simply absent from this array; the browser's `LEFT JOIN` naturally yields `daily_plan_qty = null` for any resolved `(workcenter_group, package_lf_group)` absent from this array (business-rules.md PA-12 missing-plan-row semantics, mirrors PA-07's `targets_map` pattern exactly). Consumed by both `computeDailyView` (daily achievement rate, PA-12) and `computeCumulativeView` (cumulative achievement rate via `daily_plan_qty × elapsed_days`, PA-13). When `MYSQL_OPS_ENABLED=false`, `get_daily_plans_map()` degrades to an empty array (never 500) — every client-computed row gets `daily_plan_qty = null` / `achievement_rate = null`, consistent with §3.26/§3.32's flag-off degradation rule.
