-- Reject History Paged List (ROW_NUMBER() row-count chunking)
-- Used when USE_ROW_COUNT_CHUNKING=true.
-- Template slots:
--   BASE_WITH_CTE (lot-level base SQL via performance_daily_lot)
--   WHERE_CLAUSE (QueryBuilder-generated WHERE clause against alias b)
-- Parameters:
--   :start_row - 1-based inclusive start (from decompose_by_row_count)
--   :end_row   - 1-based inclusive end
--
-- ORDER BY key (BQE-03): TXN_DAY DESC, CONTAINERNAME ASC

{{ BASE_WITH_CTE }},
ranked AS (
    SELECT
        b.TXN_TIME,
        b.TXN_DAY,
        b.TXN_MONTH,
        b.WORKCENTER_GROUP,
        b.WORKCENTERSEQUENCE_GROUP,
        b.WORKCENTERNAME,
        b.SPECNAME,
        b.EQUIPMENTNAME,
        b.PRODUCTLINENAME,
        b.SCRAP_OBJECTTYPE,
        b.PJ_TYPE,
        b.CONTAINERNAME,
        b.PJ_WORKORDER,
        b.PJ_FUNCTION,
        b.PRODUCTNAME,
        b.LOSSREASONNAME,
        b.LOSSREASON_CODE,
        b.REJECTCOMMENT,
        b.AFFECTED_WORKORDER_COUNT,
        b.MOVEIN_QTY,
        b.REJECT_QTY,
        b.REJECT_TOTAL_QTY,
        b.DEFECT_QTY,
        b.STANDBY_QTY,
        b.QTYTOPROCESS_QTY,
        b.INPROCESS_QTY,
        b.PROCESSED_QTY,
        b.REJECT_RATE_PCT,
        b.DEFECT_RATE_PCT,
        b.REJECT_SHARE_PCT,
        ROW_NUMBER() OVER (
            ORDER BY b.TXN_DAY DESC, b.CONTAINERNAME ASC
        ) AS _rn
    FROM base b
    {{ WHERE_CLAUSE }}
)
SELECT
    TXN_TIME,
    TXN_DAY,
    TXN_MONTH,
    WORKCENTER_GROUP,
    WORKCENTERSEQUENCE_GROUP,
    WORKCENTERNAME,
    SPECNAME,
    EQUIPMENTNAME,
    PRODUCTLINENAME,
    SCRAP_OBJECTTYPE,
    PJ_TYPE,
    CONTAINERNAME,
    PJ_WORKORDER,
    PJ_FUNCTION,
    PRODUCTNAME,
    LOSSREASONNAME,
    LOSSREASON_CODE,
    REJECTCOMMENT,
    AFFECTED_WORKORDER_COUNT,
    MOVEIN_QTY,
    REJECT_QTY,
    REJECT_TOTAL_QTY,
    DEFECT_QTY,
    STANDBY_QTY,
    QTYTOPROCESS_QTY,
    INPROCESS_QTY,
    PROCESSED_QTY,
    REJECT_RATE_PCT,
    DEFECT_RATE_PCT,
    REJECT_SHARE_PCT
FROM ranked
WHERE _rn BETWEEN :start_row AND :end_row
