-- job_bridge.sql
-- Selects JOB records for the JOBID bridge (Path A and Path B overlap candidates).
-- Parameters: :start_date, :end_date (wide window to capture overlapping jobs)
--
-- CTE job_base materialises the filtered JOBID set first; the txn subquery then
-- restricts JOBTXNHISTORY to only those JOBIDs via IN (...) so Oracle can use the
-- JOBID index rather than scanning the full history table.

WITH job_base AS (
    SELECT
        JOBID,
        TRIM(RESOURCEID)           AS RESOURCEID,
        CREATEDATE,
        COMPLETEDATE,
        TRIM(SYMPTOMCODENAME)      AS SYMPTOMCODENAME,
        TRIM(CAUSECODENAME)        AS CAUSECODENAME,
        TRIM(REPAIRCODENAME)       AS REPAIRCODENAME,
        TRIM(COMPLETE_FULLNAME)    AS COMPLETE_FULLNAME,
        FIRSTCLOCKONDATE,
        LASTCLOCKOFFDATE,
        TRIM(JOBORDERNAME)         AS JOBORDERNAME,
        TRIM(JOBMODELNAME)         AS JOBMODELNAME
    FROM DWH.DW_MES_JOB
    WHERE {{ RESOURCE_FILTER }}
      AND (
          COMPLETEDATE >= TO_DATE(:start_date, 'YYYY-MM-DD') - 7
          OR COMPLETEDATE IS NULL
      )
      AND CREATEDATE <= TO_DATE(:end_date, 'YYYY-MM-DD') + 7
)
SELECT
    jb.JOBID,
    jb.RESOURCEID,
    jb.CREATEDATE,
    jb.COMPLETEDATE,
    jb.SYMPTOMCODENAME,
    jb.CAUSECODENAME,
    jb.REPAIRCODENAME,
    jb.COMPLETE_FULLNAME,
    jb.FIRSTCLOCKONDATE,
    jb.LASTCLOCKOFFDATE,
    jb.JOBORDERNAME,
    jb.JOBMODELNAME,
    txn.ASSIGNED_DATE,
    txn.ACK_DATE,
    txn.INSPECT_START,
    txn.INSPECT_END
FROM job_base jb
LEFT JOIN (
    SELECT
        t.JOBID,
        MIN(CASE WHEN t.JOBSTATUS = 'ASSIGNED'     THEN t.TXNDATE END) AS ASSIGNED_DATE,
        MIN(CASE WHEN t.JOBSTATUS = 'ACKNOWLEDGED' THEN t.TXNDATE END) AS ACK_DATE,
        MIN(CASE WHEN t.STAGENAME IN (
                'QC-產品檢驗', 'PD-產品檢驗',
                'QC_驗機', 'EE_驗機', 'PD_驗機', 'PE_驗機'
            ) THEN t.TXNDATE END)                                       AS INSPECT_START,
        MAX(CASE WHEN t.STAGENAME IN (
                'QC-產品檢驗', 'PD-產品檢驗',
                'QC_驗機', 'EE_驗機', 'PD_驗機', 'PE_驗機'
            ) THEN t.TXNDATE END)                                       AS INSPECT_END
    FROM DWH.DW_MES_JOBTXNHISTORY t
    WHERE t.JOBID IN (SELECT JOBID FROM job_base)
    GROUP BY t.JOBID
) txn ON txn.JOBID = jb.JOBID
