-- Job List Query
-- Retrieves maintenance jobs for selected resources within date range
-- Placeholders:
--   RESOURCE_FILTER - Resource ID filter condition (e.g., RESOURCEID IN (...))
-- Parameters:
--   :start_date - Start date (YYYY-MM-DD)
--   :end_date   - End date (YYYY-MM-DD)

SELECT
    j.JOBID,
    j.RESOURCEID,
    j.RESOURCENAME,
    j.JOBSTATUS,
    j.JOBMODELNAME,
    j.JOBORDERNAME,
    j.CREATEDATE,
    j.COMPLETEDATE,
    j.CANCELDATE,
    j.FIRSTCLOCKONDATE,
    j.LASTCLOCKOFFDATE,
    j.CAUSECODENAME,
    j.REPAIRCODENAME,
    j.SYMPTOMCODENAME,
    j.PJ_CAUSECODE2NAME,
    j.PJ_REPAIRCODE2NAME,
    j.PJ_SYMPTOMCODE2NAME,
    j.CREATE_EMPNAME,
    j.COMPLETE_EMPNAME
FROM DWH.DW_MES_JOB j
WHERE {{ RESOURCE_FILTER }}
  AND j.CREATEDATE >= TO_DATE(:start_date, 'YYYY-MM-DD')
  AND j.CREATEDATE < TO_DATE(:end_date, 'YYYY-MM-DD') + 1
ORDER BY j.RESOURCENAME, j.CREATEDATE DESC
