# Proposal: hold-list-sorting

## Problem

hold-overview 和 hold-detail 頁面的明細清單（`HoldLotTable.vue`）沒有排序功能。
表頭是純文字，點擊無反應。

專案中已有 `useSortableTable` composable 和獨立的 `LotTable.vue`（含排序），
但實際渲染使用的是 `wip-shared/HoldLotTable.vue`（無排序）。

## Appetite

Small — 將現有 `useSortableTable` 整合進 `HoldLotTable.vue`，純前端排序（當前頁）。

## Solution

在 `wip-shared/HoldLotTable.vue` 中整合 `useSortableTable` composable：
- 表頭加上 `@click` + 排序指示器（▲▼⇕）
- 所有 13 欄位皆可排序
- 排序為前端排序（排序當頁資料），與現有後端分頁相容
- 完成後移除未使用的 `hold-overview/components/LotTable.vue` 和 `hold-detail/components/LotTable.vue`（死碼清理）
