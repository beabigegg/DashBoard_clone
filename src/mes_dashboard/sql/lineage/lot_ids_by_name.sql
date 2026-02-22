-- Unified LineageEngine - LOT IDs by Container Name
-- Resolves container IDs by LOT names for wafer-origin joins.
--
-- Parameters:
--   NAME_FILTER - QueryBuilder-generated condition on c.CONTAINERNAME
--
SELECT
    c.CONTAINERID,
    c.CONTAINERNAME
FROM DWH.DW_MES_CONTAINER c
WHERE c.OBJECTTYPE = 'LOT'
  AND {{ NAME_FILTER }}
