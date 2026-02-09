-- TMTT Defect Analysis - Base Data Query
-- Returns LOT-level data with TMTT input, defects (印字/腳型), and MOLD equipment
--
-- Parameters:
--   :start_date - Start date (YYYY-MM-DD)
--   :end_date   - End date (YYYY-MM-DD)
--
-- Tables used:
--   DWH.DW_MES_LOTWIPHISTORY (TMTT station records, MOLD station records)
--   DWH.DW_MES_LOTREJECTHISTORY (defect records)
--   DWH.DW_MES_CONTAINER (product info)
--   DWH.DW_MES_WIP (WORKFLOWNAME, filtered by PRODUCTLINENAME <> '點測')
--
-- Notes:
--   - LOSSREASONNAME: '276_腳型不良', '277_印字不良'
--   - TMTT station: WORKCENTERNAME matching 'TMTT' or '測試'
--   - MOLD station: WORKCENTERNAME matching '成型'
--   - Multiple MOLD equipment per LOT: take earliest TRACKINTIMESTAMP
--   - TMTT dedup: one row per CONTAINERID, take latest TRACKINTIMESTAMP
--   - LOTREJECTHISTORY only has EQUIPMENTNAME (no EQUIPMENTID)
--   - WORKFLOW: from DW_MES_WIP.WORKFLOWNAME (exclude PRODUCTLINENAME='點測')
--   - Defect qty = SUM(REJECTQTY + STANDBYQTY + QTYTOPROCESS + INPROCESSQTY + PROCESSEDQTY)

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
      AND r.LOSSREASONNAME IN ('276_腳型不良', '277_印字不良')
    GROUP BY r.CONTAINERID, r.LOSSREASONNAME
),
mold_records AS (
    SELECT /*+ MATERIALIZE */
        m.CONTAINERID,
        m.EQUIPMENTID AS MOLD_EQUIPMENTID,
        m.EQUIPMENTNAME AS MOLD_EQUIPMENTNAME,
        ROW_NUMBER() OVER (
            PARTITION BY m.CONTAINERID
            ORDER BY m.TRACKINTIMESTAMP ASC
        ) AS mold_rn
    FROM DWH.DW_MES_LOTWIPHISTORY m
    WHERE m.CONTAINERID IN (SELECT CONTAINERID FROM tmtt_deduped)
      AND (m.WORKCENTERNAME LIKE '%成型%')
      AND m.EQUIPMENTID IS NOT NULL
),
mold_deduped AS (
    SELECT * FROM mold_records WHERE mold_rn = 1
),
product_info AS (
    SELECT /*+ MATERIALIZE */
        c.CONTAINERID,
        c.CONTAINERNAME,
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
    p.CONTAINERNAME,
    p.PJ_TYPE,
    p.PRODUCTLINENAME,
    NVL(wf.WORKFLOWNAME, t.SPECNAME) AS WORKFLOW,
    t.FINISHEDRUNCARD,
    t.TMTT_EQUIPMENTID,
    t.TMTT_EQUIPMENTNAME,
    t.TRACKINQTY,
    t.TRACKINTIMESTAMP,
    m.MOLD_EQUIPMENTID,
    m.MOLD_EQUIPMENTNAME,
    r.LOSSREASONNAME,
    NVL(r.REJECTQTY, 0) AS REJECTQTY
FROM tmtt_deduped t
LEFT JOIN product_info p ON t.CONTAINERID = p.CONTAINERID
LEFT JOIN workflow_info wf ON t.CONTAINERID = wf.CONTAINERID
LEFT JOIN mold_deduped m ON t.CONTAINERID = m.CONTAINERID
LEFT JOIN tmtt_rejects r ON t.CONTAINERID = r.CONTAINERID
ORDER BY t.TRACKINTIMESTAMP
