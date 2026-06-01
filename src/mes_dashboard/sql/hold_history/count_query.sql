-- Hold History Row Count for row-count chunking (USE_ROW_COUNT_CHUNKING=true)
-- Counts base_facts rows matching the same WHERE clause.
-- Parameters:
--   :start_date - Start date (YYYY-MM-DD)
--   :end_date   - End date (YYYY-MM-DD)
-- Note: NON_QUALITY_REASONS placeholder must be filled by service before execution.

SELECT COUNT(*) AS row_count
FROM DWH.DW_MES_HOLDRELEASEHISTORY h
WHERE (
    h.HOLDTXNDATE >= TO_DATE(:start_date || ' 073000', 'YYYY-MM-DD HH24MISS') - 1
    OR h.RELEASETXNDATE >= TO_DATE(:start_date || ' 073000', 'YYYY-MM-DD HH24MISS') - 1
    OR h.RELEASETXNDATE IS NULL
  )
  AND (
    h.HOLDTXNDATE <= TO_DATE(:end_date || ' 073000', 'YYYY-MM-DD HH24MISS')
    OR h.RELEASETXNDATE <= TO_DATE(:end_date || ' 073000', 'YYYY-MM-DD HH24MISS')
    OR h.RELEASETXNDATE IS NULL
  )
