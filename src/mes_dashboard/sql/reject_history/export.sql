-- Reject History Export (Unpaginated)
-- Template slots:
--   BASE_QUERY (base reject-history daily dataset SQL)
--   WHERE_CLAUSE (QueryBuilder-generated WHERE clause against alias b)

{{ BASE_WITH_CTE }}
SELECT
    b.TXN_DAY,
    b.TXN_MONTH,
    b.WORKCENTER_GROUP,
    b.WORKCENTERNAME,
    b.SPECNAME,
    b.PRODUCTLINENAME,
    b.PJ_TYPE,
    b.LOSSREASONNAME,
    b.LOSSREASON_CODE,
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
    b.REJECT_SHARE_PCT,
    b.AFFECTED_LOT_COUNT,
    b.AFFECTED_WORKORDER_COUNT
FROM base b
{{ WHERE_CLAUSE }}
ORDER BY
    b.TXN_DAY DESC,
    b.WORKCENTERSEQUENCE_GROUP ASC,
    b.WORKCENTERNAME ASC,
    b.REJECT_TOTAL_QTY DESC
