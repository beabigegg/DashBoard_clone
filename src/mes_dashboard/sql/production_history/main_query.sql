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
-- GROUP BY rationale:
--   Same LOT+WC+SPEC+EQP may have multiple partial track-out records.
--   We take MIN(TrackIn), MAX(TrackOut) to get the effective window.
--
-- Note: EQUIPMENTID IS NOT NULL excludes checkpoint-only stations.

SELECT
    c.CONTAINERNAME,
    c.PJ_TYPE,
    c.PJ_BOP,
    c.MFGORDERNAME           AS WORK_ORDER,
    c.FIRSTNAME              AS WAFER_LOT,
    h.WORKCENTERNAME,
    h.SPECNAME,
    h.EQUIPMENTID,
    h.EQUIPMENTNAME,
    MIN(h.TRACKINTIMESTAMP)  AS TRACKIN_TS,
    MAX(h.TRACKOUTTIMESTAMP) AS TRACKOUT_TS,
    MIN(h.TRACKINQTY)        AS TRACKIN_QTY,
    MAX(h.TRACKOUTQTY)       AS TRACKOUT_QTY
FROM DWH.DW_MES_CONTAINER c
JOIN DWH.DW_MES_LOTWIPHISTORY h ON c.CONTAINERID = h.CONTAINERID
WHERE h.TRACKINTIMESTAMP >= TO_TIMESTAMP(:chunk_start,    'YYYY-MM-DD')
  AND h.TRACKINTIMESTAMP <  TO_TIMESTAMP(:chunk_end_excl, 'YYYY-MM-DD')
  AND h.EQUIPMENTID IS NOT NULL
  AND h.TRACKINTIMESTAMP IS NOT NULL
  {{ EXTRA_FILTERS }}
GROUP BY
    c.CONTAINERNAME,
    c.PJ_TYPE,
    c.PJ_BOP,
    c.MFGORDERNAME,
    c.FIRSTNAME,
    h.WORKCENTERNAME,
    h.SPECNAME,
    h.EQUIPMENTID,
    h.EQUIPMENTNAME
