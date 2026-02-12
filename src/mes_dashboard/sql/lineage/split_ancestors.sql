-- Unified LineageEngine - Split Ancestors
-- Resolve split genealogy upward via DW_MES_CONTAINER.SPLITFROMID
--
-- Parameters:
--   CID_FILTER - QueryBuilder-generated condition for START WITH
--
-- Notes:
--   - CONNECT BY NOCYCLE prevents infinite loops on cyclic data.
--   - LEVEL <= 20 matches previous BFS guard.
--
-- Recursive WITH fallback (Oracle recursive subquery factoring):
--   If CONNECT BY execution plan regresses, replace this file's content with
--   sql/lineage/split_ancestors_recursive.sql (kept as reference).
--
SELECT
    c.CONTAINERID,
    c.SPLITFROMID,
    c.CONTAINERNAME,
    LEVEL AS SPLIT_DEPTH
FROM DWH.DW_MES_CONTAINER c
START WITH {{ CID_FILTER }}
CONNECT BY NOCYCLE PRIOR c.SPLITFROMID = c.CONTAINERID
    AND LEVEL <= 20
