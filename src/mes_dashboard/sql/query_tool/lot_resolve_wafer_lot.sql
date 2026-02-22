-- Wafer LOT (FIRSTNAME) to CONTAINERID Resolution
-- Expands wafer lot values to matching LOT containers.
--
-- Parameters:
--   WAFER_FILTER - QueryBuilder filter on FIRSTNAME + object constraints
--
SELECT
    CONTAINERID,
    CONTAINERNAME,
    MFGORDERNAME,
    SPECNAME,
    QTY,
    FIRSTNAME
FROM DWH.DW_MES_CONTAINER
WHERE {{ WAFER_FILTER }}
