-- base_events.sql
-- Selects E10 downtime events from DWH.DW_MES_RESOURCESTATUS_SHIFT
-- Only UDT/SDT/EGT statuses (DA-01); NST excluded at query layer.
-- Parameters: :start_date, :end_date (plus optional :workcenter, :resource_id handled by service)

SELECT
    s.HISTORYID,
    s.OLDSTATUSNAME,
    TRIM(s.OLDREASONNAME) AS OLDREASONNAME,
    s.OLDLASTSTATUSCHANGEDATE,
    s.LASTSTATUSCHANGEDATE,
    CAST(s.HOURS AS FLOAT) AS HOURS,
    s.JOBID
FROM
    DWH.DW_MES_RESOURCESTATUS_SHIFT s
WHERE
    s.OLDSTATUSNAME IN ('UDT', 'SDT', 'EGT')
    AND s.OLDLASTSTATUSCHANGEDATE >= TO_DATE(:start_date, 'YYYY-MM-DD')
    AND s.OLDLASTSTATUSCHANGEDATE <  TO_DATE(:end_date,   'YYYY-MM-DD') + 1
ORDER BY
    s.OLDLASTSTATUSCHANGEDATE DESC,
    s.HISTORYID ASC
