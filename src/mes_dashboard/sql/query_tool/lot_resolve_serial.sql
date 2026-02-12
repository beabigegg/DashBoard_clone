-- Serial Number (流水號) to CONTAINERID Resolution
-- Converts finished product serial numbers to CONTAINERID list.
--
-- Parameters:
--   SERIAL_FILTER - QueryBuilder filter on p.FINISHEDNAME
--
SELECT DISTINCT
    p.CONTAINERID,
    p.FINISHEDNAME,
    c.CONTAINERNAME,
    c.SPECNAME
FROM DWH.DW_MES_PJ_COMBINEDASSYLOTS p
LEFT JOIN DWH.DW_MES_CONTAINER c ON p.CONTAINERID = c.CONTAINERID
WHERE {{ SERIAL_FILTER }}
