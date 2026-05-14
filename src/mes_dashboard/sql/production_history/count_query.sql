-- Production History Row Count (data integrity baseline)
-- Counts raw LOTWIPHISTORY partial track-out rows for the full date range
-- without chunking. Used to detect truncation in the chunk-merge pipeline.
--
-- Row grain (changed by change `prod-history-detail-raw-rows`):
--   No GROUP BY — counts raw partial rows, matching main_query.sql.
--
-- Parameters:
--   :start_date    - YYYY-MM-DD (inclusive)
--   :end_date_excl - YYYY-MM-DD (exclusive = end_date + 1 day)
--
-- Dynamic placeholder (replaced by service):
--   {{ EXTRA_FILTERS }} - AND conditions for pj_type, lot, etc.

SELECT COUNT(*) AS row_count
FROM DWH.DW_MES_CONTAINER c
JOIN DWH.DW_MES_LOTWIPHISTORY h ON c.CONTAINERID = h.CONTAINERID
WHERE h.TRACKINTIMESTAMP >= TO_TIMESTAMP(:start_date,    'YYYY-MM-DD')
  AND h.TRACKINTIMESTAMP <  TO_TIMESTAMP(:end_date_excl, 'YYYY-MM-DD')
  AND h.EQUIPMENTID IS NOT NULL
  AND h.TRACKINTIMESTAMP IS NOT NULL
  {{ EXTRA_FILTERS }}
