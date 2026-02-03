-- Utilization Heatmap Query
-- Returns equipment utilization data by workcenter and date
--
-- Calculates PRD% = PRD_HOURS / AVAIL_HOURS * 100
-- where AVAIL_HOURS = PRD + SBY + UDT + SDT + EGT (excludes NST)
--
-- Parameters:
--   :days - Number of days to look back
--
-- Dynamic placeholders:
--   LOCATION_FILTER - Location exclusion filter
--   ASSET_STATUS_FILTER - Asset status exclusion filter
--   FLAG_FILTER - Equipment flag filters (isProduction, isKey, isMonitor)

SELECT
    ss.WORKCENTERNAME,
    TRUNC(ss.TXNDATE) as DATA_DATE,
    SUM(CASE WHEN ss.OLDSTATUSNAME = 'PRD' THEN ss.HOURS ELSE 0 END) as PRD_HOURS,
    SUM(CASE WHEN ss.OLDSTATUSNAME IN ('PRD', 'SBY', 'UDT', 'SDT', 'EGT') THEN ss.HOURS ELSE 0 END) as AVAIL_HOURS
FROM DWH.DW_MES_RESOURCESTATUS_SHIFT ss
JOIN DWH.DW_MES_RESOURCE r ON ss.HISTORYID = r.RESOURCEID
WHERE ss.TXNDATE >= TRUNC(SYSDATE) - :days
  AND ss.TXNDATE < TRUNC(SYSDATE)
  AND ss.WORKCENTERNAME IS NOT NULL
  AND ((r.OBJECTCATEGORY = 'ASSEMBLY' AND r.OBJECTTYPE = 'ASSEMBLY')
       OR (r.OBJECTCATEGORY = 'WAFERSORT' AND r.OBJECTTYPE = 'WAFERSORT'))
  {{ LOCATION_FILTER }}
  {{ ASSET_STATUS_FILTER }}
  {{ FLAG_FILTER }}
GROUP BY ss.WORKCENTERNAME, TRUNC(ss.TXNDATE)
ORDER BY ss.WORKCENTERNAME, DATA_DATE
