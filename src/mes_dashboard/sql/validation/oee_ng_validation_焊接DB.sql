-- =============================================================================
-- OEE NG Validation Queries — 焊接_DB Workcenter Group
-- Purpose : Cross-check TRACKOUTQTY and NG_QTY against PJMES051 Excel report
-- Period  : 2026-03-01 ~ 2026-03-25 (shift-adjusted, boundary 07:30)
-- Expected: TRACKOUTQTY ~19M, NG_QTY ~1.5M
-- Schema  : DWH (MBU1_R)
-- Shift   : timestamp - 450/1440 shifts the day boundary from 00:00 to 07:30
-- Note    : DEFECTQTY is intentionally excluded from NG formula
--           Records where SPECNAME = '成品倉' are excluded (terminate lots)
-- =============================================================================


-- =============================================================================
-- QUERY 1: Production output (TRACKOUTQTY) per equipment per shift_date
-- Strategy: Deduplicate partial track-outs with ROW_NUMBER on the same
--           CONTAINERID + SPECNAME + WORKCENTERNAME + TRACKINTIMESTAMP group,
--           keeping only the latest TRACKOUTTIMESTAMP record (last partial),
--           then SUM its TRACKOUTQTY as the effective output for that pass.
-- =============================================================================

WITH wc_group AS (
    -- All workcenters belonging to 焊接_DB group
    SELECT DISTINCT WORK_CENTER
    FROM DWH.DW_MES_SPEC_WORKCENTER_V
    WHERE WORK_CENTER_GROUP = '焊接_DB'
),
eqp_list AS (
    -- All equipment IDs that belong to those workcenters
    SELECT DISTINCT r.RESOURCEID AS EQUIPMENTID
    FROM DWH.DW_MES_RESOURCE r
    WHERE r.WORKCENTERNAME IN (SELECT WORK_CENTER FROM wc_group)
),
wip_raw AS (
    -- Raw LOTWIPHISTORY rows for the date range and equipment set.
    -- Shift boundary 07:30: subtract 450 minutes so that 07:30 maps to 00:00.
    SELECT
        h.CONTAINERID,
        h.SPECNAME,
        h.WORKCENTERNAME,
        h.EQUIPMENTID,
        h.EQUIPMENTNAME,
        h.TRACKINTIMESTAMP,
        h.TRACKOUTTIMESTAMP,
        h.TRACKOUTQTY,
        -- Shift-adjusted calendar date (07:30 boundary)
        TRUNC(h.TRACKOUTTIMESTAMP - 450/1440) AS SHIFT_DATE,
        -- Dedup key: same lot + station + trackin pass may have multiple partial
        -- trackout rows. Rank by trackouttimestamp DESC; rn=1 is the final record.
        ROW_NUMBER() OVER (
            PARTITION BY h.CONTAINERID,
                         h.SPECNAME,
                         h.WORKCENTERNAME,
                         h.EQUIPMENTID,
                         h.TRACKINTIMESTAMP
            ORDER BY h.TRACKOUTTIMESTAMP DESC
        ) AS RN
    FROM DWH.DW_MES_LOTWIPHISTORY h
    WHERE h.TRACKOUTTIMESTAMP >= TO_TIMESTAMP('2026-03-01', 'YYYY-MM-DD') + 450/1440
      AND h.TRACKOUTTIMESTAMP <  TO_TIMESTAMP('2026-03-26', 'YYYY-MM-DD') + 450/1440
      AND h.EQUIPMENTID IS NOT NULL
      AND h.TRACKOUTQTY  IS NOT NULL
      AND h.SPECNAME <> '成品倉'
      AND h.WORKCENTERNAME <> '成品倉'
      AND h.EQUIPMENTID IN (SELECT EQUIPMENTID FROM eqp_list)
),
wip_deduped AS (
    -- Keep only the final partial-trackout record per pass
    SELECT
        CONTAINERID,
        SPECNAME,
        WORKCENTERNAME,
        EQUIPMENTID,
        EQUIPMENTNAME,
        TRACKINTIMESTAMP,
        TRACKOUTTIMESTAMP,
        TRACKOUTQTY,
        SHIFT_DATE
    FROM wip_raw
    WHERE RN = 1
)
SELECT
    w.EQUIPMENTID,
    w.EQUIPMENTNAME,
    w.WORKCENTERNAME,
    w.SHIFT_DATE,
    COUNT(DISTINCT w.CONTAINERID)           AS LOT_COUNT,
    SUM(w.TRACKOUTQTY)                      AS TRACKOUT_QTY
FROM wip_deduped w
GROUP BY
    w.EQUIPMENTID,
    w.EQUIPMENTNAME,
    w.WORKCENTERNAME,
    w.SHIFT_DATE
ORDER BY
    w.WORKCENTERNAME,
    w.EQUIPMENTID,
    w.SHIFT_DATE
;


-- =============================================================================
-- QUERY 2: NG quantity using compound key join
-- Strategy: Build production fingerprints (CONTAINERID + SPECNAME +
--           WORKCENTERNAME + SHIFT_DATE) from LOTWIPHISTORY, then join to
--           LOTREJECTHISTORY on the same compound key.
--           NG = REJECTQTY + STANDBYQTY + QTYTOPROCESS + INPROCESSQTY + PROCESSEDQTY
--           DEFECTQTY is excluded per business rule.
-- =============================================================================

WITH wc_group AS (
    SELECT DISTINCT WORK_CENTER
    FROM DWH.DW_MES_SPEC_WORKCENTER_V
    WHERE WORK_CENTER_GROUP = '焊接_DB'
),
eqp_list AS (
    SELECT DISTINCT r.RESOURCEID AS EQUIPMENTID
    FROM DWH.DW_MES_RESOURCE r
    WHERE r.WORKCENTERNAME IN (SELECT WORK_CENTER FROM wc_group)
),
-- Step 1: Production fingerprints from LOTWIPHISTORY (after dedup)
wip_raw AS (
    SELECT
        h.CONTAINERID,
        h.SPECNAME,
        h.WORKCENTERNAME,
        h.EQUIPMENTID,
        h.EQUIPMENTNAME,
        h.TRACKINTIMESTAMP,
        h.TRACKOUTTIMESTAMP,
        TRUNC(h.TRACKOUTTIMESTAMP - 450/1440) AS SHIFT_DATE,
        ROW_NUMBER() OVER (
            PARTITION BY h.CONTAINERID,
                         h.SPECNAME,
                         h.WORKCENTERNAME,
                         h.EQUIPMENTID,
                         h.TRACKINTIMESTAMP
            ORDER BY h.TRACKOUTTIMESTAMP DESC
        ) AS RN
    FROM DWH.DW_MES_LOTWIPHISTORY h
    WHERE h.TRACKOUTTIMESTAMP >= TO_TIMESTAMP('2026-03-01', 'YYYY-MM-DD') + 450/1440
      AND h.TRACKOUTTIMESTAMP <  TO_TIMESTAMP('2026-03-26', 'YYYY-MM-DD') + 450/1440
      AND h.EQUIPMENTID IS NOT NULL
      AND h.SPECNAME <> '成品倉'
      AND h.WORKCENTERNAME <> '成品倉'
      AND h.EQUIPMENTID IN (SELECT EQUIPMENTID FROM eqp_list)
),
wip_fingerprint AS (
    -- Unique (CONTAINERID, SPECNAME, WORKCENTERNAME, EQUIPMENTID, SHIFT_DATE) keys
    SELECT DISTINCT
        CONTAINERID,
        SPECNAME,
        WORKCENTERNAME,
        EQUIPMENTID,
        EQUIPMENTNAME,
        SHIFT_DATE
    FROM wip_raw
    WHERE RN = 1
),
-- Step 2: Reject records from LOTREJECTHISTORY, shift-adjusted, excluding 成品倉
reject_raw AS (
    SELECT
        r.CONTAINERID,
        r.SPECNAME,
        r.WORKCENTERNAME,
        TRUNC(r.TXNDATE - 450/1440)                    AS SHIFT_DATE,
        -- NG formula: 5 fields, no DEFECTQTY
        NVL(r.REJECTQTY,    0)
          + NVL(r.STANDBYQTY,  0)
          + NVL(r.QTYTOPROCESS, 0)
          + NVL(r.INPROCESSQTY, 0)
          + NVL(r.PROCESSEDQTY, 0)                     AS NG_QTY,
        NVL(r.DEFECTQTY, 0)                            AS DEFECT_QTY  -- for info only
    FROM DWH.DW_MES_LOTREJECTHISTORY r
    WHERE r.TXNDATE >= TO_TIMESTAMP('2026-03-01', 'YYYY-MM-DD') + 450/1440
      AND r.TXNDATE <  TO_TIMESTAMP('2026-03-26', 'YYYY-MM-DD') + 450/1440
      AND r.SPECNAME     <> '成品倉'
      AND r.WORKCENTERNAME <> '成品倉'
      AND EXISTS (
          SELECT 1 FROM DWH.DW_MES_SPEC_WORKCENTER_V v
          WHERE v.WORK_CENTER = r.WORKCENTERNAME
            AND v.WORK_CENTER_GROUP = '焊接_DB'
      )
),
-- Step 3: Join reject records to production fingerprints via compound key
--         CONTAINERID + SPECNAME + WORKCENTERNAME + SHIFT_DATE
ng_joined AS (
    SELECT
        p.EQUIPMENTID,
        p.EQUIPMENTNAME,
        p.WORKCENTERNAME,
        p.SHIFT_DATE,
        rj.NG_QTY,
        rj.DEFECT_QTY
    FROM reject_raw rj
    JOIN wip_fingerprint p
      ON  p.CONTAINERID    = rj.CONTAINERID
      AND p.SPECNAME        = rj.SPECNAME
      AND p.WORKCENTERNAME  = rj.WORKCENTERNAME
      AND p.SHIFT_DATE      = rj.SHIFT_DATE
)
SELECT
    ng.EQUIPMENTID,
    ng.EQUIPMENTNAME,
    ng.WORKCENTERNAME,
    ng.SHIFT_DATE,
    SUM(ng.NG_QTY)     AS NG_QTY,
    SUM(ng.DEFECT_QTY) AS DEFECT_QTY   -- shown for reference, not in NG formula
FROM ng_joined ng
GROUP BY
    ng.EQUIPMENTID,
    ng.EQUIPMENTNAME,
    ng.WORKCENTERNAME,
    ng.SHIFT_DATE
ORDER BY
    ng.WORKCENTERNAME,
    ng.EQUIPMENTID,
    ng.SHIFT_DATE
;


-- =============================================================================
-- QUERY 3: Comparison summary — per equipment TRACKOUTQTY, NG_QTY, Yield%
-- Combines Query 1 and Query 2 in one pass.
-- Yield% = TRACKOUT_QTY / (TRACKOUT_QTY + NG_QTY) * 100
-- A grand-total row is appended via UNION ALL / ROLLUP.
-- =============================================================================

WITH wc_group AS (
    SELECT DISTINCT WORK_CENTER
    FROM DWH.DW_MES_SPEC_WORKCENTER_V
    WHERE WORK_CENTER_GROUP = '焊接_DB'
),
eqp_list AS (
    SELECT DISTINCT r.RESOURCEID AS EQUIPMENTID
    FROM DWH.DW_MES_RESOURCE r
    WHERE r.WORKCENTERNAME IN (SELECT WORK_CENTER FROM wc_group)
),
-- ---------- production side ----------
wip_raw AS (
    SELECT
        h.CONTAINERID,
        h.SPECNAME,
        h.WORKCENTERNAME,
        h.EQUIPMENTID,
        h.EQUIPMENTNAME,
        h.TRACKINTIMESTAMP,
        h.TRACKOUTTIMESTAMP,
        h.TRACKOUTQTY,
        TRUNC(h.TRACKOUTTIMESTAMP - 450/1440) AS SHIFT_DATE,
        ROW_NUMBER() OVER (
            PARTITION BY h.CONTAINERID,
                         h.SPECNAME,
                         h.WORKCENTERNAME,
                         h.EQUIPMENTID,
                         h.TRACKINTIMESTAMP
            ORDER BY h.TRACKOUTTIMESTAMP DESC
        ) AS RN
    FROM DWH.DW_MES_LOTWIPHISTORY h
    WHERE h.TRACKOUTTIMESTAMP >= TO_TIMESTAMP('2026-03-01', 'YYYY-MM-DD') + 450/1440
      AND h.TRACKOUTTIMESTAMP <  TO_TIMESTAMP('2026-03-26', 'YYYY-MM-DD') + 450/1440
      AND h.EQUIPMENTID IS NOT NULL
      AND h.TRACKOUTQTY  IS NOT NULL
      AND h.SPECNAME <> '成品倉'
      AND h.WORKCENTERNAME <> '成品倉'
      AND h.EQUIPMENTID IN (SELECT EQUIPMENTID FROM eqp_list)
),
wip_deduped AS (
    SELECT
        CONTAINERID,
        SPECNAME,
        WORKCENTERNAME,
        EQUIPMENTID,
        EQUIPMENTNAME,
        SHIFT_DATE,
        TRACKOUTQTY
    FROM wip_raw
    WHERE RN = 1
),
prod_by_eqp AS (
    SELECT
        EQUIPMENTID,
        EQUIPMENTNAME,
        WORKCENTERNAME,
        SUM(TRACKOUTQTY)          AS TRACKOUT_QTY,
        COUNT(DISTINCT CONTAINERID) AS LOT_COUNT
    FROM wip_deduped
    GROUP BY EQUIPMENTID, EQUIPMENTNAME, WORKCENTERNAME
),
-- ---------- fingerprint for NG join ----------
wip_fingerprint AS (
    SELECT DISTINCT
        CONTAINERID,
        SPECNAME,
        WORKCENTERNAME,
        EQUIPMENTID,
        SHIFT_DATE
    FROM wip_raw
    WHERE RN = 1
),
-- ---------- reject side ----------
reject_raw AS (
    SELECT
        r.CONTAINERID,
        r.SPECNAME,
        r.WORKCENTERNAME,
        TRUNC(r.TXNDATE - 450/1440) AS SHIFT_DATE,
        NVL(r.REJECTQTY,    0)
          + NVL(r.STANDBYQTY,  0)
          + NVL(r.QTYTOPROCESS, 0)
          + NVL(r.INPROCESSQTY, 0)
          + NVL(r.PROCESSEDQTY, 0) AS NG_QTY
    FROM DWH.DW_MES_LOTREJECTHISTORY r
    WHERE r.TXNDATE >= TO_TIMESTAMP('2026-03-01', 'YYYY-MM-DD') + 450/1440
      AND r.TXNDATE <  TO_TIMESTAMP('2026-03-26', 'YYYY-MM-DD') + 450/1440
      AND r.SPECNAME     <> '成品倉'
      AND r.WORKCENTERNAME <> '成品倉'
      AND EXISTS (
          SELECT 1 FROM DWH.DW_MES_SPEC_WORKCENTER_V v
          WHERE v.WORK_CENTER = r.WORKCENTERNAME
            AND v.WORK_CENTER_GROUP = '焊接_DB'
      )
),
ng_by_eqp AS (
    SELECT
        p.EQUIPMENTID,
        SUM(rj.NG_QTY) AS NG_QTY
    FROM reject_raw rj
    JOIN wip_fingerprint p
      ON  p.CONTAINERID    = rj.CONTAINERID
      AND p.SPECNAME        = rj.SPECNAME
      AND p.WORKCENTERNAME  = rj.WORKCENTERNAME
      AND p.SHIFT_DATE      = rj.SHIFT_DATE
    GROUP BY p.EQUIPMENTID
),
-- ---------- combined per-equipment ----------
combined AS (
    SELECT
        pr.EQUIPMENTID,
        pr.EQUIPMENTNAME,
        pr.WORKCENTERNAME,
        pr.LOT_COUNT,
        pr.TRACKOUT_QTY,
        NVL(ng.NG_QTY, 0)                                           AS NG_QTY
    FROM prod_by_eqp pr
    LEFT JOIN ng_by_eqp ng ON ng.EQUIPMENTID = pr.EQUIPMENTID
)
-- ---------- per-equipment rows + grand total ----------
SELECT
    CASE GROUPING(EQUIPMENTID) WHEN 1 THEN '*** GRAND TOTAL ***' ELSE EQUIPMENTID END
        AS EQUIPMENTID,
    CASE GROUPING(EQUIPMENTID) WHEN 1 THEN '' ELSE EQUIPMENTNAME END
        AS EQUIPMENTNAME,
    CASE GROUPING(EQUIPMENTID) WHEN 1 THEN '' ELSE WORKCENTERNAME END
        AS WORKCENTERNAME,
    SUM(LOT_COUNT)      AS LOT_COUNT,
    SUM(TRACKOUT_QTY)   AS TRACKOUT_QTY,
    SUM(NG_QTY)         AS NG_QTY,
    ROUND(
        SUM(TRACKOUT_QTY)
        / NULLIF(SUM(TRACKOUT_QTY) + SUM(NG_QTY), 0)
        * 100,
        4
    )                   AS YIELD_PCT
FROM combined
GROUP BY ROLLUP(EQUIPMENTID, EQUIPMENTNAME, WORKCENTERNAME)
HAVING GROUPING(EQUIPMENTID) = 1
    -- Suppress intermediate ROLLUP subtotals (EQP without NAME); keep leaf + grand total
    OR (GROUPING(EQUIPMENTID) = 0 AND GROUPING(EQUIPMENTNAME) = 0)
ORDER BY
    GROUPING(EQUIPMENTID) ASC,   -- detail rows first, grand total last
    WORKCENTERNAME,
    EQUIPMENTID
;
