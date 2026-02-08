-- Resource Latest Status Query
-- Returns the latest status for each resource using ROW_NUMBER()
--
-- Dynamic placeholders:
--   days_back - Number of days to look back for status changes
--   LOCATION_FILTER - Location exclusion filter (AND ...)
--   ASSET_STATUS_FILTER - Asset status exclusion filter (AND ...)
--
-- Note: This query is designed to be embedded as a subquery (no CTE/WITH clause)
-- The MAX_TXNDATE calculation is done inline using a scalar subquery with KEEP FIRST

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
      AND COALESCE(s.TXNDATE, s.LASTSTATUSCHANGEDATE) >= SYSDATE - {{ days_back }}
      {{ LOCATION_FILTER }}
      {{ ASSET_STATUS_FILTER }}
)
WHERE rn = 1
