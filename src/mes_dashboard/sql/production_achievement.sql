-- Production Achievement Rate — Oracle read (production-achievement-kanban)
--
-- Groups PA-05-qualifying DW_MES_LOTWIPHISTORY trackout events by
-- (output_date, shift_code, SPECNAME). SPECNAME is the finest station
-- granularity available at the DB; workcenter_group (大站點/PACKAGE) is
-- resolved in Python via services/filter_cache.get_spec_workcenter_mapping()
-- (business-rules.md PA-06) — no SPECNAME->station mapping is done here,
-- keeping this query source-agnostic to that cache's contents.
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
--   :chunk_end_excl - YYYY-MM-DD (exclusive = user end_date + 1 day)
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

WITH workflow_info AS (
    SELECT CONTAINERID, WORKFLOWNAME
    FROM (
        SELECT
            w.CONTAINERID,
            w.WORKFLOWNAME,
            ROW_NUMBER() OVER (
                PARTITION BY w.CONTAINERID
                ORDER BY w.WORKFLOWNAME
            ) AS wf_rn
        FROM DWH.DW_MES_WIP w
    )
    WHERE wf_rn = 1
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
    SUM(weh.TRACKOUTQTY) AS ACTUAL_OUTPUT_QTY
FROM DWH.DW_MES_LOTWIPHISTORY weh
LEFT JOIN workflow_info wb ON weh.CONTAINERID = wb.CONTAINERID
WHERE weh.TRACKOUTTIMESTAMP >= TO_TIMESTAMP(:start_date,     'YYYY-MM-DD')
  AND weh.TRACKOUTTIMESTAMP <  TO_TIMESTAMP(:chunk_end_excl, 'YYYY-MM-DD')
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
    weh.SPECNAME
