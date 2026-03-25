-- Lot Equipment Name Check
-- Check which container names have equipment records at given workcenters.
-- Returns DISTINCT container names that have at least one equipment record.
--
-- Dynamic placeholders:
--   CONTAINER_FILTER  - filter on c.CONTAINERNAME (via QueryBuilder)
--   WORKCENTER_FILTER - filter on h.WORKCENTERNAME (via QueryBuilder)

SELECT DISTINCT
    c.CONTAINERNAME
FROM DWH.DW_MES_LOTWIPHISTORY h
JOIN DWH.DW_MES_CONTAINER c ON h.CONTAINERID = c.CONTAINERID
WHERE h.EQUIPMENTID IS NOT NULL
  AND h.TRACKINTIMESTAMP IS NOT NULL
  AND {{ CONTAINER_FILTER }}
  AND {{ WORKCENTER_FILTER }}
