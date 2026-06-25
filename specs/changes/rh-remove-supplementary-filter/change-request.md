# Change Request

## Original Request

reject-history 移除二階補充篩選：將報廢原因加入第一層 Oracle BASE_WHERE 預篩選，捨棄 WORKCENTER GROUP 篩選，完整移除補充篩選 UI 區塊。Package 與 TYPE（PJ_TYPE）已在第一層，故補充篩選的四個欄位全數整合完畢。DuckDB spool 仍保留供 Pareto 計算、明細分頁與 CSV 匯出使用；移除的僅是補充篩選的 WHERE 條件層與前端 UI。

Context confirmed in prior conversation:
- WORKCENTER GROUP is NOT a Pareto analysis dimension (DIM_TO_COLUMN: reason/LOSSREASONNAME, package/PRODUCTLINENAME, type/PJ_TYPE only)
- Supplementary "TYPE" = b.PJ_TYPE (same as primary "PJ Type" — already in BASE_WHERE)
- Supplementary "Package" = b.PRODUCTLINENAME (same as primary "Package" — already in BASE_WHERE)
- LOSSREASONNAME from r.LOSSREASONNAME (main table, not LEFT JOIN) — can go to BASE_WHERE
- reason_filter_cache.get_reject_reasons() is the ready option source (L1+L2 Redis, 24h TTL)
- DuckDB spool kept for Pareto cross-filter, pagination, CSV export

## Business / User Goal

## Non-goals

## Constraints

## Known Context

## Open Questions

## Requested Delivery Date / Priority
