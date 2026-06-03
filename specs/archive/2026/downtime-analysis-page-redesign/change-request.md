# Change Request

## Original Request

downtime-analysis頁面需要重新設計：
1. 圖表部分的交互不夠，沒有互動式的點選CROSS-FILTER功能
2. 兩個明細表是額外獨立頁面，沒有與圖表頁聯動。我的想法是，這一樣的出發點是狀態的圖表→將明細表做成雙層，放在圖表之下。所謂的雙層是狀態→機台→JOB，並且需要包含目前明細表中的資訊。

Redesign downtime-analysis page: add chart cross-filter (BigCategoryChart click → category filter, DailyTrendChart legend click → status filter), replace three-tab layout with single-page layout where charts are above and a three-tier expandable table (Status group → Machine → Event/JOB) is below. Backend needs new filter params (big_category, status_types, resource_id) on equipment-detail and event-detail endpoints. Two new frontend components: StatusMachineJobTable and MachineEventRows.

User clarification: The first expansion tier is **Status/Category (UDT/SDT/EGT)**, then Machine within that status, then Events/JOB per machine.

## Business / User Goal

工廠工程師能在同一個頁面上：
- 點擊 BigCategoryChart 扇形 → 自動篩選下方明細表只顯示該類別
- 點擊 DailyTrendChart 圖例 → 篩選特定狀態（UDT/SDT/EGT）
- 直接在圖表下方展開三層表格（狀態分組 → 機台 → 個別事件/JOB），不需要切換 tab

## Non-goals

- 不更改現有 API 的回應結構（只增加 optional query params）
- 不重寫圖表的核心邏輯，只加入 click event handlers
- 不新增任何新的 Oracle 查詢（所有過濾均在 spool in-memory 完成）

## Constraints

- 所有 CSS 必須 scoped under `.theme-downtime-analysis`（`npm run css:check` 會強制執行）
- 修改任何 `style.css` 後必須 `npm run build`
- DataTable 在 shared-ui 是共用元件，不能破壞其他頁面

## Known Context

- 現有頁面是三 tab 結構（Charts / Equipment / Events），均已有完整功能
- 後端使用 parquet spool，`apply_view()` 函式在 in-memory 做聚合
- 前端使用 ECharts（vue-echarts），follow HoldTreeMap 的 click emit 模式
- 詳見 plan: /home/egg/.claude/plans/spicy-hopping-taco.md

## Open Questions

（無）

## Requested Delivery Date / Priority

High priority.
