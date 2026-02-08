-- OU (Operating Utilization) Trend Query
-- Returns daily OU% for the past N days
--
-- Placeholders:
--   LOCATION_FILTER     - Location exclusion filter
--   ASSET_STATUS_FILTER - Asset status exclusion filter
--   FLAG_FILTER         - Equipment flag filter (isProduction, isKey, isMonitor)
-- Parameters:
--   :days - Number of days to look back

SELECT
    TRUNC(ss.TXNDATE) as DATA_DATE,
    SUM(CASE WHEN ss.OLDSTATUSNAME = 'PRD' THEN ss.HOURS ELSE 0 END) as PRD_HOURS,
    SUM(CASE WHEN ss.OLDSTATUSNAME = 'SBY' THEN ss.HOURS ELSE 0 END) as SBY_HOURS,
    SUM(CASE WHEN ss.OLDSTATUSNAME = 'UDT' THEN ss.HOURS ELSE 0 END) as UDT_HOURS,
    SUM(CASE WHEN ss.OLDSTATUSNAME = 'SDT' THEN ss.HOURS ELSE 0 END) as SDT_HOURS,
    SUM(CASE WHEN ss.OLDSTATUSNAME = 'EGT' THEN ss.HOURS ELSE 0 END) as EGT_HOURS,
    SUM(ss.HOURS) as TOTAL_HOURS
FROM DWH.DW_MES_RESOURCESTATUS_SHIFT ss
JOIN DWH.DW_MES_RESOURCE r ON ss.HISTORYID = r.RESOURCEID
WHERE ss.TXNDATE >= TRUNC(SYSDATE) - :days
  AND ss.TXNDATE < TRUNC(SYSDATE)
  AND ((r.OBJECTCATEGORY = 'ASSEMBLY' AND r.OBJECTTYPE = 'ASSEMBLY')
       OR (r.OBJECTCATEGORY = 'WAFERSORT' AND r.OBJECTTYPE = 'WAFERSORT'))
  {{ LOCATION_FILTER }}
  {{ ASSET_STATUS_FILTER }}
  {{ FLAG_FILTER }}
GROUP BY TRUNC(ss.TXNDATE)
ORDER BY DATA_DATE
