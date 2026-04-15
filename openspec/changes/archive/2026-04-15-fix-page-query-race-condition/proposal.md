## Why

在反覆輸入→查詢、或頁面切換的情況下，部分頁面缺乏請求生命週期防護：`yield-alert-center` 和 `reject-history` 的 RQ Job 輪詢在元件卸載後不會自動中止；`production-history` 的查詢按鈕缺少 loading guard，允許重複觸發；`query-tool` 多標籤切換時各 composable 的 pending 請求未被清理。這些問題導致頁面離開後仍有背景網路請求、以及潛在的 race condition。

## What Changes

- `yield-alert-center/App.vue`：`onUnmounted` 加入 `_jobAbortController?.abort()` — 離頁時中止 RQ Job 輪詢
- `reject-history/App.vue`：同上
- `production-history/App.vue`：`handleQuery()` 加入 loading guard（`if (loading.value) return`）及 `useRequestGuard` stale check，防止重複查詢與回應亂序
- `query-tool/App.vue`：`onBeforeUnmount` 加入各子 composable 的 abort/cleanup 呼叫
- 新增 e2e 測試檔 `tests/e2e/test_query_race_condition_e2e.py`：Playwright 驗證上述場景

## Capabilities

### New Capabilities

- `page-request-lifecycle`: 定義各頁面查詢請求的生命週期契約 — 元件卸載時必須中止所有進行中的非同步操作（Job 輪詢、fetch），以及防止重複觸發查詢的 loading guard 規範

### Modified Capabilities

- `yield-alert-center-page`: 新增「元件卸載時中止 Job 輪詢」的行為要求
- `reject-history-page`: 同上

## Impact

- **受影響前端檔案**：`yield-alert-center/App.vue`、`reject-history/App.vue`、`production-history/App.vue`、`query-tool/App.vue`
- **受影響測試**：新增 `tests/e2e/test_query_race_condition_e2e.py`
- **無 API 變更**，無 breaking change
- **依賴**：使用現有 `shared-composables/useRequestGuard.js`，無新增 dependency
