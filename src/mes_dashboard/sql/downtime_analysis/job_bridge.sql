-- job_bridge.sql
-- Selects JOB records for the JOBID bridge (Path A and Path B overlap candidates).
-- Parameters: :start_date, :end_date (wide window to capture overlapping jobs)

SELECT
    j.JOBID,
    TRIM(j.RESOURCEID)           AS RESOURCEID,
    j.CREATEDATE,
    j.COMPLETEDATE,
    TRIM(j.SYMPTOMCODENAME)      AS SYMPTOMCODENAME,
    TRIM(j.CAUSECODENAME)        AS CAUSECODENAME,
    TRIM(j.REPAIRCODENAME)       AS REPAIRCODENAME,
    TRIM(j.COMPLETE_FULLNAME)    AS COMPLETE_FULLNAME,
    j.FIRSTCLOCKONDATE,
    j.LASTCLOCKOFFDATE,
    TRIM(j.JOBORDERNAME)         AS JOBORDERNAME,
    TRIM(j.JOBMODELNAME)         AS JOBMODELNAME
FROM
    DWH.DW_MES_JOB j
WHERE
    (
        j.COMPLETEDATE >= TO_DATE(:start_date, 'YYYY-MM-DD') - 7
        OR j.COMPLETEDATE IS NULL
    )
    AND j.CREATEDATE <= TO_DATE(:end_date, 'YYYY-MM-DD') + 7
