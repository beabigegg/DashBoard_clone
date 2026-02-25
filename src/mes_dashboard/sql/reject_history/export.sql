-- Reject History Export (Unpaginated, Per-LOT)
-- Template slots:
--   BASE_WITH_CTE (lot-level base SQL via performance_daily_lot)
--   WHERE_CLAUSE (QueryBuilder-generated WHERE clause against alias b)

{{ BASE_WITH_CTE }}
SELECT
    b.TXN_TIME,
    b.TXN_DAY,
    b.CONTAINERNAME,
    b.WORKCENTER_GROUP,
    b.WORKCENTERNAME,
    b.SPECNAME,
    b.WORKFLOWNAME,
    b.EQUIPMENTNAME,
    b.PRODUCTLINENAME,
    b.PJ_FUNCTION,
    b.PJ_TYPE,
    b.PRODUCTNAME,
    b.LOSSREASONNAME,
    b.LOSSREASON_CODE,
    b.REJECTCOMMENT,
    b.MOVEIN_QTY,
    b.REJECT_QTY,
    b.STANDBY_QTY,
    b.QTYTOPROCESS_QTY,
    b.INPROCESS_QTY,
    b.PROCESSED_QTY,
    b.REJECT_TOTAL_QTY,
    b.DEFECT_QTY,
    b.REJECT_RATE_PCT,
    b.DEFECT_RATE_PCT,
    b.REJECT_SHARE_PCT
FROM base b
{{ WHERE_CLAUSE }}
ORDER BY
    b.TXN_DAY DESC,
    b.WORKCENTERSEQUENCE_GROUP ASC,
    b.WORKCENTERNAME ASC,
    b.REJECT_TOTAL_QTY DESC,
    b.CONTAINERNAME ASC
