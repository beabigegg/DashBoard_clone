-- Production History Paged Query (ROW_NUMBER() row-count chunking)
-- Used when USE_ROW_COUNT_CHUNKING=true.
--
-- Parameters (bound via oracledb named params):
--   :chunk_start    - YYYY-MM-DD (full dataset chunk start, inclusive)
--   :chunk_end_excl - YYYY-MM-DD (full dataset chunk end exclusive = user end_date + 1 day)
--   :start_row      - 1-based inclusive start (from decompose_by_row_count)
--   :end_row        - 1-based inclusive end
--
-- Dynamic placeholder (replaced by service):
--   {{ EXTRA_FILTERS }}  - Additional AND conditions (same as main_query.sql)
--
-- ORDER BY key (BQE-03): TRACKINTIMESTAMP ASC, CONTAINERID ASC
-- Fully tie-breaking across the dataset for stable row-count pagination.

WITH ranked AS (
    SELECT
        c.CONTAINERNAME,
        c.PJ_TYPE,
        c.PJ_BOP,
        c.PJ_FUNCTION,
        c.MFGORDERNAME,
        c.FIRSTNAME,
        c.PRODUCTLINENAME,
        h.WORKCENTERNAME,
        h.SPECNAME,
        h.EQUIPMENTID,
        h.EQUIPMENTNAME,
        h.TRACKINTIMESTAMP,
        h.TRACKOUTTIMESTAMP,
        h.TRACKINQTY,
        h.TRACKOUTQTY,
        ROW_NUMBER() OVER (
            ORDER BY h.TRACKINTIMESTAMP ASC, c.CONTAINERNAME ASC
        ) AS _rn
    FROM DWH.DW_MES_CONTAINER c
    JOIN DWH.DW_MES_LOTWIPHISTORY h ON c.CONTAINERID = h.CONTAINERID
    WHERE h.TRACKINTIMESTAMP >= TO_TIMESTAMP(:chunk_start,    'YYYY-MM-DD')
      AND h.TRACKINTIMESTAMP <  TO_TIMESTAMP(:chunk_end_excl, 'YYYY-MM-DD')
      AND h.EQUIPMENTID IS NOT NULL
      AND h.TRACKINTIMESTAMP IS NOT NULL
      {{ EXTRA_FILTERS }}
)
SELECT
    CONTAINERNAME,
    PJ_TYPE,
    PJ_BOP,
    PJ_FUNCTION,
    MFGORDERNAME,
    FIRSTNAME,
    PRODUCTLINENAME,
    WORKCENTERNAME,
    SPECNAME,
    EQUIPMENTID,
    EQUIPMENTNAME,
    TRACKINTIMESTAMP,
    TRACKOUTTIMESTAMP,
    TRACKINQTY,
    TRACKOUTQTY
FROM ranked
WHERE _rn BETWEEN :start_row AND :end_row
