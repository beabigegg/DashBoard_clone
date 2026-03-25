-- Lot Equipment Lookup
-- Resolves container names + workcenter names → distinct equipment IDs
-- with observed date range (min track-in / max track-out).
--
-- Dynamic placeholders:
--   CONTAINER_FILTER  - filter on c.CONTAINERNAME (via QueryBuilder)
--   WORKCENTER_FILTER - filter on h.WORKCENTERNAME (via QueryBuilder)

SELECT DISTINCT
    h.EQUIPMENTID,
    h.EQUIPMENTNAME,
    MIN(h.TRACKINTIMESTAMP) OVER () AS MIN_TRACKIN,
    MAX(NVL(h.TRACKOUTTIMESTAMP, h.TRACKINTIMESTAMP)) OVER () AS MAX_TRACKOUT
FROM DWH.DW_MES_LOTWIPHISTORY h
JOIN DWH.DW_MES_CONTAINER c ON h.CONTAINERID = c.CONTAINERID
WHERE h.EQUIPMENTID IS NOT NULL
  AND h.TRACKINTIMESTAMP IS NOT NULL
  AND {{ CONTAINER_FILTER }}
  AND {{ WORKCENTER_FILTER }}
