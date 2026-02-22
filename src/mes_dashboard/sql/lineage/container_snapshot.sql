-- Unified LineageEngine - Container Snapshot
-- Fetches key container attributes for semantic lineage classification.
--
-- Parameters:
--   CID_FILTER - QueryBuilder-generated condition on c.CONTAINERID
--
SELECT
    c.CONTAINERID,
    c.CONTAINERNAME,
    c.MFGORDERNAME,
    c.OBJECTTYPE,
    c.FIRSTNAME,
    c.ORIGINALCONTAINERID,
    c.SPLITFROMID
FROM DWH.DW_MES_CONTAINER c
WHERE {{ CID_FILTER }}
