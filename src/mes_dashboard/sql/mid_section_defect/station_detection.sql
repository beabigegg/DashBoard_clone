-- Optimized: mid_section_defect/station_detection
-- Change: Replaced SELECT DISTINCT in workflow_info with ROW_NUMBER()
--         to ensure deterministic 1:1 join (prevents row multiplication
--         when a container has multiple workflows)

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
    WHERE h.TRACKINTIMESTAMP >= TO_DATE(:start_date, 'YYYY-MM-DD')
      AND h.TRACKINTIMESTAMP < TO_DATE(:end_date, 'YYYY-MM-DD') + 1
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
    WHERE r.TXNDATE >= TO_DATE(:start_date, 'YYYY-MM-DD')
      AND r.TXNDATE < TO_DATE(:end_date, 'YYYY-MM-DD') + 1
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
        CONTAINERID,
        WORKFLOWNAME
    FROM (
        SELECT
            w.CONTAINERID,
            w.WORKFLOWNAME,
            ROW_NUMBER() OVER (
                PARTITION BY w.CONTAINERID
                ORDER BY w.WORKFLOWNAME
            ) AS wf_rn
        FROM DWH.DW_MES_WIP w
        WHERE w.CONTAINERID IN (SELECT CONTAINERID FROM detection_deduped)
          AND w.PRODUCTLINENAME <> '點測'
    )
    WHERE wf_rn = 1
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
    t.TRACKINQTY,
    t.TRACKINTIMESTAMP,
    r.LOSSREASONNAME,
    NVL(r.REJECTQTY, 0) AS REJECTQTY
FROM detection_deduped t
LEFT JOIN lot_metadata m ON t.CONTAINERID = m.CONTAINERID
LEFT JOIN workflow_info wf ON t.CONTAINERID = wf.CONTAINERID
LEFT JOIN detection_rejects r ON t.CONTAINERID = r.CONTAINERID
ORDER BY t.TRACKINTIMESTAMP
