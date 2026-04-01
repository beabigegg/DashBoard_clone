-- Production History Row Count (data integrity baseline)
-- Counts grouped records for the full date range without chunking.
-- Used to detect truncation in the chunk-merge pipeline.
--
-- Parameters:
--   :start_date    - YYYY-MM-DD (inclusive)
--   :end_date_excl - YYYY-MM-DD (exclusive = end_date + 1 day)
--
-- Dynamic placeholder (replaced by service):
--   {{ EXTRA_FILTERS }} - AND conditions for pj_type, lot, etc.

SELECT COUNT(*) AS row_count
FROM (
    SELECT 1
    FROM DWH.DW_MES_CONTAINER c
    JOIN DWH.DW_MES_LOTWIPHISTORY h ON c.CONTAINERID = h.CONTAINERID
    WHERE h.TRACKINTIMESTAMP >= TO_TIMESTAMP(:start_date,    'YYYY-MM-DD')
      AND h.TRACKINTIMESTAMP <  TO_TIMESTAMP(:end_date_excl, 'YYYY-MM-DD')
      AND h.EQUIPMENTID IS NOT NULL
      AND h.TRACKINTIMESTAMP IS NOT NULL
      {{ EXTRA_FILTERS }}
    GROUP BY
        c.CONTAINERNAME,
        c.PJ_TYPE,
        c.PJ_BOP,
        c.MFGORDERNAME,
        c.FIRSTNAME,
        c.PRODUCTLINENAME,
        h.WORKCENTERNAME,
        h.SPECNAME,
        h.EQUIPMENTID,
        h.EQUIPMENTNAME
)
