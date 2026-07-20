-- DB Scheduling — Idle Equipment History Fallback (2026-07 rule change)
--
-- Why this file exists (deliberate, narrow exception to ADR 0013):
--   ADR 0013 decided DB-scheduling needs no dedicated Oracle query because
--   every candidate machine always had a live row in the 5-min WIP cache
--   (DWH.DW_MES_LOT_V) — it was always mid-lot. The 2026-07 business-rule
--   change requires ALSO surfacing currently-IDLE 焊接_DB equipment as
--   candidates. An idle machine has no WIP-cache row (nothing to read), so
--   its most recent SPECNAME/PACKAGE_LF attributes must come from history
--   (DWH.DW_MES_LOTWIPHISTORY) instead. This query only ever runs against a
--   small, pre-filtered IN-list (the handful of 焊接_DB machines NOT already
--   covered by the WIP cache), so it stays a small synchronous lookup — it
--   does not reintroduce a per-request Oracle read for the primary (live)
--   candidate pool, which still comes entirely from the WIP cache.
--
-- Parameters:
--   :cutoff_date - only consider trackouts on/after this date (YYYY-MM-DD).
--                  30-day lookback (see db_scheduling_service.py) is long
--                  enough to cover a typical PM/changeover idle span without
--                  surfacing equipment that has been relocated or
--                  decommissioned long ago.
--
-- Dynamic placeholders:
--   EQUIPMENT_FILTER - IN-list condition on UPPER(h.EQUIPMENTNAME), scoped to
--                       the specific idle equipment set for this request.
--   SPEC_FILTER      - IN-list condition on h.SPECNAME, scoped to the DB-00
--                       12-spec list (DB_PROCESS_SPECS).
--
-- Note: Uses EQUIPMENTNAME (native to DW_MES_LOTWIPHISTORY) — NOT
--       EQUIPMENTS, which only exists on DW_MES_LOT_V. PACKAGE_LF is
--       LOTWIPHISTORY's own package column and is NOT the same column name
--       as DW_MES_LOT_V.PACKAGE_LEF used elsewhere in db_scheduling_service.
WITH ranked AS (
    SELECT
        h.EQUIPMENTNAME,
        h.SPECNAME,
        h.PACKAGE_LF,
        h.TRACKOUTTIMESTAMP,
        ROW_NUMBER() OVER (
            PARTITION BY h.EQUIPMENTNAME
            ORDER BY h.TRACKOUTTIMESTAMP DESC
        ) AS rn
    FROM DWH.DW_MES_LOTWIPHISTORY h
    WHERE h.EQUIPMENTNAME IS NOT NULL
      AND h.TRACKOUTTIMESTAMP IS NOT NULL
      AND h.TRACKOUTTIMESTAMP >= TO_DATE(:cutoff_date, 'YYYY-MM-DD')
      AND {{ EQUIPMENT_FILTER }}
      AND {{ SPEC_FILTER }}
)
SELECT
    EQUIPMENTNAME,
    SPECNAME,
    PACKAGE_LF,
    TRACKOUTTIMESTAMP
FROM ranked
WHERE rn = 1
