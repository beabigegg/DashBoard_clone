## 1. Critical：離頁 abort 修復

- [x] 1.1 `yield-alert-center/App.vue`：在 `onUnmounted`（L658）第一行加入 `_jobAbortController?.abort();`
- [x] 1.2 `reject-history/App.vue`：在 `onUnmounted`（L1305）第一行加入 `_jobAbortController?.abort();`

## 2. production-history 查詢防護

- [x] 2.1 讀取 `frontend/src/production-history/App.vue` 的 `handleQuery()` 實作（L75 附近）
- [x] 2.2 在 `handleQuery()` 開頭加入 `if (loading.value) return;`
- [x] 2.3 引入 `useRequestGuard`（`import { useRequestGuard } from '../shared-composables/useRequestGuard.js'`）
- [x] 2.4 在 `handleQuery()` 進入時呼叫 `const requestId = nextRequestId();`，並在每個非同步回應前加 `if (isStaleRequest(requestId)) return;`

## 3. query-tool 多 composable cleanup

- [x] 3.1 讀取 `frontend/src/query-tool/App.vue` 所有引入的 composable 清單
- [x] 3.2 讀取各 composable（`useLotResolve`、`useLotDetail`、`useReverseLineage`、`useLotEquipmentQuery` 等）確認是否暴露 abort/cancel/cleanup 介面
- [x] 3.3 在 `onBeforeUnmount`（L444）中依實際介面加入 cleanup 呼叫；若無介面，呼叫 `nextRequestId()` 使進行中回應失效

## 4. E2E 測試

- [x] 4.1 建立 `tests/e2e/test_query_race_condition_e2e.py`
- [x] 4.2 撰寫測試 A：`yield-alert-center` 離頁後輪詢停止（`page.on('request')` 計數 `/api/yield-alert/job/*`，navigate away 後 3 秒內無新請求）
- [x] 4.3 撰寫測試 B：`reject-history` 離頁後輪詢停止（同上，監聽 `/api/reject-history/job/*`）
- [x] 4.4 撰寫測試 C：`production-history` 快速連點查詢保護（5 次連點，同時 in-flight 請求 ≤ 1）

## 5. 驗證

- [x] 5.1 啟動本地服務：`./scripts/start_server.sh start`
- [x] 5.2 執行既有 e2e 迴歸確認無退化：`conda run -n mes-dashboard pytest tests/e2e/test_yield_alert_e2e.py tests/e2e/test_reject_history_e2e.py tests/e2e/test_production_history_e2e.py -v -s --timeout=120`
- [x] 5.3 執行新 e2e 測試：`conda run -n mes-dashboard pytest tests/e2e/test_query_race_condition_e2e.py -v -s --timeout=180`
- [x] 5.4 確認所有測試通過
