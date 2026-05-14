# Change Request

## Original Request

在 reject-history 的 DetailTable.vue 與 material-trace 的 App.vue 中，Hold/Release 明細表和 Result 明細表（DataTable）被 `.card-body` 的 padding 視覺框住，造成「表中表」外觀。修正方式同 hold-history-detail-flat-table：對各自的 `.card-body` 加 override class 並設 padding:0，讓 DataTable 直接貼齊卡片邊緣，成為單一平面表格。成功標準：hold-history-detail-flat-table 已通過的 CSS governance + Vitest gates 繼續通過；reject-history 與 material-trace 明細表的 `.card-body` 不再有 padding 框住 DataTable。

## Business / User Goal

## Non-goals

## Constraints

## Known Context

## Open Questions

## Requested Delivery Date / Priority
