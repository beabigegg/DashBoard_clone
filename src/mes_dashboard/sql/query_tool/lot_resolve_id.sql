-- LOT ID to CONTAINERID Resolution
-- Converts user-input LOT ID (CONTAINERNAME) to internal CONTAINERID
--
-- Parameters:
--   CONTAINER_FILTER - QueryBuilder filter on CONTAINERNAME
--
-- Note: CONTAINERID is 16-char hex (e.g., '48810380001cba48')
--       CONTAINERNAME is user-visible LOT ID (e.g., 'GA23100020-A00-011')

SELECT
    CONTAINERID,
    CONTAINERNAME,
    MFGORDERNAME,
    SPECNAME,
    QTY
FROM DWH.DW_MES_CONTAINER
WHERE {{ CONTAINER_FILTER }}
