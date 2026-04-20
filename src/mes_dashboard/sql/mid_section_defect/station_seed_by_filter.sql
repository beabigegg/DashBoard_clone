-- MSD Container Mode: Seed Resolution via Detection Station History
-- Finds containers that both match the user's input filter AND have records
-- at the detection station in LOTWIPHISTORY. These become the lineage seeds.
--
-- Parameters:
--   {{ VALUE_FILTER }}   - e.g. c.MFGORDERNAME IN ('WO001','WO002')
--   {{ STATION_FILTER }} - Dynamic LIKE clause for workcenter (built by Python)

SELECT DISTINCT
    h.CONTAINERID,
    c.CONTAINERNAME,
    c.MFGORDERNAME
FROM DWH.DW_MES_LOTWIPHISTORY h
JOIN DWH.DW_MES_CONTAINER c ON c.CONTAINERID = h.CONTAINERID
WHERE ({{ VALUE_FILTER }})
  AND ({{ STATION_FILTER }})
  AND h.EQUIPMENTID IS NOT NULL
  AND h.TRACKINTIMESTAMP IS NOT NULL
ORDER BY c.CONTAINERNAME
