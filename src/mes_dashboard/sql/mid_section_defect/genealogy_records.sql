-- DEPRECATED: replaced by sql/lineage/split_ancestors.sql
-- Mid-Section Defect Traceability - LOT Genealogy Records (Query 2)
-- Batch query for split/merge records related to work orders
--
-- Parameters:
--   MFG_ORDER_FILTER - Dynamic IN clause for MFGORDERNAME (built by QueryBuilder)
--
-- Tables used:
--   DWH.DW_MES_CONTAINER (MFGORDERNAME indexed → get CONTAINERIDs)
--   DWH.DW_MES_HM_LOTMOVEOUT (48M rows, no CONTAINERID index)
--
-- Performance:
--   Full scan on HM_LOTMOVEOUT filtered by CONTAINERIDs from work orders.
--   CDONAME filter reduces result set to only split/merge operations.
--   Estimated 30-120s. Use aggressive caching (30-min TTL).
--
WITH work_order_lots AS (
    SELECT CONTAINERID
    FROM DWH.DW_MES_CONTAINER
    WHERE {{ MFG_ORDER_FILTER }}
)
SELECT
    h.CDONAME AS OPERATION_TYPE,
    h.CONTAINERID AS TARGET_CID,
    h.CONTAINERNAME AS TARGET_LOT,
    h.FROMCONTAINERID AS SOURCE_CID,
    h.FROMCONTAINERNAME AS SOURCE_LOT,
    h.QTY,
    h.TXNDATE
FROM DWH.DW_MES_HM_LOTMOVEOUT h
WHERE (
    h.CONTAINERID IN (SELECT CONTAINERID FROM work_order_lots)
    OR h.FROMCONTAINERID IN (SELECT CONTAINERID FROM work_order_lots)
)
  AND h.FROMCONTAINERID IS NOT NULL
  AND (UPPER(h.CDONAME) LIKE '%SPLIT%' OR UPPER(h.CDONAME) LIKE '%COMBINE%')
ORDER BY h.TXNDATE
