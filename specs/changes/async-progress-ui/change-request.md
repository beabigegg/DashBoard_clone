# Change Request

## Original Request

建立共用 AsyncQueryProgress.vue 元件並套用到 yield-alert 與 production-history：
(1) 新增 shared-ui/AsyncQueryProgress.vue（inline 進度條、百分比、取消按鈕）；
(2) 補齊 useAsyncJobPolling.ts JobStatusResponse 的 pct/stage 型別宣告；
(3) 在 yield-alert-center/App.vue 與 production-history/App.vue 加入進度 UI；
(4) 後端 yield_alert_job_service 與 production_history_job_service 補 pct milestone (0/30/100)

## Business / User Goal

使用者執行 yield-alert 或 production-history 慢查詢時，能看到進度條 + 百分比 + 已等待秒數，並可按取消按鈕中止輪詢，提升使用體驗。同時消除 useAsyncJobPolling.ts 的 unknown cast，讓 pct/stage 欄位型別安全。

## Non-goals

- 不實作 downtime / hold-history 的 RQ 遷移（屬階段三）
- 不新增 job registry（屬階段二）
- 不改動現有 reject-history 的進度 bar 實作

## Constraints

- 純前端元件（AsyncQueryProgress.vue）零後端依賴
- 後端只在現有 update_job_progress() 呼叫點補 pct，不改 Redis schema
- CSS 使用 .async-job-progress base class，不依賴 theme-* scope（避免 Teleport 問題）
- Node ≥ 22.6；vue-tsc --noEmit 必須通過；npm run css:check 必須通過

## Known Context

- 現有 AsyncJobPolling composable: frontend/src/shared-composables/useAsyncJobPolling.ts（3s 輪詢）
- 現有進度 bar 參考：reject-history/App.vue:1478-1486 .async-job-status-bar
- yield-alert-center/App.vue 已有 jobProgress state（lines 61-68）
- production-history/App.vue 透過 useProductionHistory.ts 收集 jobProgress
- 計畫來源：docs/dynamic-rq-migration-plan.md 階段一

## Open Questions

無。

## Requested Delivery Date / Priority

高優先（階段一，純前端，零後端風險）。
