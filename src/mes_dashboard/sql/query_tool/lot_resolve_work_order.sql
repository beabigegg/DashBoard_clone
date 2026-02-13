-- Work Order to CONTAINERID Resolution
-- Expands work orders (MFGORDERNAME) to associated CONTAINERIDs.
-- Uses DW_MES_CONTAINER directly (same source as LOT ID resolve).
--
-- Parameters:
--   WORK_ORDER_FILTER - QueryBuilder filter on MFGORDERNAME
--
SELECT
    CONTAINERID,
    MFGORDERNAME,
    CONTAINERNAME,
    SPECNAME
FROM DWH.DW_MES_CONTAINER
WHERE {{ WORK_ORDER_FILTER }}
