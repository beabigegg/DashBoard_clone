-- Unified LineageEngine - Merge Sources
-- Find source lots merged into finished lots from DW_MES_PJ_COMBINEDASSYLOTS.
--
-- Parameters:
--   FINISHED_NAME_FILTER - QueryBuilder-generated condition on ca.FINISHEDNAME
--
SELECT
    ca.CONTAINERID   AS SOURCE_CID,
    ca.CONTAINERNAME AS SOURCE_NAME,
    ca.FINISHEDNAME,
    ca.LOTID         AS FINISHED_CID
FROM DWH.DW_MES_PJ_COMBINEDASSYLOTS ca
WHERE {{ FINISHED_NAME_FILTER }}
