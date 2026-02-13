-- Unified LineageEngine - Split Descendants (Forward Tree)
-- Resolve split genealogy downward from root(s) via DW_MES_CONTAINER.SPLITFROMID
--
-- Parameters:
--   ROOT_FILTER - QueryBuilder-generated condition for START WITH (root CIDs)
--
-- Notes:
--   - CONNECT BY NOCYCLE PRIOR prevents infinite loops on cyclic data.
--   - LEVEL <= 20 matches MAX_SPLIT_DEPTH guard.
--   - Direction is reversed from split_ancestors.sql:
--     ancestors: PRIOR SPLITFROMID = CONTAINERID (child → parent)
--     descendants: PRIOR CONTAINERID = SPLITFROMID (parent → child)
--
SELECT
    c.CONTAINERID,
    c.SPLITFROMID,
    c.CONTAINERNAME,
    LEVEL AS SPLIT_DEPTH
FROM DWH.DW_MES_CONTAINER c
START WITH {{ ROOT_FILTER }}
CONNECT BY NOCYCLE PRIOR c.CONTAINERID = c.SPLITFROMID
    AND LEVEL <= 20
