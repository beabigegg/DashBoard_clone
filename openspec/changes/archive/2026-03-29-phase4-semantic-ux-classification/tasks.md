## 0. 前置確認：現有行為 audit

- [x] 0.1 確認 `resource_history_routes.py`：view miss → `cache_expired_error()` (410)，無自動 dispatch
- [x] 0.2 確認 `hold_history_routes.py`：view miss → `cache_expired_error()` (410)，無自動 dispatch
- [x] 0.3 確認 `yield_alert_routes.py`：view miss → `cache_expired_error()` (410)，無自動 dispatch
- [x] 0.4 確認 `reject_history_routes.py`：view miss → `cache_expired_error()` (410)，POST /query → 202 路徑已正確分離
- [x] 0.5 確認前端 410 處理：resource / hold / yield-alert 頁面在 410 後是否觸發 sync re-query（非 polling）
- [x] 0.6 確認前端 410 處理：reject 頁面在 410 後是否觸發 async job dispatch → polling

## 1. 新增 governed spec：query-response-semantic-contract

- [x] 1.1 確認 `openspec/specs/query-response-semantic-contract/` 目錄尚未存在
- [x] 1.2 從此 change 的 delta spec 套用至 `openspec/specs/query-response-semantic-contract/spec.md`
- [x] 1.3 驗證 spec 內容：Type A / Type B 分類清單、view endpoint 不 dispatch 的明確要求

## 2. 更新 governed spec：reject-history-api

- [x] 2.1 將 `specs/reject-history-api/spec.md` delta 套用至 `openspec/specs/reject-history-api/spec.md`
- [x] 2.2 驗證：加入 Type B 端到端契約（view miss → 410 → client dispatch → 202 → polling → view）
- [x] 2.3 驗證：明確記錄 apply_view 不自動 dispatch（職責分離）

## 3. 更新 governed spec：Type A 域

- [x] 3.1 將 `specs/resource-dataset-cache/spec.md` delta 套用至 `openspec/specs/resource-dataset-cache/spec.md`
- [x] 3.2 將 `specs/hold-dataset-cache/spec.md` delta 套用至 `openspec/specs/hold-dataset-cache/spec.md`
- [x] 3.3 將 `specs/yield-alert-spool-query/spec.md` delta 套用至 `openspec/specs/yield-alert-spool-query/spec.md`
- [x] 3.4 驗證三個 spec 均加入 Type A 標籤 + "client re-triggers sync query on 410" scenario

## 4. 更新 governed spec：async-query-job-service

- [x] 4.1 將 `specs/async-query-job-service/spec.md` delta 套用至 `openspec/specs/async-query-job-service/spec.md`
- [x] 4.2 驗證：加入「作為 Type B miss re-dispatch 入口」的 ADDED requirement

## 5. 驗證與收尾

- [x] 5.1 執行 `pytest tests/ -v` 確認無回歸（本 Phase 無代碼變更，測試應全部通過）
- [x] 5.2 確認 `openspec/specs/query-response-semantic-contract/spec.md` 存在且可被 openspec 讀取
- [x] 5.3 確認 `contract/api_inventory.md` 中 reject / resource / hold / yield-alert 的語意分類有無需要更新（若有，補充 Type A/B 標記）
- [x] 5.4 更新 `docs/page_query_architecture_audit_and_ram_phase_plan.md` Phase 4 section：加入實作結果摘要
