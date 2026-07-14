-- Production Achievement Rate — Oracle read (production-achievement-kanban;
-- grain widened + D6 fetch-completeness fix by production-achievement-overhaul)
--
-- Groups PA-05-qualifying DW_MES_LOTWIPHISTORY trackout events by
-- (output_date, shift_code, SPECNAME, PACKAGE_LF) -- PACKAGE_LF added by
-- production-achievement-overhaul (business-rules.md PA-09) as a first-class
-- spool dimension; it is NOT rolled up to package_lf_group here (that D1
-- merge-mapping join happens client-side, data-shape-contract.md §3.33).
-- SPECNAME is the finest station granularity available at the DB;
-- workcenter_group (大站點/PACKAGE) is resolved client-side via the
-- spec_workcenter_map inline array (sourced from
-- services/filter_cache.get_spec_workcenter_mapping(), business-rules.md
-- PA-06) — no SPECNAME->station mapping is done here, keeping this query
-- source-agnostic to that cache's contents.
--
-- shift_code (PA-01/PA-02) and output_date (PA-03/PA-04) are computed as SQL
-- CASE expressions so GROUP BY / SUM run server-side (design.md: avoids
-- fetching every qualifying row into Python). A thin Python mirror of both
-- exists in services/production_achievement_service.py for unit-test
-- boundary assertions only — not on this query's hot path.
--
-- PA-05 effective-output predicate (business-rules.md) is preserved verbatim
-- below — every SPECNAME/processtypename/WORKFLOWNAME branch, not simplified.
--
-- Parameters (bound via oracledb named params):
--   :start_date     - YYYY-MM-DD (inclusive)
--   :chunk_end_excl - YYYY-MM-DD HH24:MI:SS (exclusive upper bound). Widened
--                     from a date-only bind by production-achievement-overhaul
--                     (D6/PA-15) so the worker's pre_query() can append one
--                     narrow closing chunk `[end_date+1 00:00:00,
--                     end_date+1 07:30:00)` covering the overnight N-shift
--                     tail that a date-only (implicit-midnight) bind
--                     previously excluded from every fetch entirely. The
--                     :start_date bind's format mask stays date-only --
--                     every chunk's lower bound is always exactly midnight.
--
-- Dynamic placeholder (replaced by service; empty string when no filter):
--   {{ CONTAINERNAME_FILTER }} - optional caller-supplied CONTAINERNAME
--                                prefix filter (NOT part of the PA-05
--                                qualifying predicate itself)
--
-- Tables:
--   DWH.DW_MES_LOTWIPHISTORY (alias weh) — trackout events, SPECNAME,
--                                            processtypename, TRACKOUTQTY
--   DWH.DW_MES_WIP           (alias wb)  — WORKFLOWNAME (雙晶/三晶 classification),
--                                            joined by CONTAINERID (dedup via
--                                            ROW_NUMBER, one workflow row per
--                                            container — see mid_section_defect
--                                            precedent for this join shape)
--
-- scoped_containers pre-filters to only the CONTAINERIDs that can actually
-- need wb.WORKFLOWNAME resolved. Of PA-05's branches, only three reference
-- wb.WORKFLOWNAME at all (the plain D/B specs that must NOT be 雙晶/三晶,
-- plus the 雙晶-specific and 三晶-specific SPECNAME lists) -- every other
-- branch (金線/銀線/銅線 group, 2DB2WB, 2DB1WB, 2DB, 1DB, DBCB, CBRO group)
-- never touches WORKFLOWNAME.
--
-- DW_MES_WIP (95M+ rows) has NO index on CONTAINERID, only on CONTAINERNAME
-- and TXNDATE (confirmed via ALL_IND_COLUMNS against the real dev DB) --
-- joining/filtering it by CONTAINERID forces a full-table scan regardless
-- of how tightly scoped_containers is narrowed (measured: unscoped ROW_NUMBER()
-- OVER DW_MES_WIP by CONTAINERID timed out at 55s DPY-4024; scoping by date
-- range alone still took 47.5s for ~36K containers; scoping further by the
-- SPECNAME allowlist above only got to 41s for ~16.7K containers -- the cost
-- is dominated by the full scan itself, not the join cardinality). The fix
-- is bridging through DW_MES_CONTAINER (5.5M rows, indexed on BOTH
-- CONTAINERID and CONTAINERNAME) to translate our CONTAINERID scope into
-- CONTAINERNAMEs, then joining DW_MES_WIP via its indexed CONTAINERNAME
-- column instead. Measured after this fix: 30-day window down to ~22s.

WITH scoped_containers AS (
    SELECT DISTINCT weh.CONTAINERID
    FROM DWH.DW_MES_LOTWIPHISTORY weh
    WHERE weh.TRACKOUTTIMESTAMP >= TO_TIMESTAMP(:start_date,     'YYYY-MM-DD')
      AND weh.TRACKOUTTIMESTAMP <  TO_TIMESTAMP(:chunk_end_excl, 'YYYY-MM-DD HH24:MI:SS')
      {{ CONTAINERNAME_FILTER }}
      AND weh.SPECNAME IN (
        'Epoxy D/B','Eutectic D/B','Solder Paste D/B','Solder D/B+E-Clip+固化',
        'Solder D/B+E-Clip+固化-DW','Solder Paste D/B+E-Clip','Solder Paste D/B+E-Clip-DW',
        'Epoxy D/B-2','Eutectic D/B-2','Eutectic D/B-雙晶','Epoxy D/B-3','Eutectic D/B-3'
      )
),
scoped_container_names AS (
    SELECT c.CONTAINERID, c.CONTAINERNAME
    FROM DWH.DW_MES_CONTAINER c
    WHERE c.CONTAINERID IN (SELECT CONTAINERID FROM scoped_containers)
),
workflow_info_by_name AS (
    SELECT CONTAINERNAME, WORKFLOWNAME
    FROM (
        SELECT
            w.CONTAINERNAME,
            w.WORKFLOWNAME,
            ROW_NUMBER() OVER (
                PARTITION BY w.CONTAINERNAME
                ORDER BY w.WORKFLOWNAME
            ) AS wf_rn
        FROM DWH.DW_MES_WIP w
        WHERE w.CONTAINERNAME IN (SELECT CONTAINERNAME FROM scoped_container_names)
    )
    WHERE wf_rn = 1
),
workflow_info AS (
    SELECT scn.CONTAINERID, wi.WORKFLOWNAME
    FROM scoped_container_names scn
    LEFT JOIN workflow_info_by_name wi ON scn.CONTAINERNAME = wi.CONTAINERNAME
)
SELECT
    CASE
        WHEN weh.TRACKOUTTIMESTAMP IS NULL THEN NULL
        WHEN TO_CHAR(weh.TRACKOUTTIMESTAMP, 'YYYYMMDD') > '20191231'
             AND TO_CHAR(weh.TRACKOUTTIMESTAMP, 'YYYYMMDD') < '20200330'
        THEN
            -- PA-02: three-shift historical regime
            CASE
                WHEN TO_CHAR(weh.TRACKOUTTIMESTAMP, 'HH24:MI:SS') BETWEEN '08:00:00' AND '15:59:59' THEN 'A'
                WHEN TO_CHAR(weh.TRACKOUTTIMESTAMP, 'HH24:MI:SS') BETWEEN '16:00:00' AND '23:59:59' THEN 'B'
                ELSE 'C'
            END
        ELSE
            -- PA-01: two-shift current regime
            CASE
                WHEN TO_CHAR(weh.TRACKOUTTIMESTAMP, 'HH24:MI:SS') BETWEEN '07:30:00' AND '19:29:59' THEN 'D'
                ELSE 'N'
            END
    END AS SHIFT_CODE,
    CASE
        WHEN weh.TRACKOUTTIMESTAMP IS NULL THEN NULL
        WHEN TO_CHAR(weh.TRACKOUTTIMESTAMP, 'YYYYMMDD') > '20191231'
             AND TO_CHAR(weh.TRACKOUTTIMESTAMP, 'YYYYMMDD') < '20200330'
        THEN
            -- PA-04 (UNVERIFIED ASSUMPTION): three-shift C-tail attributes to previous day
            CASE
                WHEN TO_CHAR(weh.TRACKOUTTIMESTAMP, 'HH24:MI:SS') < '08:00:00'
                THEN TRUNC(weh.TRACKOUTTIMESTAMP) - 1
                ELSE TRUNC(weh.TRACKOUTTIMESTAMP)
            END
        ELSE
            -- PA-03: two-shift N-tail attributes to previous day
            CASE
                WHEN TO_CHAR(weh.TRACKOUTTIMESTAMP, 'HH24:MI:SS') < '07:30:00'
                THEN TRUNC(weh.TRACKOUTTIMESTAMP) - 1
                ELSE TRUNC(weh.TRACKOUTTIMESTAMP)
            END
    END AS OUTPUT_DATE,
    weh.SPECNAME AS SPECNAME,
    weh.PACKAGE_LF AS PACKAGE_LF,
    SUM(weh.TRACKOUTQTY) AS ACTUAL_OUTPUT_QTY
FROM DWH.DW_MES_LOTWIPHISTORY weh
LEFT JOIN workflow_info wb ON weh.CONTAINERID = wb.CONTAINERID
WHERE weh.TRACKOUTTIMESTAMP >= TO_TIMESTAMP(:start_date,     'YYYY-MM-DD')
  AND weh.TRACKOUTTIMESTAMP <  TO_TIMESTAMP(:chunk_end_excl, 'YYYY-MM-DD HH24:MI:SS')
  {{ CONTAINERNAME_FILTER }}
  AND (
    (CASE WHEN (wb.WORKFLOWNAME LIKE '%雙晶%' OR wb.WORKFLOWNAME LIKE '%三晶%') THEN 1 ELSE 0 END = 0
     AND weh.SPECNAME IN ('Epoxy D/B','Eutectic D/B','Solder Paste D/B','Solder D/B+E-Clip+固化','Solder D/B+E-Clip+固化-DW','Solder Paste D/B+E-Clip','Solder Paste D/B+E-Clip-DW'))
    OR weh.SPECNAME IN ('金線製程','銀線製程','銅線製程','手工跳線','雷射焊接','Eutectic D/B+Ag Wire','Eutectic D/B+Au Wire','Eutectic D/B+Cu Wire','E-Clip+固化','包膠-WB')
    OR (weh.SPECNAME IN ('2DB2WB','1DB2WB') AND weh.processtypename IN ('DWB_WB2'))
    OR (weh.SPECNAME IN ('2DB1WB','1DB1WB') AND weh.processtypename IN ('DWB_WB'))
    OR (wb.WORKFLOWNAME LIKE '%雙晶%' AND weh.SPECNAME IN ('Epoxy D/B-2','Eutectic D/B-2','Eutectic D/B-雙晶'))
    OR (wb.WORKFLOWNAME LIKE '%三晶%' AND weh.SPECNAME IN ('Epoxy D/B-3','Eutectic D/B-3'))
    OR (weh.SPECNAME IN ('2DB') AND weh.processtypename IN ('2DB_DB2'))
    OR (weh.SPECNAME IN ('1DB') AND weh.processtypename IN ('2DB_DB'))
    OR (weh.SPECNAME IN ('DBCB') AND weh.processtypename IN ('DBCB_CB'))
    OR (weh.SPECNAME IN ('2DBCBRO','1DBCBRO','CBRO') AND weh.processtypename IN ('CBA_RO'))
  )
GROUP BY
    CASE
        WHEN weh.TRACKOUTTIMESTAMP IS NULL THEN NULL
        WHEN TO_CHAR(weh.TRACKOUTTIMESTAMP, 'YYYYMMDD') > '20191231'
             AND TO_CHAR(weh.TRACKOUTTIMESTAMP, 'YYYYMMDD') < '20200330'
        THEN
            CASE
                WHEN TO_CHAR(weh.TRACKOUTTIMESTAMP, 'HH24:MI:SS') BETWEEN '08:00:00' AND '15:59:59' THEN 'A'
                WHEN TO_CHAR(weh.TRACKOUTTIMESTAMP, 'HH24:MI:SS') BETWEEN '16:00:00' AND '23:59:59' THEN 'B'
                ELSE 'C'
            END
        ELSE
            CASE
                WHEN TO_CHAR(weh.TRACKOUTTIMESTAMP, 'HH24:MI:SS') BETWEEN '07:30:00' AND '19:29:59' THEN 'D'
                ELSE 'N'
            END
    END,
    CASE
        WHEN weh.TRACKOUTTIMESTAMP IS NULL THEN NULL
        WHEN TO_CHAR(weh.TRACKOUTTIMESTAMP, 'YYYYMMDD') > '20191231'
             AND TO_CHAR(weh.TRACKOUTTIMESTAMP, 'YYYYMMDD') < '20200330'
        THEN
            CASE
                WHEN TO_CHAR(weh.TRACKOUTTIMESTAMP, 'HH24:MI:SS') < '08:00:00'
                THEN TRUNC(weh.TRACKOUTTIMESTAMP) - 1
                ELSE TRUNC(weh.TRACKOUTTIMESTAMP)
            END
        ELSE
            CASE
                WHEN TO_CHAR(weh.TRACKOUTTIMESTAMP, 'HH24:MI:SS') < '07:30:00'
                THEN TRUNC(weh.TRACKOUTTIMESTAMP) - 1
                ELSE TRUNC(weh.TRACKOUTTIMESTAMP)
            END
    END,
    weh.SPECNAME,
    weh.PACKAGE_LF
