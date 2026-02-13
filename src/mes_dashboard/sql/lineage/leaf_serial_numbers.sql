-- Unified LineageEngine - Leaf Serial Numbers
-- Find finished product serial numbers (FINISHEDNAME) for leaf lot CIDs.
-- Source: DW_MES_PJ_COMBINEDASSYLOTS (TMTT assembly merge records).
--
-- Parameters:
--   CID_FILTER - QueryBuilder-generated condition on ca.CONTAINERID
--
SELECT DISTINCT
    ca.CONTAINERID,
    ca.FINISHEDNAME
FROM DWH.DW_MES_PJ_COMBINEDASSYLOTS ca
WHERE {{ CID_FILTER }}
  AND ca.FINISHEDNAME IS NOT NULL
