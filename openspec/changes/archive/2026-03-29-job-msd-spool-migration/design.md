## Context

Phase 5 已將 production-history、hold、resource、reject 四個 dataset cache 遷移至 `merge_chunks_to_spool()` → `register_spool_file()` → DuckDB page/export 模式。但 `job_query_service` 和 `mid_section_defect_service` 的長日期範圍 engine path 仍使用舊的 `merge_chunks()` → 完整 DataFrame → `redis_store_df()` 回存模式，造成不必要的 RAM 尖峰。

**現行流程（兩個 domain 相同）：**
```
execute_plan(chunks)
    │
    ▼
merge_chunks() ← 所有 chunk 從 Redis 載入，concat 成完整 DF（RAM 峰值 = 結果集大小）
    │
    ▼
redis_store_df() ← pickle 序列化整張 DF 回 Redis（RAM 再加一倍）
    │
    ▼
df.iterrows() → JSON response
```

**目標流程：**
```
execute_plan(chunks)
    │
    ▼
merge_chunks_to_spool() ← 逐 chunk 寫 parquet（RAM = 單一 chunk 大小）
    │
    ▼
register_spool_file() ← 只存 metadata 到 Redis
    │
    ▼
DuckDB read_parquet → JSON response
```

## Goals / Non-Goals

**Goals:**
- 將 job_query 和 msd_detect 的 engine path 從 `merge_chunks()` 遷移到 `merge_chunks_to_spool()`
- 消除長日期範圍查詢時的完整 DataFrame RAM 尖峰
- 維持 API 回傳格式完全不變（前端零修改）
- 遵循 production_history_service 已建立的 spool 模式

**Non-Goals:**
- 不修改 short query（direct path）的邏輯——短查詢仍走現有路徑
- 不為 job_query / msd_detect 加入 async job + polling 模式——維持同步回傳
- 不重構 batch_query_engine 本身
- 不處理 material_trace、query_tool、lineage 等其他 domain 的 spool 遷移

## Decisions

### Decision 1: 同步 spool 模式（非 async job）

job_query 和 msd_detect 目前都是同步 API（使用者按查詢後等結果）。遷移只改內部 merge 路徑，不引入 async job + polling。

**理由：** 前端目前沒有 polling 機制，引入 async 會是 breaking change。目標是純粹降 RAM，不改 API 行為。

### Decision 2: DuckDB 讀 parquet 取代 df.iterrows() 轉 JSON

spool 寫入後，用 DuckDB `read_parquet()` → `fetchall()` 取得 records，取代 pandas `iterrows()`。

**理由：** DuckDB 讀 parquet 的記憶體效率遠高於 pandas，且已在 production_history 驗證過此模式。

### Decision 3: Spool namespace 命名

- job_query: namespace = `"job_query"`
- msd_detect: namespace = `"msd_detect"`

與 cache_prefix 對齊但獨立於 Redis chunk namespace，避免名稱碰撞。

### Decision 4: Spool TTL 與 Redis cache TTL 對齊

- job_query: 使用現有 `_JOB_CACHE_TTL`
- msd_detect: 使用現有 `CACHE_TTL_DETECTION`

spool 過期後 DuckDB 讀取會 miss，觸發重新查詢，行為與現有 Redis cache miss 一致。

### Decision 5: msd_detect 結果轉換位置

`_fetch_station_detection()` 目前回傳 DataFrame 給呼叫方，呼叫方再做後續處理（`cache_set(cache_key, df.to_dict('records'))`）。遷移後：
- engine path 改為寫 spool 後用 DuckDB 讀出 records
- direct path 不變（短查詢量小，維持原流程）
- 呼叫方拿到的仍是相同格式的 records/DataFrame

## Risks / Trade-offs

**[Risk] Spool 磁碟空間增長** → 已有 spool TTL 自動清理機制（`QUERY_SPOOL_TTL_SECONDS`），與其他 domain 共用同一套清理邏輯。

**[Risk] DuckDB read_parquet 回傳欄位型別可能與 pandas iterrows 不同** → 在轉換層統一處理 datetime 格式化和 None 值，與 job_query 現有的 iterrows 邏輯等價。

**[Risk] msd_detect 的呼叫鏈較複雜（多個函式消費 detection DataFrame）** → 只改 `_fetch_station_detection` 內部的 engine path merge 方式，回傳介面不變。
