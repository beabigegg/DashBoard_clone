# Change Request

## Original Request

將 yield-alert-center 頁面的 main.js、utils.js、useYieldAlertDuckDB.js 重新命名為 .ts，並為 App.vue 與四個 chart SFC（YieldHeatmap.vue、YieldPackageChart.vue、YieldStationChart.vue、YieldTrendChart.vue）加上 lang="ts"，完成 Phase 3 TypeScript 遷移。

Affected surface: frontend/src/yield-alert-center/ (3 JS files + 5 Vue SFCs)
Desired behavior: rename .js → .ts, add lang="ts" to SFCs, update test file extension references
Success criterion: vue-tsc --noEmit passes, all existing Vitest and Python tests pass with updated references

## Business / User Goal

## Non-goals

## Constraints

## Known Context

## Open Questions

## Requested Delivery Date / Priority
