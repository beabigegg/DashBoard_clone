# Design: hold-list-sorting

## Decision 1: 直接修改共用元件

在 `wip-shared/HoldLotTable.vue` 中整合 `useSortableTable`，不建立新元件。

理由：hold-overview 和 hold-detail 都用這個共用元件，一次修改兩處受益。

## Decision 2: 前端排序（當頁資料）

排序範圍為當前分頁的資料（前端排序），不修改後端 API。

理由：
- 與現有後端分頁機制相容，不需改 API
- `useSortableTable` 已經過驗證，直接復用
- 使用者主要需求是快速比較同頁資料

## Decision 3: 清理死碼

移除 `hold-overview/components/LotTable.vue` 和 `hold-detail/components/LotTable.vue`。

理由：這兩個元件從未被 App.vue import，是死碼。

## Architecture

```
HoldLotTable.vue
├── import { useSortableTable } from 'shared-composables'
├── <th @click="toggleSort('lotId')" :aria-sort="...">
│     LOTID <span class="sort-indicator">▲/▼/⇕</span>
│   </th>
├── <tr v-for="lot in sortedData" ...>
└── 排序狀態: sortKey, sortDirection (component-local)
```

## Column → sortKey Mapping

| Column | sortKey | Type |
|--------|---------|------|
| LOTID | lotId | string |
| WORKORDER | workorder | string |
| QTY | qty | number |
| Product | product | string |
| Package | package | string |
| Workcenter | workcenter | string |
| Hold Reason | holdReason | string |
| Spec | spec | string |
| Age | age | number |
| Hold By | holdBy | string |
| Dept | dept | string |
| Hold Comment | holdComment | string |
| Future Hold Comment | futureHoldComment | string |
