-- Mid-Section Defect Traceability - TMTT Detection Data (Query 1)
-- Returns LOT-level data with TMTT input, ALL defects, and lot metadata
--
-- Parameters:
--   :start_date - Start date (YYYY-MM-DD)
--   :end_date   - End date (YYYY-MM-DD)
--
-- Tables used:
--   DWH.DW_MES_LOTWIPHISTORY (TMTT station records)
--   DWH.DW_MES_LOTREJECTHISTORY (defect records - ALL loss reasons)
--   DWH.DW_MES_CONTAINER (product info + MFGORDERNAME for genealogy)
--   DWH.DW_MES_WIP (WORKFLOWNAME)
--
-- Changes from tmtt_defect/base_data.sql:
--   1. Removed hardcoded LOSSREASONNAME filter → fetches ALL loss reasons
--   2. Added MFGORDERNAME from DW_MES_CONTAINER (needed for genealogy batch)
--   3. Removed MOLD equipment lookup (upstream tracing done separately)
--   4. Kept existing dedup logic (ROW_NUMBER by CONTAINERID, latest TRACKINTIMESTAMP)

WITH tmtt_records AS (
    SELECT /*+ MATERIALIZE */
        h.CONTAINERID,
        h.EQUIPMENTID AS TMTT_EQUIPMENTID,
        h.EQUIPMENTNAME AS TMTT_EQUIPMENTNAME,
        h.TRACKINQTY,
        h.TRACKINTIMESTAMP,
        h.TRACKOUTTIMESTAMP,
        h.FINISHEDRUNCARD,
        h.SPECNAME,
        h.WORKCENTERNAME,
        ROW_NUMBER() OVER (
            PARTITION BY h.CONTAINERID
            ORDER BY h.TRACKINTIMESTAMP DESC, h.TRACKOUTTIMESTAMP DESC NULLS LAST
        ) AS rn
    FROM DWH.DW_MES_LOTWIPHISTORY h
    WHERE h.TRACKINTIMESTAMP >= TO_DATE(:start_date, 'YYYY-MM-DD')
      AND h.TRACKINTIMESTAMP < TO_DATE(:end_date, 'YYYY-MM-DD') + 1
      AND (UPPER(h.WORKCENTERNAME) LIKE '%TMTT%' OR h.WORKCENTERNAME LIKE '%測試%')
      AND h.EQUIPMENTID IS NOT NULL
      AND h.TRACKINTIMESTAMP IS NOT NULL
),
tmtt_deduped AS (
    SELECT * FROM tmtt_records WHERE rn = 1
),
tmtt_rejects AS (
    SELECT /*+ MATERIALIZE */
        r.CONTAINERID,
        r.LOSSREASONNAME,
        SUM(NVL(r.REJECTQTY, 0) + NVL(r.STANDBYQTY, 0) + NVL(r.QTYTOPROCESS, 0)
            + NVL(r.INPROCESSQTY, 0) + NVL(r.PROCESSEDQTY, 0)) AS REJECTQTY
    FROM DWH.DW_MES_LOTREJECTHISTORY r
    WHERE r.TXNDATE >= TO_DATE(:start_date, 'YYYY-MM-DD')
      AND r.TXNDATE < TO_DATE(:end_date, 'YYYY-MM-DD') + 1
      AND (UPPER(r.WORKCENTERNAME) LIKE '%TMTT%' OR r.WORKCENTERNAME LIKE '%測試%')
    GROUP BY r.CONTAINERID, r.LOSSREASONNAME
),
lot_metadata AS (
    SELECT /*+ MATERIALIZE */
        c.CONTAINERID,
        c.CONTAINERNAME,
        c.MFGORDERNAME,
        c.PJ_TYPE,
        c.PRODUCTLINENAME
    FROM DWH.DW_MES_CONTAINER c
    WHERE c.CONTAINERID IN (SELECT CONTAINERID FROM tmtt_deduped)
),
workflow_info AS (
    SELECT /*+ MATERIALIZE */
        DISTINCT w.CONTAINERID,
        w.WORKFLOWNAME
    FROM DWH.DW_MES_WIP w
    WHERE w.CONTAINERID IN (SELECT CONTAINERID FROM tmtt_deduped)
      AND w.PRODUCTLINENAME <> '點測'
)
SELECT
    t.CONTAINERID,
    m.CONTAINERNAME,
    m.MFGORDERNAME,
    m.PJ_TYPE,
    m.PRODUCTLINENAME,
    NVL(wf.WORKFLOWNAME, t.SPECNAME) AS WORKFLOW,
    t.FINISHEDRUNCARD,
    t.TMTT_EQUIPMENTID,
    t.TMTT_EQUIPMENTNAME,
    t.TRACKINQTY,
    t.TRACKINTIMESTAMP,
    r.LOSSREASONNAME,
    NVL(r.REJECTQTY, 0) AS REJECTQTY
FROM tmtt_deduped t
LEFT JOIN lot_metadata m ON t.CONTAINERID = m.CONTAINERID
LEFT JOIN workflow_info wf ON t.CONTAINERID = wf.CONTAINERID
LEFT JOIN tmtt_rejects r ON t.CONTAINERID = r.CONTAINERID
ORDER BY t.TRACKINTIMESTAMP
