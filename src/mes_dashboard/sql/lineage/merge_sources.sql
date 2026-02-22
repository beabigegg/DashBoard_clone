-- Unified LineageEngine - Merge Sources
-- Find source lots merged into target LOT CIDs from DW_MES_PJ_COMBINEDASSYLOTS.
--
-- Parameters:
--   TARGET_CID_FILTER - QueryBuilder-generated condition on ca.LOTID
--
SELECT
    ca.CONTAINERID   AS SOURCE_CID,
    ca.CONTAINERNAME AS SOURCE_NAME,
    ca.FINISHEDNAME,
    ca.LOTID         AS FINISHED_CID
FROM DWH.DW_MES_PJ_COMBINEDASSYLOTS ca
WHERE {{ TARGET_CID_FILTER }}
