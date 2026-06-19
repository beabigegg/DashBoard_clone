-- cross_shift_merge.sql
-- DuckDB cross-shift event merge (DA-02): 60-second gap walk.
--
-- This is the DuckDB SQL form of _merge_cross_shift_events() in
-- downtime_analysis_service.py.  It reads from a table named "base_raw"
-- (registered by DowntimeJob.post_aggregate before executing this SQL).
--
-- Algorithm:
--   Within each (HISTORYID, OLDSTATUSNAME, OLDREASONNAME) group, ordered by
--   OLDLASTSTATUSCHANGEDATE, start a new run when the gap between the
--   previous row's LASTSTATUSCHANGEDATE and the current OLDLASTSTATUSCHANGEDATE
--   exceeds {gap_seconds} seconds (or when the group key changes).
--   Merge fragments in the same run: SUM(HOURS), MIN(event_start), MAX(event_end).
--   JOBID: take the first non-null value in the run (FIRST() FILTER).
--
-- ADR-0010: This SQL is parameterized via Python str.format(); use {{...}} for
-- literal braces.  Only {gap_seconds} is a substitution point.
--
-- Output columns match the input expected by bridge_join.sql:
--   HISTORYID, OLDSTATUSNAME, OLDREASONNAME, event_start, event_end,
--   hours, fragment_count, JOBID

WITH sorted_events AS (
    SELECT
        *,
        COALESCE(TRY_CAST(HOURS AS DOUBLE), 0.0)        AS _hours_num,
        TRY_CAST(OLDLASTSTATUSCHANGEDATE AS TIMESTAMP)   AS _estart,
        TRY_CAST(LASTSTATUSCHANGEDATE    AS TIMESTAMP)   AS _eend,
        TRIM(CAST(HISTORYID      AS VARCHAR))             AS _h,
        TRIM(CAST(OLDSTATUSNAME  AS VARCHAR))             AS _s,
        COALESCE(NULLIF(TRIM(CAST(OLDREASONNAME AS VARCHAR)), ''), '') AS _r
    FROM base_raw
    ORDER BY
        TRIM(CAST(HISTORYID     AS VARCHAR)),
        TRIM(CAST(OLDSTATUSNAME AS VARCHAR)),
        COALESCE(NULLIF(TRIM(CAST(OLDREASONNAME AS VARCHAR)), ''), ''),
        TRY_CAST(OLDLASTSTATUSCHANGEDATE AS TIMESTAMP) NULLS LAST
),
numbered AS (
    SELECT *, ROW_NUMBER() OVER () AS _srn
    FROM sorted_events
),
lagged AS (
    SELECT *,
        LAG(_h)    OVER (ORDER BY _srn) AS _ph,
        LAG(_s)    OVER (ORDER BY _srn) AS _ps,
        LAG(_r)    OVER (ORDER BY _srn) AS _pr,
        LAG(_eend) OVER (ORDER BY _srn) AS _prev_end
    FROM numbered
),
breaks AS (
    SELECT *,
        CASE
            WHEN _ph IS NULL                                                 THEN 1
            WHEN _h  != _ph                                                  THEN 1
            WHEN _s  != _ps                                                  THEN 1
            WHEN _r  != COALESCE(_pr, '')                                    THEN 1
            WHEN _prev_end IS NULL                                           THEN 1
            WHEN datediff('second', _prev_end, _estart) > {gap_seconds}      THEN 1
            ELSE 0
        END AS _is_break
    FROM lagged
),
run_ids AS (
    SELECT *,
        SUM(_is_break) OVER (
            ORDER BY _srn
            ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
        ) AS _run_id
    FROM breaks
)
SELECT
    FIRST(_h)                                                                             AS HISTORYID,
    FIRST(_s)                                                                             AS OLDSTATUSNAME,
    FIRST(NULLIF(TRIM(CAST(OLDREASONNAME AS VARCHAR)), ''))
        FILTER (WHERE NULLIF(TRIM(CAST(OLDREASONNAME AS VARCHAR)), '') IS NOT NULL)       AS OLDREASONNAME,
    MIN(_estart)                                                                          AS event_start,
    MAX(_eend)                                                                            AS event_end,
    ROUND(SUM(_hours_num), 6)                                                             AS hours,
    COUNT(*)                                                                              AS fragment_count,
    FIRST(CAST(JOBID AS VARCHAR)) FILTER (WHERE JOBID IS NOT NULL)                        AS JOBID
FROM run_ids
GROUP BY _run_id
ORDER BY HISTORYID, event_start
