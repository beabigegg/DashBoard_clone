-- Production Achievement — known PACKAGE_LF values (production-achievement-overhaul)
--
-- Returns the distinct set of raw PACKAGE_LF values Oracle has emitted over
-- a ~13-month rolling window (hardcoded constant -- NOT an env var, per
-- implementation-plan.md IP-3). Backs services/filter_cache.py's
-- `package_lf_values` cache key, surfaced via
-- GET /api/production-achievement/known-package-lf-values so
-- PackageLfMappingPanel.vue (frontend/src/production-achievement-settings/)
-- can show admins the full universe of raw values that MAY need a merge-map
-- entry (mirrors GET /known-workcenter-groups' OD-8 purpose for D2).
--
-- Deliberately NOT scoped by the PA-05 effective-output predicate (unlike
-- sql/production_achievement.sql): this is a lightweight "what raw strings
-- has Oracle emitted recently" admin-UI lookup, not a report-accuracy
-- computation, so it avoids re-deriving PA-05's WORKFLOWNAME-dependent join.
--
-- No bind parameters -- the rolling window is computed relative to SYSDATE
-- inside the query itself.

SELECT DISTINCT PACKAGE_LF
FROM DWH.DW_MES_LOTWIPHISTORY
WHERE PACKAGE_LF IS NOT NULL
  AND TRACKOUTTIMESTAMP >= ADD_MONTHS(TRUNC(SYSDATE), -13)
ORDER BY PACKAGE_LF
