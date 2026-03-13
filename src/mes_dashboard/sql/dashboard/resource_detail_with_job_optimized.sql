-- Optimized: dashboard/resource_detail_with_job
-- Changes:
--   1. Merged latest_txn CTE into base_data to avoid double scan of RESOURCESTATUS
--      (original had separate MAX(COALESCE(TXNDATE,LASTSTATUSCHANGEDATE)) scan)
--   2. Kept original exact timestamp equality JOIN (j.CREATEDATE = rs.LASTSTATUSCHANGEDATE)
--      JOBID in RESOURCESTATUS is not always populated, so timestamp match is more reliable
--   3. Replaced COALESCE in WHERE with OR-based predicate for index usage
--
-- Placeholders:
--   DAYS_BACK           - Number of days to look back
--   LOCATION_FILTER     - Location exclusion filter
--   ASSET_STATUS_FILTER - Asset status exclusion filter
--   WHERE_CLAUSE        - Dynamic WHERE conditions for final SELECT
-- Parameters:
--   :start_row - Pagination start row
--   :end_row   - Pagination end row

WITH base_data AS (
    SELECT *
    FROM (
        SELECT
            r.RESOURCEID,
            r.RESOURCENAME,
            r.OBJECTCATEGORY,
            r.OBJECTTYPE,
            r.RESOURCEFAMILYNAME,
            r.WORKCENTERNAME,
            r.LOCATIONNAME,
            r.VENDORNAME,
            r.VENDORMODEL,
            r.PJ_DEPARTMENT,
            r.PJ_ASSETSSTATUS,
            r.PJ_ISPRODUCTION,
            r.PJ_ISKEY,
            r.PJ_ISMONITOR,
            r.PJ_LOTID,
            r.DESCRIPTION,
            s.NEWSTATUSNAME,
            s.NEWREASONNAME,
            s.LASTSTATUSCHANGEDATE,
            s.OLDSTATUSNAME,
            s.OLDREASONNAME,
            s.AVAILABILITY,
            s.JOBID,
            s.TXNDATE,
            ROW_NUMBER() OVER (
                PARTITION BY r.RESOURCEID
                ORDER BY s.LASTSTATUSCHANGEDATE DESC NULLS LAST,
                         COALESCE(s.TXNDATE, s.LASTSTATUSCHANGEDATE) DESC
            ) AS rn
        FROM DWH.DW_MES_RESOURCE r
        JOIN DWH.DW_MES_RESOURCESTATUS s ON r.RESOURCEID = s.HISTORYID
        WHERE ((r.OBJECTCATEGORY = 'ASSEMBLY' AND r.OBJECTTYPE = 'ASSEMBLY')
            OR (r.OBJECTCATEGORY = 'WAFERSORT' AND r.OBJECTTYPE = 'WAFERSORT'))
          AND (s.TXNDATE >= SYSDATE - {{ DAYS_BACK }}
               OR (s.TXNDATE IS NULL AND s.LASTSTATUSCHANGEDATE >= SYSDATE - {{ DAYS_BACK }}))
          {{ LOCATION_FILTER }}
          {{ ASSET_STATUS_FILTER }}
    )
    WHERE rn = 1
),
max_time AS (
    SELECT MAX(LASTSTATUSCHANGEDATE) AS MAX_STATUS_TIME FROM base_data
)
SELECT * FROM (
    SELECT
        rs.RESOURCENAME,
        rs.WORKCENTERNAME,
        rs.RESOURCEFAMILYNAME,
        rs.NEWSTATUSNAME,
        rs.NEWREASONNAME,
        rs.LASTSTATUSCHANGEDATE,
        rs.PJ_DEPARTMENT,
        rs.VENDORNAME,
        rs.VENDORMODEL,
        rs.PJ_ISPRODUCTION,
        rs.PJ_ISKEY,
        rs.PJ_ISMONITOR,
        j.JOBID,
        rs.PJ_LOTID,
        j.JOBORDERNAME,
        j.JOBSTATUS,
        j.SYMPTOMCODENAME,
        j.CAUSECODENAME,
        j.REPAIRCODENAME,
        j.CREATEDATE as JOB_CREATEDATE,
        j.FIRSTCLOCKONDATE,
        mt.MAX_STATUS_TIME,
        ROUND((mt.MAX_STATUS_TIME - rs.LASTSTATUSCHANGEDATE) * 24 * 60, 0) as DOWN_MINUTES,
        ROW_NUMBER() OVER (
            ORDER BY
                CASE rs.NEWSTATUSNAME
                    WHEN 'UDT' THEN 1
                    WHEN 'SDT' THEN 2
                    ELSE 3
                END,
                rs.LASTSTATUSCHANGEDATE DESC NULLS LAST
        ) AS rn
    FROM base_data rs
    CROSS JOIN max_time mt
    LEFT JOIN DWH.DW_MES_JOB j ON j.RESOURCEID = rs.RESOURCEID
                           AND j.CREATEDATE = rs.LASTSTATUSCHANGEDATE
    WHERE {{ WHERE_CLAUSE }}
) WHERE rn BETWEEN :start_row AND :end_row
