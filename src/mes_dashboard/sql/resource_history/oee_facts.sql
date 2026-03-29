-- OEE production facts: trackout quantities + NG quantities per equipment per shift date.
-- Joins LOTWIPHISTORY (production) with LOTREJECTHISTORY (NG) via compound key
-- (CONTAINERID + SPECNAME + WORKCENTERNAME), assigning NG to the producing equipment.
--
-- Shift date boundary: 07:30 → SHIFT_DATE = TRUNC(TRACKOUTTIMESTAMP - 450/1440)
-- Reject window: ±30 days beyond production date range for cross-period matching.
--
-- Parameters:
--   :start_date       - Production start date (YYYY-MM-DD)
--   :end_date         - Production end date (YYYY-MM-DD)
--   :reject_start     - Reject query start (start_date - 30 days)
--   :reject_end       - Reject query end (end_date + 30 days)

WITH wip AS (
    SELECT /*+ MATERIALIZE */
        w.CONTAINERID,
        w.SPECNAME,
        w.WORKCENTERNAME,
        w.EQUIPMENTID,
        TRUNC(w.TRACKOUTTIMESTAMP - 450/1440) AS SHIFT_DATE,
        w.TRACKOUTQTY
    FROM DWH.DW_MES_LOTWIPHISTORY w
    WHERE w.TRACKOUTTIMESTAMP >= TO_DATE(:start_date, 'YYYY-MM-DD') + 450/1440
      AND w.TRACKOUTTIMESTAMP <  TO_DATE(:end_date,   'YYYY-MM-DD') + 1 + 450/1440
      AND w.SPECNAME       <> '成品倉'
      AND w.WORKCENTERNAME <> '成品倉'
),
reject AS (
    SELECT /*+ MATERIALIZE */
        r.CONTAINERID,
        r.SPECNAME,
        r.WORKCENTERNAME,
        NVL(r.REJECTQTY, 0)
          + NVL(r.STANDBYQTY, 0)
          + NVL(r.QTYTOPROCESS, 0)
          + NVL(r.INPROCESSQTY, 0)
          + NVL(r.PROCESSEDQTY, 0) AS NG_QTY
    FROM DWH.DW_MES_LOTREJECTHISTORY r
    WHERE r.TXNDATE >= TO_DATE(:reject_start, 'YYYY-MM-DD')
      AND r.TXNDATE <  TO_DATE(:reject_end,   'YYYY-MM-DD') + 1
      AND r.SPECNAME       <> '成品倉'
      AND r.WORKCENTERNAME <> '成品倉'
),
reject_agg AS (
    SELECT
        CONTAINERID,
        SPECNAME,
        WORKCENTERNAME,
        SUM(NG_QTY) AS NG_QTY
    FROM reject
    GROUP BY CONTAINERID, SPECNAME, WORKCENTERNAME
),
-- Trackout: count every partial trackout record (no dedup)
trackout_agg AS (
    SELECT
        EQUIPMENTID,
        SHIFT_DATE,
        SUM(TRACKOUTQTY) AS TRACKOUT_QTY
    FROM wip
    GROUP BY EQUIPMENTID, SHIFT_DATE
),
-- NG attribution: deduplicate compound key to avoid fan-out when
-- a container has multiple partial trackouts on the same equipment
wip_keys AS (
    SELECT DISTINCT
        CONTAINERID,
        SPECNAME,
        WORKCENTERNAME,
        EQUIPMENTID,
        SHIFT_DATE
    FROM wip
),
ng_agg AS (
    SELECT
        k.EQUIPMENTID,
        k.SHIFT_DATE,
        SUM(NVL(r.NG_QTY, 0)) AS NG_QTY
    FROM wip_keys k
    LEFT JOIN reject_agg r
        ON  r.CONTAINERID    = k.CONTAINERID
        AND r.SPECNAME       = k.SPECNAME
        AND r.WORKCENTERNAME = k.WORKCENTERNAME
    GROUP BY k.EQUIPMENTID, k.SHIFT_DATE
)
SELECT
    t.EQUIPMENTID,
    t.SHIFT_DATE,
    t.TRACKOUT_QTY,
    COALESCE(n.NG_QTY, 0) AS NG_QTY
FROM trackout_agg t
LEFT JOIN ng_agg n
    ON  n.EQUIPMENTID = t.EQUIPMENTID
    AND n.SHIFT_DATE  = t.SHIFT_DATE
ORDER BY t.EQUIPMENTID, t.SHIFT_DATE
