# Change Request

## Original Request

WIP-Overview 的 Workcenter × Package Matrix (QTY) 目前僅支援 workcenter drill down 到 wip-detail；希望可以像 hold-overview 一樣藉由點選 CELL 去 DRILL DOWN（WORKCENTER + PACKAGE）到 WIP-DETAIL 頁面。

WIP-DETAIL 頁面後，目前的 Lot Details 僅有 LOT ID / STATUS / EQUIPMENT / SPECs 等資訊，需要在 LOT ID 旁邊新增 Type（來自 PJ_Type）。

WIP-OVERVIEW 與 WIP-DETAIL 上方的 filters 區域新增 WORKFLOW（來自 WORKFLOWNAME）與 BOP（來自 BOP）、FUNCTION（來自 PJ_FUNCTION）這三個篩選。FILTER 須同步更新至 HOLD-OVERVIEW 頁面（共用 UI component，各頁獨立 state）。

FILTERS 的排序依照：
WORKORDER / LOT ID / PACKAGE
WORKFLOW / BOP / TYPE
FUNCTION / WAFER LOT / WAFER TYPE
這樣去做 3×3 的排序，同樣保留 CROSS-FILTER。

## Business / User Goal

## Non-goals

## Constraints

## Known Context

## Open Questions

## Requested Delivery Date / Priority
