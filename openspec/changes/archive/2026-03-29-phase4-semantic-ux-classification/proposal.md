## Why

Phase 3 統一了所有歷史查詢域的 `apply_view()` 路徑（DuckDB 唯一引擎，spool miss → 410），但沒有正式定義各域的對外 UX 語意契約。resource / hold / yield-alert 的 410 應觸發前端同步重查；reject / material-trace / MSD 的 410 應觸發前端非同步 202 輪詢——這兩種行為模式目前存在於實作中，但缺乏明確的 spec 定義。本 Phase 正式化這項分類，建立可治理的雙語意查詢契約。

## What Changes

- **新增 `query-response-semantic-contract` spec**：正式定義 Type A（sync re-query）與 Type B（async 202 polling）兩種查詢語意，列出各域歸屬
- **`reject-history-api` spec 更新**：明確記錄 view miss → 410 → 前端應發起 async job（POST /query → 202）→ polling 的完整契約；`apply_view()` 本身不自動 dispatch（保持職責分離）
- **Type A 域 spec 更新**（resource-dataset-cache、hold-dataset-cache、yield-alert-spool-query）：明確記錄 view miss → 410 → 前端應觸發同步主查詢的契約
- **`async-query-job-service` spec 更新**：說明此服務為 Type B 域的 miss re-dispatch 入口，補充 job dispatch 的 query-id 重建語意
- **不含代碼變更**：routes 行為已符合設計目標（410 路徑正確），Phase 4 為純 spec / contract governance

## Capabilities

### New Capabilities
- `query-response-semantic-contract`: 定義雙語意查詢契約——Type A（sync re-query on 410）與 Type B（async 202 polling on 410）；列出各域分類與 client 端應對行為規範

### Modified Capabilities
- `reject-history-api`: 補充 view miss → 410 → async re-dispatch → polling 的完整端到端契約（含 query-id 重建、job status polling 路徑）
- `resource-dataset-cache`: 正式化 Type A 語意——view miss → 410 → 前端同步重查契約
- `hold-dataset-cache`: 正式化 Type A 語意——view miss → 410 → 前端同步重查契約
- `yield-alert-spool-query`: 正式化 Type A 語意——view miss → 410 → 前端同步重查契約
- `async-query-job-service`: 補充作為 Type B miss re-dispatch 入口的角色定義

## Impact

- 影響：`openspec/specs/` 內 5 個現有 spec 更新 + 1 個新 spec
- 無後端代碼變更（routes 行為已正確）
- 前端行為已正確實作；本 Phase 為 contract 的補充文件化，不含前端 breaking change
- 受影響的 routes（記錄用）：
  - `reject_history_routes.py` — Type B（apply_view miss → 410 → 前端 async dispatch）
  - `resource_history_routes.py`, `hold_history_routes.py`, `yield_alert_routes.py` — Type A（apply_view miss → 410 → 前端 sync re-query）
