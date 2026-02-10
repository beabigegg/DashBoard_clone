-- Mid-Section Defect - All Loss Reasons (cached daily)
-- Lightweight query for filter dropdown population.
-- Returns ALL loss reasons across all stations (not just TMTT).
--
-- Tables used:
--   DWH.DW_MES_LOTREJECTHISTORY (TXNDATE indexed)
--
-- Performance:
--   DISTINCT on one column with date filter only.
--   Cached 24h in Redis.
--
SELECT DISTINCT r.LOSSREASONNAME
FROM DWH.DW_MES_LOTREJECTHISTORY r
WHERE r.TXNDATE >= SYSDATE - 180
  AND r.LOSSREASONNAME IS NOT NULL
ORDER BY r.LOSSREASONNAME
