-- Job Transaction History Detail
-- Retrieves all transaction history for a single job
-- Parameters:
--   :job_id - The JOBID to query

SELECT
    h.JOBTXNHISTORYID,
    h.JOBID,
    h.TXNDATE,
    h.FROMJOBSTATUS,
    h.JOBSTATUS,
    h.STAGENAME,
    h.TOSTAGENAME,
    h.CAUSECODENAME,
    h.REPAIRCODENAME,
    h.SYMPTOMCODENAME,
    h.USER_EMPNO,
    h.USER_NAME,
    h.EMP_EMPNO,
    h.EMP_NAME,
    h.COMMENTS,
    h.CDONAME,
    h.JOBMODELNAME,
    h.JOBORDERNAME
FROM DWH.DW_MES_JOBTXNHISTORY h
WHERE h.JOBID = :job_id
ORDER BY h.TXNDATE ASC
