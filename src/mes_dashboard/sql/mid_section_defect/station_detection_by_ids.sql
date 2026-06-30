-- Mid-Section Defect - Step B: Detection Enrichment by Container IDs (UNIFIED)
-- Returns LOT-level detection data (detection station input, ALL defects, lot
-- metadata, workflow) for an explicit CONTAINERID set.  This is the single
-- enrichment query shared by BOTH query modes:
--   * Date-range mode: CONTAINERIDs come from station_detection_cids.sql (Step A);
--     DETECTION_TIME_FILTER / REJECT_TIME_FILTER bound rows to the query window so
--     semantics match the legacy single-SQL date-range query exactly.
--   * Container mode (LOT/工單/WAFER): CONTAINERIDs come from seed resolution;
--     the time-filter placeholders are empty (no window bound).
--
-- Parameters:
--   {{ CONTAINER_IDS }}          - Comma-separated quoted CONTAINERID list (Python-built, <=1000 per batch)
--   {{ STATION_FILTER }}         - Dynamic LIKE clause for workcenter group (WIP alias h)
--   {{ STATION_FILTER_REJECTS }} - Same pattern for reject CTE (alias r)
--   {{ DETECTION_TIME_FILTER }}  - Optional "AND h.TRACKINTIMESTAMP >= ... AND < ...+1" (date mode) or empty
--   {{ REJECT_TIME_FILTER }}     - Optional "AND r.TXNDATE >= ... AND < ...+1" (date mode) or empty
--   :start_date / :end_date      - Bound only when the time-filter placeholders are non-empty
--
-- Tables used:
--   DWH.DW_MES_LOTWIPHISTORY     (detection station records)
--   DWH.DW_MES_LOTREJECTHISTORY  (defect records - charge-off + non-charge-off)
--   DWH.DW_MES_CONTAINER         (product info + MFGORDERNAME for genealogy)
--   DWH.DW_MES_WIP               (WORKFLOWNAME)
--
-- Notes:
--   Dedup is PARTITION BY CONTAINERID, so batching the IN list never changes
--   results (each container is fully contained in one batch).
--   workflow_info uses ROW_NUMBER() (NOT DISTINCT) to guarantee a deterministic
--   1:1 join and prevent row multiplication when a container has multiple
--   workflows.

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
      {{ DETECTION_TIME_FILTER }}
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
      {{ REJECT_TIME_FILTER }}
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
