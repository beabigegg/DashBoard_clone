## Why

目前根目錄遷移與 Vite 架構已完成可用性與功能對齊，但「穩定性、退避、自癒、查詢效率」仍未被完整定義為可驗收的規格。現在需要在不改變既有業務邏輯的前提下，將運行韌性與前端運算前移策略正式化，避免 cutover 後在高負載或故障情境下出現不一致行為。

## What Changes

- 以三階段推進非破壞式優化：
- P0（先救穩定）：讓 DB pool 參數真正生效、在生產基線啟用 circuit breaker、補齊 pool exhausted 的專用錯誤語意與前後端退避行為。
- P1（再拚效率）：重整快取資料結構與查詢路徑（索引化/增量化），降低每次請求的全量 merge 成本。
- P2（運維收斂）：統一 conda + systemd 執行模型，補齊 worker 自癒與告警門檻，讓 watchdog/restart 流程可操作且可觀測。
- 明確保留既有架構原則：
- `resource`（設備基礎資料）與 `wip`（線上即時狀況）維持全表快取策略，不改成分片或拆表快取。
- Vite 架構持續以「元件複用（圖表/查詢/抽屜）」與「運算前移至瀏覽器」為主軸，前端承接可前移的聚合與呈現計算。

## Capabilities

### New Capabilities
- `runtime-resilience-recovery`: 定義 DB pool 耗盡、worker 異常、服務降級時的標準退避、恢復與熱重啟流程。
- `conda-systemd-runtime-alignment`: 定義 conda 環境、systemd 服務、watchdog 與啟停腳本的一致部署契約與驗收門檻。

### Modified Capabilities
- `frontend-compute-shift`: 擴充前端運算前移邊界與 parity 驗證，確保前端計算結果與後端契約一致。
- `full-vite-page-modularization`: 強化跨頁可複用元件與共用核心模組（圖表、查詢、抽屜、欄位契約）的要求。
- `layered-route-cache`: 明確要求保留 `resource/wip` 全表快取，並在此基礎上優化索引與資料形狀。
- `cache-observability-hardening`: 擴充快取/連線池/熔斷器的可觀測欄位、降級訊號與告警閾值。
- `migration-gates-and-rollout`: 新增穩定性壓測、pool 壓力、worker 重啟演練等遷移門檻。

## Impact

- Affected code:
- Backend: `src/mes_dashboard/core/database.py`, `src/mes_dashboard/core/circuit_breaker.py`, `src/mes_dashboard/core/cache.py`, `src/mes_dashboard/routes/*.py`, `src/mes_dashboard/services/resource_cache.py`, `src/mes_dashboard/services/realtime_equipment_cache.py`。
- Frontend: `frontend/src/core/*` 與各頁 entry 模組，持續抽取可複用圖表/查詢邏輯。
- Ops: `scripts/start_server.sh`, `scripts/worker_watchdog.py`, `deploy/mes-dashboard-watchdog.service`, `.env.example`, `README.md`。
- API/behavior:
- 新增或標準化故障語意（含 pool exhausted / circuit open / degraded）與對應退避策略。
- Dependencies/systems:
- 維持單一埠服務模型；持續使用 conda + gunicorn + redis + systemd/watchdog。
- Validation:
- 增加 resilience/performance 測試與 rollout gate，驗證降級、恢復、快取一致性與前後端計算一致性。
