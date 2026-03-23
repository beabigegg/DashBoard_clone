## Phase 1: 整合排序功能

- [x] 1.1 在 `wip-shared/HoldLotTable.vue` 中 import `useSortableTable`
  - `import { useSortableTable } from '../../shared-composables/useSortableTable.js'`
  - 以 `props.lots` 建立 computed ref 傳入 `useSortableTable`
- [x] 1.2 將 13 個 `<th>` 加上 `@click="toggleSort('key')"` 和 `:aria-sort` 屬性
  - 加入排序指示器 `▲`/`▼`/`⇕`
  - 加上 `cursor: pointer` 樣式
- [x] 1.3 將 `<tr v-for="lot in lots">` 改為 `<tr v-for="lot in sortedData">`
- [x] 1.4 驗證 hold-overview 頁面排序功能正常
- [x] 1.5 驗證 hold-detail 頁面排序功能正常

## Phase 2: 死碼清理

- [x] 2.1 刪除 `frontend/src/hold-overview/components/LotTable.vue`
- [x] 2.2 刪除 `frontend/src/hold-detail/components/LotTable.vue`
- [x] 2.3 確認 build 成功（無 broken import）
