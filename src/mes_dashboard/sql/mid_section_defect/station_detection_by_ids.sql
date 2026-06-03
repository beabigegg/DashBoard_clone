-- Defect Traceability - Station Detection Data by Container IDs
-- Returns LOT-level data with detection station input, ALL defects, and lot metadata
-- Used in container query mode where seed lots are resolved first.
--
-- Parameters:
--   {{ CONTAINER_IDS }} - Comma-separated quoted CONTAINERID list (built by Python)
--   {{ STATION_FILTER }} - Dynamic LIKE clause for workcenter group (built by Python)
--   {{ STATION_FILTER_REJECTS }} - Same pattern for reject CTE (column alias differs)
--
-- Tables used:
--   DWH.DW_MES_LOTWIPHISTORY (detection station records)
--   DWH.DW_MES_LOTREJECTHISTORY (defect records - charge-off + non-charge-off)
--   DWH.DW_MES_CONTAINER (product info + MFGORDERNAME for genealogy)
--   DWH.DW_MES_WIP (WORKFLOWNAME)

WITH detection_records AS (
    SELECT /*+ MATERIALIZE */
        h.CONTAINERID,
        h.EQUIPMENTID AS DETECTION_EQUIPMENTID,
        h.EQUIPMENTNAME AS DETECTION_EQUIPMENTNAME,
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
    WHERE h.CONTAINERID IN ({{ CONTAINER_IDS }})
      AND ({{ STATION_FILTER }})
      AND h.EQUIPMENTID IS NOT NULL
      AND h.TRACKINTIMESTAMP IS NOT NULL
),
detection_deduped AS (
    SELECT * FROM detection_records WHERE rn = 1
),
detection_rejects AS (
    SELECT /*+ MATERIALIZE */
        r.CONTAINERID,
        r.LOSSREASONNAME,
        SUM(NVL(r.REJECTQTY, 0) + NVL(r.STANDBYQTY, 0) + NVL(r.QTYTOPROCESS, 0)
            + NVL(r.INPROCESSQTY, 0) + NVL(r.PROCESSEDQTY, 0)
            + NVL(r.DEFECTQTY, 0)) AS REJECTQTY
    FROM DWH.DW_MES_LOTREJECTHISTORY r
    WHERE r.CONTAINERID IN ({{ CONTAINER_IDS }})
      AND ({{ STATION_FILTER_REJECTS }})
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
    WHERE c.CONTAINERID IN (SELECT CONTAINERID FROM detection_deduped)
),
workflow_info AS (
    SELECT /*+ MATERIALIZE */
        DISTINCT w.CONTAINERID,
        w.WORKFLOWNAME
    FROM DWH.DW_MES_WIP w
    WHERE w.CONTAINERID IN (SELECT CONTAINERID FROM detection_deduped)
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
    t.DETECTION_EQUIPMENTID,
    t.DETECTION_EQUIPMENTNAME,
    t.WORKCENTERNAME,
    t.TRACKINQTY,
    t.TRACKINTIMESTAMP,
    r.LOSSREASONNAME,
    NVL(r.REJECTQTY, 0) AS REJECTQTY
FROM detection_deduped t
LEFT JOIN lot_metadata m ON t.CONTAINERID = m.CONTAINERID
LEFT JOIN workflow_info wf ON t.CONTAINERID = wf.CONTAINERID
LEFT JOIN detection_rejects r ON t.CONTAINERID = r.CONTAINERID
ORDER BY t.TRACKINTIMESTAMP
