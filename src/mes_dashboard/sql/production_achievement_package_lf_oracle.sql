-- Production Achievement Rate -- Oracle-sourced D1 default map
-- (production-achievement-oracle-plan-source, business-rules.md PA-09)
--
-- Full, un-joined MES_WIP_OUTPUTPLAN_DETAIL reference table (46 rows as of
-- 2026-07): PACKAGE (raw code) -> PACKAGE_REPORT (the merged Package Group
-- name actually used in reports). This table ALSO has a PACKAGEGROUP column
-- -- do NOT use it here, it is a DIFFERENT (coarser) internal planning
-- grouping, confirmed via live-data cross-check to disagree with
-- PACKAGE_REPORT for several raw codes (e.g. PACKAGE='SOT-23 CU' ->
-- PACKAGEGROUP='SOT-23' [merged] but PACKAGE_REPORT='SOT-23 CU' [stays its
-- own group]; same divergence for SOT-353/SOT-363/SOT-363 CU, each its own
-- PACKAGE_REPORT group despite sharing PACKAGEGROUP='SOT-363/353']).
-- This is the SAME table production_achievement_plan.sql joins against, but
-- that query only surfaces PACKAGE_REPORT values for PACKAGE codes that have
-- a live MES_WIP_OUTPUTPLAN row in a specific queried month -- this query
-- has no OP join and no month filter, so it returns the complete reference
-- table regardless of what any report is currently querying.
--
-- Used by production_achievement_package_lf_service.get_oracle_package_lf_map()
-- to auto-populate D1's default merge mapping; manually-maintained D1 rows in
-- production_achievement_package_lf_map still take priority over these
-- Oracle defaults (sparse exceptions-only override layer, PA-09), needed for
-- the confirmed Oracle-side gap (OUTPUTPLAN.PACKAGEGROUP='DFN1006-2L/3L' has
-- no matching OPD.PACKAGE row, see production_achievement_plan.sql) and any
-- future case where the desired reporting grouping diverges from Oracle's.
--
-- No bind parameters -- this is a static reference table, not date-scoped.

SELECT
    PACKAGE        AS RAW_PACKAGE_LF,
    PACKAGE_REPORT AS ORACLE_MERGED_GROUP
FROM DWH.MES_WIP_OUTPUTPLAN_DETAIL
ORDER BY PACKAGE
