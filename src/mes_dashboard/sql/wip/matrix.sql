-- WIP Matrix Query
-- Returns workcenter x product line (package) matrix
--
-- Aggregates QTY by WORKCENTER_GROUP and PACKAGE_LEF
-- Used for the overview dashboard matrix visualization
--
-- Dynamic placeholders:
--   WHERE_CLAUSE - Filter conditions including status and hold type

SELECT
    WORKCENTER_GROUP,
    WORKCENTERSEQUENCE_GROUP,
    PACKAGE_LEF,
    SUM(QTY) as QTY
FROM DWH.DW_MES_LOT_V
{{ WHERE_CLAUSE }}
GROUP BY WORKCENTER_GROUP, WORKCENTERSEQUENCE_GROUP, PACKAGE_LEF
ORDER BY WORKCENTERSEQUENCE_GROUP, PACKAGE_LEF
