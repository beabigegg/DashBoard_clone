-- Defect Traceability - Downstream Reject Records (Forward Tracing)
-- Get reject records for tracked LOTs at all downstream stations
--
-- Parameters:
--   Dynamically built IN clause for descendant CONTAINERIDs ({{ DESCENDANT_FILTER }})
--
-- Tables used:
--   DWH.DW_MES_LOTREJECTHISTORY (reject records)
--
-- Performance:
--   CONTAINERID has index. Batch IN clause (up to 1000 per query).

SELECT
    r.CONTAINERID,
    r.WORKCENTERNAME,
    CASE
        WHEN UPPER(r.WORKCENTERNAME) LIKE '%元件切割%'
            OR UPPER(r.WORKCENTERNAME) LIKE '%PKG_SAW%' THEN '元件切割'
        WHEN UPPER(r.WORKCENTERNAME) LIKE '%切割%' THEN '切割'
        WHEN UPPER(r.WORKCENTERNAME) LIKE '%焊接_DB%'
            OR UPPER(r.WORKCENTERNAME) LIKE '%焊_DB_料%'
            OR UPPER(r.WORKCENTERNAME) LIKE '%焊_DB%' THEN '焊接_DB'
        WHEN UPPER(r.WORKCENTERNAME) LIKE '%焊接_WB%'
            OR UPPER(r.WORKCENTERNAME) LIKE '%焊_WB_料%'
            OR UPPER(r.WORKCENTERNAME) LIKE '%焊_WB%' THEN '焊接_WB'
        WHEN UPPER(r.WORKCENTERNAME) LIKE '%焊接_DW%'
            OR UPPER(r.WORKCENTERNAME) LIKE '%焊_DW%'
            OR UPPER(r.WORKCENTERNAME) LIKE '%焊_DW_料%' THEN '焊接_DW'
        WHEN UPPER(r.WORKCENTERNAME) LIKE '%成型%'
            OR UPPER(r.WORKCENTERNAME) LIKE '%成型_料%' THEN '成型'
        WHEN UPPER(r.WORKCENTERNAME) LIKE '%去膠%' THEN '去膠'
        WHEN UPPER(r.WORKCENTERNAME) LIKE '%水吹砂%' THEN '水吹砂'
        WHEN UPPER(r.WORKCENTERNAME) LIKE '%掛鍍%'
            OR UPPER(r.WORKCENTERNAME) LIKE '%滾鍍%'
            OR UPPER(r.WORKCENTERNAME) LIKE '%條鍍%'
            OR UPPER(r.WORKCENTERNAME) LIKE '%電鍍%'
            OR UPPER(r.WORKCENTERNAME) LIKE '%補鍍%'
            OR UPPER(r.WORKCENTERNAME) LIKE '%TOTAI%'
            OR UPPER(r.WORKCENTERNAME) LIKE '%BANDL%' THEN '電鍍'
        WHEN UPPER(r.WORKCENTERNAME) LIKE '%移印%' THEN '移印'
        WHEN UPPER(r.WORKCENTERNAME) LIKE '%切彎腳%' THEN '切彎腳'
        WHEN UPPER(r.WORKCENTERNAME) LIKE '%TMTT%'
            OR UPPER(r.WORKCENTERNAME) LIKE '%測試%' THEN '測試'
        ELSE NULL
    END AS WORKCENTER_GROUP,
    NVL(TRIM(r.LOSSREASONNAME), '(未填寫)') AS LOSSREASONNAME,
    NVL(TRIM(r.EQUIPMENTNAME), '(NA)') AS EQUIPMENTNAME,
    NVL(r.REJECTQTY, 0)
      + NVL(r.STANDBYQTY, 0)
      + NVL(r.QTYTOPROCESS, 0)
      + NVL(r.INPROCESSQTY, 0)
      + NVL(r.PROCESSEDQTY, 0) AS REJECT_TOTAL_QTY,
    r.TXNDATE
FROM DWH.DW_MES_LOTREJECTHISTORY r
WHERE {{ DESCENDANT_FILTER }}
ORDER BY r.CONTAINERID, r.TXNDATE
