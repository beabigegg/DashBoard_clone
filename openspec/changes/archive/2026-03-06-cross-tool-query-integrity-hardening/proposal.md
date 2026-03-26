## Why

報廢歷史查詢已建立「部分失敗可見化 + 快取/分塊 + spool 回退」的完整性策略，但其他大量查詢工具仍存在不一致行為：同樣是保護 OOM 的截斷機制，部分路徑沒有將截斷與資料品質訊號穩定回傳，甚至在特定路徑把 metadata 混入資料集後造成下游處理風險。現在需要將完整性契約跨工具統一，避免「資料不完整但看起來像完整」與高量場景例外。

## What Changes

- 建立跨工具共用的「查詢結果完整性契約（Query Quality Meta）」：統一描述 `complete/partial/truncated`、原因、影響範圍與建議動作。
- 重構 EventFetcher 截斷訊號傳遞，移除把 `__meta__` 混入 CID->records map 的做法，改為顯式 metadata 回傳。
- 修正 trace staged API（同步 / async job / NDJSON）對資料品質訊號的端到端傳遞，前端可穩定顯示非完整結果警示。
- 修正 mid-section-defect 對 event payload 的正規化流程，確保 metadata 與資料列解耦，避免高量截斷場景的型別/迭代風險。
- 補齊 Query Tool 高量明細端點的 server-side pagination，降低單次 payload 與記憶體峰值。
- 將 Material Trace 匯出從全量 materialize 改為串流輸出，保留既有上限語意並回報完整性訊號。
- 將 reject-history 已驗證的 partial-failure 呈現與失敗區間語意，抽取為可跨工具重用的模式（含測試與文件）。
- **BREAKING**: EventFetcher 內部回傳契約由「可能混入 `__meta__`」調整為「資料與 metadata 分離」；直接依賴舊內部結構的呼叫端需同步調整。

## Capabilities

### New Capabilities
- `query-result-integrity-contract`: 定義跨工具共用的查詢完整性 metadata 契約與傳遞/顯示規範。

### Modified Capabilities
- `event-fetcher-unified`: 將截斷/部分結果訊號改為顯式 metadata，避免混入 records map。
- `trace-staged-api`: 同步、非同步與 NDJSON 路徑都必須傳遞並暴露 query quality metadata。
- `query-tool-lot-trace`: 高量明細端點改為 server-side pagination，並在回應中攜帶完整性狀態。
- `material-trace-api`: 匯出改為串流化，並標準化截斷/非完整結果回報。
- `msd-analysis-transparency`: MSD 聚合管線需明確處理 partial/truncated events，不得因 metadata 造成資料處理錯誤。

## Impact

- Affected backend services:
  - `src/mes_dashboard/services/event_fetcher.py`
  - `src/mes_dashboard/routes/trace_routes.py`
  - `src/mes_dashboard/services/trace_job_service.py`
  - `src/mes_dashboard/services/mid_section_defect_service.py`
  - `src/mes_dashboard/services/query_tool_service.py`
  - `src/mes_dashboard/routes/query_tool_routes.py`
  - `src/mes_dashboard/services/material_trace_service.py`
  - `src/mes_dashboard/routes/material_trace_routes.py`
- Affected frontend:
  - `frontend/src/shared-composables/useTraceProgress.js`
  - `frontend/src/query-tool/*`
  - `frontend/src/material-trace/*`
- Affected tests:
  - `tests/test_event_fetcher.py`
  - `tests/test_trace_routes.py`
  - `tests/test_trace_job_service.py`
  - `tests/test_mid_section_defect_service.py`
  - `tests/test_query_tool_*`
  - `tests/test_material_trace_*`
- Ops/config/docs:
  - `.env.example`（新增或補齊完整性相關參數）
  - `docs/oom_cache_cross_apply_analysis.md`（與新契約對齊）
