## Context

目前重查詢模組的記憶體保護策略不一致：

- Query Tool：在 service 前段即 RSS reject，命中後直接 `MemoryError`
- Trace：sync 路徑在 events 與 aggregation 前做 RSS reject
- Reject History：primary query 前段有 RSS front-door reject
- Material Trace：使用 shared memory guard，但 route 目前把 `MemoryError` 當 validation 錯誤（400）
- Yield Alert：已有 DuckDB/spool + guard，但與其他頁面的 overload 回應格式未完全對齊

本次事故顯示 Query Tool 在高壓下直接失敗，而相同風險在其他重查詢頁面也存在。

## Goals / Non-Goals

**Goals**
- 統一重查詢頁面的 overload 契約（503 + Retry-After + 統一 code/meta）
- Query Tool 導入 DuckDB/spool 降級路徑，降低 RSS guard 直接失敗率
- 對齊低良率查詢業務規則：`WORKCENTER_GROUP` 彙整 + reject 過濾一致
- 建立可觀測的 guard/fallback 指標

**Non-Goals**
- 不改變既有 API URL 與主要 payload 結構
- 不全面替換 pandas 路徑；保留 fallback
- 不進行跨模組大規模 SQL 重寫

## Decisions

### D1. 「先可用結果、後拒絕」順序

- **Decision**: 對可由 cache/spool 回應的路徑，先嘗試回可用資料，再進入 reject。
- **Rationale**: 避免高壓時所有請求都直接失敗；優先保服務可用性。

### D2. Query Tool 採 DuckDB-first（高量路徑）

- **Decision**: 為 Query Tool 批次 history/associations 增加 `query_tool_sql_runtime.py`，讀 parquet spool 做分頁與聚合。
- **Rationale**: 專案已有 reject/hold/resource/yield 的成功模式，可複用。
- **Fallback**: DuckDB 不可用或 spool miss 時回到既有 pandas/EventFetcher 路徑。

### D3. Overload 回應契約統一

- **Decision**: 重查詢 `MemoryError` 或 RSS reject 一律回 503（`SERVICE_UNAVAILABLE`），附 `Retry-After` 與一致 meta/code。
- **Rationale**: 400 代表參數錯誤，與過載語意不符；會誤導前端與 AI 重試策略。

### D4. Trace guard 命中優先 async

- **Decision**: `trace/events` sync 路徑 guard 命中時，若 async worker 可用且請求符合條件，直接轉 202 job 模式。
- **Rationale**: Trace 已有 async 基礎設施，可避免大量 503。

### D5. 業務規則一致化（低良率）

- **Decision**: Query Tool 低良率相關輸出強制經過 `WORKCENTER_GROUP` 對齊與 reject policy filter（material scrap / excluded reasons / PB diode 等）。
- **Rationale**: 修正 AI 問答場景「查得到但邏輯不一致」。

### D6. 配置顯式化

- **Decision**: 補齊並治理 `.env.example` 的 heavy-query guard 參數，包含 `QUERY_TOOL_RSS_REJECT_MB`。
- **Rationale**: 目前 Query Tool 依賴程式內預設值，不利於環境治理與故障排查。

## Risks / Trade-offs

- **[Risk]** DuckDB/pandas 雙路徑結果不一致  
  **Mitigation**: 建立 parity 測試，關鍵欄位與總量比對。

- **[Risk]** 降級路徑增加程式複雜度  
  **Mitigation**: 抽出共用 overload/fallback helper，避免各路由重複實作。

- **[Risk]** spool 檔案容量膨脹  
  **Mitigation**: 延續 `query_spool_store` 既有容量/TTL/cleanup 機制與告警。

- **[Risk]** 轉為 503 影響前端舊行為  
  **Mitigation**: 保持錯誤訊息相容，僅修正 status code 與 retry meta。
