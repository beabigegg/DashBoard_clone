-- Mid-Section Defect Traceability - Split Chain (Query 2a)
-- Resolve split ancestors via DW_MES_CONTAINER.SPLITFROMID
--
-- Parameters:
--   Dynamically built IN clause for CONTAINERIDs
--
-- Tables used:
--   DWH.DW_MES_CONTAINER (5.2M rows, CONTAINERID UNIQUE index)
--
-- Performance:
--   CONTAINERID has UNIQUE index. Batch IN clause (up to 1000 per query).
--   Each batch <1s.
--
-- Note: SPLITFROMID may be NULL for lots that were not split from another.
--   BFS caller uses SPLITFROMID to walk upward; NULL means chain terminus.
--
SELECT
    c.CONTAINERID,
    c.SPLITFROMID,
    c.ORIGINALCONTAINERID,
    c.CONTAINERNAME
FROM DWH.DW_MES_CONTAINER c
WHERE {{ CID_FILTER }}
