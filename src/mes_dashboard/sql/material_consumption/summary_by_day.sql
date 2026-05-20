-- Material Consumption Summary — day-level aggregate (MC-01)
-- Joins DWH.DW_MES_LOTMATERIALSHISTORY with DWH.DW_MES_CONTAINER for PJ_TYPE.
-- {{ WHERE_CLAUSE }} is replaced by QueryBuilder.build() with parameterized conditions.
-- primary_category is intentionally excluded from the summary spool;
-- it is retained in detail_rows.sql for CSV export only.

SELECT
    TRUNC(m.TXNDATE)       AS txn_date,
    m.MATERIALPARTNAME     AS material_part,
    c.PJ_TYPE              AS pj_type,
    SUM(m.QTYCONSUMED)     AS total_consumed,
    SUM(m.QTYREQUIRED)     AS total_required,
    COUNT(DISTINCT m.CONTAINERID)   AS lot_count,
    COUNT(DISTINCT m.PJ_WORKORDER)  AS workorder_count
FROM DWH.DW_MES_LOTMATERIALSHISTORY m
LEFT JOIN DWH.DW_MES_CONTAINER c
    ON c.CONTAINERID = m.CONTAINERID
{{ WHERE_CLAUSE }}
GROUP BY
    TRUNC(m.TXNDATE),
    m.MATERIALPARTNAME,
    c.PJ_TYPE
ORDER BY txn_date, material_part
