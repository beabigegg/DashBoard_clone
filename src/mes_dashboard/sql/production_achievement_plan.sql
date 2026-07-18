-- Production Achievement Rate -- Oracle plan/target source
-- (production-achievement-oracle-plan-source, business-rules.md PA-11/PA-20/PA-21)
--
-- Replaces the Excel-imported production_achievement_daily_plans MySQL table.
-- Confirmed with IT (repo-root PROD_ACH.txt reference SQL) that
-- DWH.MES_WIP_OUTPUTPLAN / DWH.MES_WIP_OUTPUTPLAN_DETAIL are the authoritative
-- Oracle source for daily production targets, keyed on Package Group only --
-- there is NO workcenter/station dimension in the source data itself (the
-- same target broadcasts to every station for that package, exactly as
-- 025.txt's legacy PJMES025 report applies one PLANQTY_DAY/DAY2 value across
-- every WorkCenterXXD/N column). Station-level Input/Output routing and the
-- per-shift derivation are both done CLIENT-SIDE
-- (useProductionAchievementDuckDB.ts), not here.
--
-- Unlike PROD_ACH.txt's original shape (single query-day + single calendar-
-- month-to-date aggregate, 4 columns), this ships RAW PER-DAY rows for the
-- whole month -- consistent with this feature's existing architecture where
-- the server ships fine-grained rows and DuckDB-WASM does all rollup
-- (ADR-0016). This also makes arbitrary custom date-range queries correct by
-- construction (client sums whatever [start_date, end_date] the report
-- request covers) instead of only supporting IT's original two fixed windows.
--
-- MES_WIP_OUTPUTPLAN.PACKAGEGROUP is (despite the column name) a RAW package
-- code in this table -- it must be joined through
-- MES_WIP_OUTPUTPLAN_DETAIL.PACKAGE to resolve the reporting group name.
-- PACKAGE_REPORT column choice (NOT OPD.PACKAGEGROUP -- easy to confuse with
-- OP.PACKAGEGROUP above, a completely different column on a different
-- table): OPD has THREE columns -- PACKAGE (raw), PACKAGEGROUP (a coarser
-- internal planning grouping), and PACKAGE_REPORT (the actual merged Package
-- Group name used in reports). Confirmed via ALL_TAB_COLUMNS + real-data
-- sampling against the dev DB that PACKAGEGROUP and PACKAGE_REPORT DIVERGE
-- for several raw codes -- e.g. PACKAGE='SOT-23 CU' has PACKAGEGROUP='SOT-23'
-- (would silently merge it into SOT-23) but PACKAGE_REPORT='SOT-23 CU'
-- (correctly its own report group); same divergence for SOT-353/SOT-363/
-- SOT-363 CU (all share PACKAGEGROUP='SOT-363/353' but each is its own
-- PACKAGE_REPORT group). Using PACKAGEGROUP here was a genuine bug in an
-- earlier revision of this query, caught by user review; PACKAGE_REPORT is
-- the correct column and is what this query and
-- production_achievement_package_lf_oracle.sql both use now. Verified there
-- is no fan-out risk from this column choice: no (TMONTH, DAYSN,
-- PACKAGE_REPORT) combination across a 3-month real-data sample had more
-- than one distinct OP.PACKAGEGROUP (raw) row, so MAX() on the client join
-- (useProductionAchievementDuckDB.ts) still sees at most one target row.
--
-- INNER JOIN (not LEFT) matches PROD_ACH.txt's own join -- OPD is the only
-- source of the merged group name, so a row with no OPD match has no
-- resolvable Package Group to key on regardless of join type. KNOWN Oracle-
-- side data gap (not fixable here -- OUTPUTPLAN_DETAIL is IT-owned reference
-- data): OUTPUTPLAN.PACKAGEGROUP='DFN1006-2L/3L' has no matching OPD.PACKAGE
-- row as of 2026-07, so that package's plan silently has no target -- same
-- behavior as IT's own PROD_ACH.txt query, not a regression introduced here.
--
-- DAYSN <> 0 filter kept from PROD_ACH.txt even though no live DAYSN=0 rows
-- were observed (defensive parity with IT's own query). DAYSN <= last-day-of-
-- month filter is NOT defensive -- confirmed via real data that OUTPUTPLAN
-- carries a DAYSN=31 row even for 30-day months (e.g. TMONTH='202606'), which
-- would otherwise produce a bogus TO_DATE for e.g. 2026-06-31.
--
-- Parameters (bound via oracledb named params):
--   :tmonth -- 'YYYYMM' string. Callers (production_achievement_plan_service.py)
--             issue one query per calendar month covered by the report's
--             [start_date, end_date] range and cache per month.

SELECT
    OPD.PACKAGE_REPORT AS PLAN_PACKAGE_GROUP,
    TO_DATE(OP.TMONTH || LPAD(TO_CHAR(OP.DAYSN), 2, '0'), 'YYYYMMDD') AS OUTPUT_DATE,
    OP.PLANQTY_INPUT  AS PLANQTY_INPUT,
    OP.PLANQTY_OUTPUT AS PLANQTY_OUTPUT
FROM DWH.MES_WIP_OUTPUTPLAN OP
JOIN DWH.MES_WIP_OUTPUTPLAN_DETAIL OPD ON OP.PACKAGEGROUP = OPD.PACKAGE
WHERE OP.TMONTH = :tmonth
  AND OP.DAYSN <> 0
  AND OP.DAYSN <= TO_NUMBER(TO_CHAR(LAST_DAY(TO_DATE(OP.TMONTH, 'YYYYMM')), 'DD'))
ORDER BY OUTPUT_DATE, PLAN_PACKAGE_GROUP
