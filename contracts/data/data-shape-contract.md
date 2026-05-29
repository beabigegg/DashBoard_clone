---
contract: data
summary: Data schema, invalid-data handling, and row-level compatibility rules.
owner: application-team
surface: data
schema-version: 1.11.0
last-changed: 2026-05-22
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
    "error": "<string | null>"
  },
  "meta": { "timestamp": "...", "app_version": "..." }
}
```

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
      "onHoldTotalCount": 0,
      "onHoldTotalQty": 0,
      "todayNewQty": 0,
      "todayReleaseQty": 0,
      "todayFutureHoldQty": 0,
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

## 4. Invalid Data Behavior

| condition | expected behavior | error code / UI state | test |
|---|---|---|---|
| missing required column | service raises ValueError → 500 INTERNAL_ERROR | INTERNAL_ERROR | `tests/test_field_contracts.py` |
| wrong type (e.g. string qty) | type coercion or 400 VALIDATION_ERROR | VALIDATION_ERROR | `tests/test_field_contracts.py` |
| empty dataset | returns empty list `[]`; UI shows EmptyState | — | `frontend/tests/playwright/data-boundary/empty-result.spec.js` |
| over max row limit | truncated; adds `_meta.truncated=true` to payload | — | `tests/test_interactive_memory_guard.py` |
| unexpected enum value | 400 VALIDATION_ERROR | VALIDATION_ERROR | `tests/routes/test_fuzz_routes.py` |
| malicious input (SQL/XSS/100k) | 400 VALIDATION_ERROR (never 500) | VALIDATION_ERROR | `tests/routes/test_fuzz_routes.py` |
| DB unavailable | 503 SERVICE_UNAVAILABLE | SERVICE_UNAVAILABLE | `tests/test_degraded_responses.py` |
| Spool expired | 410 CACHE_EXPIRED or dataset_expired | CACHE_EXPIRED | resilience tests |
| Date range > 730 days | 400 VALIDATION_ERROR | VALIDATION_ERROR | route tests |

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

## CHANGELOG

## [data 1.11.0]
- ai-pipeline-upgrade (2026-05-29): Added §2.9 (AI Session Store Shape including `chat_history` pairs, cap 8/16, TTL, pop-preservation semantics) and three new AI function param schemas (`production_history_query` raw_params dispatch, `resource_history_summary` kwargs, `qc_gate_status` no-params). Added `normalize_chart_data` output for `qc_gate_status` (→ stations list) and pass-through for `production_history_query`/`resource_history_summary`. Additive; no existing schemas changed.

## [data 1.10.0]
- add-package-detail-tables (2026-05-22): Added §3.11 documenting hold-history detail row schema with new `package: string | null` field. Updated §3.6 (query-tool lot-history / equipment-lots) with new `PRODUCTLINENAME: string | null` field, `_PARTIAL_NONKEY_COLS_LOT` extension note, and CSV export column order. Updated §3.9.2 (material-consumption detail spool) with new `PRODUCTLINENAME: VARCHAR | null` column (detail spool schema breaking-change surface — parquet cleanup required on deploy/rollback). §3.7 (equipment-rejects) already had PRODUCTLINENAME documented — no change. All additive; no existing columns removed or renamed.

## [data 1.9.0]
- resource-status-package-group (2026-05-21): Added §3.10 documenting the merged resource-status record shape (all 35+ fields). New field PACKAGEGROUPNAME (string | null) added to each record; NULL for ~91% of resources (PACKAGEGROUPID is null in DWH.DW_MES_RESOURCE). Lookup via 46-row in-process dict (DW_MES_RESOURCE_PACKAGEGROUP, 7-day TTL, independent of 24h resource_cache cycle). No existing fields removed or renamed.

## [data 1.8.0]
- material-part-consumption (2026-05-20): Added §3.9 with summary spool schema (8 columns: txn_date, material_part, pj_type, primary_category, total_consumed, total_required, lot_count, workorder_count) and detail spool schema (mirrors forward_by_lot.sql columns + pj_type). New spool namespaces only; no existing schemas changed.
