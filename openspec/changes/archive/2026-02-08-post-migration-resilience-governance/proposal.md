## Why

Vite migration已完成主要功能遷移，但目前仍有兩個可見風險：一是運維端缺少「可操作」的韌性判斷（僅有狀態，缺少建議動作與重啟 churn 訊號）；二是前端主要報表頁仍存在可抽離的重複互動邏輯，會增加後續維護成本。現在補齊這兩塊，可在不改變既有使用流程下提高穩定性與可演進性。

## What Changes

- 擴充 runtime resilience 診斷契約：在 health/admin payload 提供門檻設定、重啟 churn 與可行動建議。
- 強化 watchdog state：保留最近重啟歷史，支持 churn 計算與觀測。
- 將 WIP overview/detail 重複的 autocomplete/filter 查詢邏輯抽成共用 Vite core 模組。
- 增加前端核心模組與韌性診斷的測試覆蓋。
- 更新專案說明文件（README）反映最新架構、治理策略與操作準則。

## Capabilities

### New Capabilities
- None.

### Modified Capabilities
- `runtime-resilience-recovery`: 新增重啟 churn 與復原建議契約，讓降級狀態具備可操作的 runbook 訊號。
- `full-vite-page-modularization`: 新增 WIP 報表共用 autocomplete/filter building blocks 要求，降低頁面重複實作。
- `migration-gates-and-rollout`: 新增文件與前端治理 gate，確保架構說明與實際部署契約一致。

## Impact

- Affected code:
  - `src/mes_dashboard/routes/health_routes.py`
  - `src/mes_dashboard/routes/admin_routes.py`
  - `scripts/worker_watchdog.py`
  - `frontend/src/core/`
  - `frontend/src/wip-overview/main.js`
  - `frontend/src/wip-detail/main.js`
  - `tests/`
  - `README.md`（以及使用者要求的 README.mdj）
- APIs:
  - `/health`
  - `/health/deep`
  - `/admin/api/system-status`
  - `/admin/api/worker/status`
- Operational behavior:
  - 保持單一 port 與既有手動重啟流程；新增觀測與建議，不預設啟用自動重啟風暴風險。
