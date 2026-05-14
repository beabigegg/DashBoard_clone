-- Production History Main Query
-- Queries production footprint for given PJ_TYPEs + TrackIn date chunk.
--
-- Parameters (bound via oracledb named params):
--   :chunk_start    - YYYY-MM-DD (chunk start, inclusive)
--   :chunk_end_excl - YYYY-MM-DD (chunk end exclusive = user end_date + 1 day)
--
-- Dynamic placeholder (replaced by service):
--   {{ EXTRA_FILTERS }}  - Additional AND conditions (type, lot, wc, eqp, pkg, bop)
--                          Replaced with empty string when no optional filters given.
--
-- Row grain (changed by change `prod-history-detail-raw-rows`):
--   One row per LOTWIPHISTORY partial track-out — no GROUP BY.
--   TRACKINTIMESTAMP / TRACKOUTTIMESTAMP / TRACKINQTY / TRACKOUTQTY are raw
--   per-partial values; consumers must NOT assume "first partial = original
--   batch quantity". Matrix lot-count is computed downstream in DuckDB via
--   COUNT(DISTINCT CONTAINERNAME) — see data-shape-contract §3.4 + PH-01..PH-04.
--
--   PJ_FUNCTION is carried through (pre-staged for Change 3 filter use); not
--   yet a user filter.
--
-- Note: EQUIPMENTID IS NOT NULL excludes checkpoint-only stations.

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
    h.TRACKOUTQTY
FROM DWH.DW_MES_CONTAINER c
JOIN DWH.DW_MES_LOTWIPHISTORY h ON c.CONTAINERID = h.CONTAINERID
WHERE h.TRACKINTIMESTAMP >= TO_TIMESTAMP(:chunk_start,    'YYYY-MM-DD')
  AND h.TRACKINTIMESTAMP <  TO_TIMESTAMP(:chunk_end_excl, 'YYYY-MM-DD')
  AND h.EQUIPMENTID IS NOT NULL
  AND h.TRACKINTIMESTAMP IS NOT NULL
  {{ EXTRA_FILTERS }}
ORDER BY h.TRACKINTIMESTAMP ASC, c.CONTAINERNAME
