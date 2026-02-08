-- Dashboard KPI Standalone Query
-- Returns overall KPI statistics for dashboard header
-- This is a self-contained query with CTE for optimal performance
--
-- Placeholders:
--   DAYS_BACK - Number of days to look back
--   LOCATION_FILTER - Location exclusion filter (AND ...)
--   ASSET_STATUS_FILTER - Asset status exclusion filter (AND ...)
--   WHERE_CLAUSE - Additional filter conditions

WITH resource_latest_status AS (
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
          AND COALESCE(s.TXNDATE, s.LASTSTATUSCHANGEDATE) >= SYSDATE - {{ DAYS_BACK }}
          {{ LOCATION_FILTER }}
          {{ ASSET_STATUS_FILTER }}
    )
    WHERE rn = 1
)
SELECT
    COUNT(*) as TOTAL,
    SUM(CASE WHEN NEWSTATUSNAME = 'PRD' THEN 1 ELSE 0 END) as PRD_COUNT,
    SUM(CASE WHEN NEWSTATUSNAME = 'SBY' THEN 1 ELSE 0 END) as SBY_COUNT,
    SUM(CASE WHEN NEWSTATUSNAME = 'UDT' THEN 1 ELSE 0 END) as UDT_COUNT,
    SUM(CASE WHEN NEWSTATUSNAME = 'SDT' THEN 1 ELSE 0 END) as SDT_COUNT,
    SUM(CASE WHEN NEWSTATUSNAME = 'EGT' THEN 1 ELSE 0 END) as EGT_COUNT,
    SUM(CASE WHEN NEWSTATUSNAME = 'NST' THEN 1 ELSE 0 END) as NST_COUNT,
    SUM(CASE WHEN NEWSTATUSNAME NOT IN ('PRD','SBY','UDT','SDT','EGT','NST') THEN 1 ELSE 0 END) as OTHER_COUNT
FROM resource_latest_status
{{ WHERE_CLAUSE }}
