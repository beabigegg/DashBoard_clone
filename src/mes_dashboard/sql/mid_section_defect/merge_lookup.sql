-- Mid-Section Defect Traceability - Merge Lookup (Query 2b)
-- Find source lots that were merged into finished lots
-- via DW_MES_PJ_COMBINEDASSYLOTS
--
-- Parameters:
--   Dynamically built IN clause for FINISHEDNAME values
--
-- Tables used:
--   DWH.DW_MES_PJ_COMBINEDASSYLOTS (1.97M rows, FINISHEDNAME indexed)
--
-- Performance:
--   FINISHEDNAME has index. Batch IN clause (up to 1000 per query).
--   Each batch <1s.
--
SELECT
    ca.CONTAINERID   AS SOURCE_CID,
    ca.CONTAINERNAME AS SOURCE_NAME,
    ca.FINISHEDNAME,
    ca.LOTID         AS FINISHED_CID
FROM DWH.DW_MES_PJ_COMBINEDASSYLOTS ca
WHERE {{ FINISHED_NAME_FILTER }}
