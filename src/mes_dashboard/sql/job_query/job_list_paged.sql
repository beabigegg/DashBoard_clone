-- Job List Paged Query (ROW_NUMBER() row-count chunking)
-- Used when USE_ROW_COUNT_CHUNKING=true.
-- Placeholders:
--   RESOURCE_FILTER - Resource ID filter condition
-- Parameters:
--   :start_date - Start date (YYYY-MM-DD)
--   :end_date   - End date (YYYY-MM-DD)
--   :start_row  - 1-based inclusive start (from decompose_by_row_count)
--   :end_row    - 1-based inclusive end
--
-- ORDER BY key (BQE-03): CREATEDATE DESC, JOBID ASC

WITH ranked AS (
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
        j.COMPLETE_EMPNAME,
        ROW_NUMBER() OVER (
            ORDER BY j.CREATEDATE DESC, j.JOBID ASC
        ) AS _rn
    FROM DWH.DW_MES_JOB j
    WHERE {{ RESOURCE_FILTER }}
      AND j.CREATEDATE >= TO_DATE(:start_date, 'YYYY-MM-DD')
      AND j.CREATEDATE < TO_DATE(:end_date, 'YYYY-MM-DD') + 1
)
SELECT
    JOBID,
    RESOURCEID,
    RESOURCENAME,
    JOBSTATUS,
    JOBMODELNAME,
    JOBORDERNAME,
    CREATEDATE,
    COMPLETEDATE,
    CANCELDATE,
    FIRSTCLOCKONDATE,
    LASTCLOCKOFFDATE,
    CAUSECODENAME,
    REPAIRCODENAME,
    SYMPTOMCODENAME,
    PJ_CAUSECODE2NAME,
    PJ_REPAIRCODE2NAME,
    PJ_SYMPTOMCODE2NAME,
    CREATE_EMPNAME,
    COMPLETE_EMPNAME
FROM ranked
WHERE _rn BETWEEN :start_row AND :end_row
