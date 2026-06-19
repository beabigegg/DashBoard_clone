-- bridge_join.sql
-- DuckDB time-overlap bridge JOIN (DA-03, ADR-0010).
--
-- Implements the JOBID bridge that replaces _bridge_jobid() Path B pd.merge
-- in downtime_analysis_service.py.
--
-- Inputs (registered by DowntimeJob.post_aggregate before executing this SQL):
--   base_events_merged  — output of cross_shift_merge.sql; columns:
--                          HISTORYID, OLDSTATUSNAME, OLDREASONNAME,
--                          event_start, event_end, hours, fragment_count, JOBID
--   job_raw             — Oracle DW_MES_JOB + JOBTXNHISTORY fetch; columns:
--                          JOBID, RESOURCEID, CREATEDATE, COMPLETEDATE,
--                          SYMPTOMCODENAME, CAUSECODENAME, REPAIRCODENAME,
--                          COMPLETE_FULLNAME, FIRSTCLOCKONDATE, LASTCLOCKOFFDATE,
--                          JOBORDERNAME, JOBMODELNAME,
--                          ASSIGNED_DATE, ACK_DATE, INSPECT_START, INSPECT_END
--
-- ADR-0010: Uses RANGE JOIN + window function, NOT ASOF JOIN.
-- ASOF JOIN cannot express the two-sided interval overlap predicate, the
-- overlap-seconds ranking, or the 80% runner-up ambiguity test — substituting
-- it here would silently regress winner-selection and match_ambiguous.
--
-- Output columns (§3.21 of data-shape-contract.md enriched spool schema):
--   All columns from base_events_merged, plus:
--   match_source, match_ambiguous, JOBORDERNAME, JOBMODELNAME,
--   SYMPTOMCODENAME, CAUSECODENAME, REPAIRCODENAME, COMPLETE_FULLNAME,
--   FIRSTCLOCKONDATE, LASTCLOCKOFFDATE, CREATEDATE, COMPLETEDATE,
--   ASSIGNED_DATE, ACK_DATE, INSPECT_START, INSPECT_END
--
-- NOTE: _enrich_events_df() in the Python layer then adds category, event_id,
-- renames resource_id/status/reason, and produces the final 18-column spool.

WITH
-- ── Job data with effective end date ──────────────────────────────────────────
jobs_eff AS (
    SELECT
        TRIM(CAST(JOBID      AS VARCHAR))      AS JOBID,
        TRIM(CAST(RESOURCEID AS VARCHAR))      AS RESOURCEID,
        TRY_CAST(CREATEDATE    AS TIMESTAMP)   AS CREATEDATE,
        TRY_CAST(COMPLETEDATE  AS TIMESTAMP)   AS COMPLETEDATE,
        TRY_CAST(FIRSTCLOCKONDATE  AS TIMESTAMP) AS FIRSTCLOCKONDATE,
        TRY_CAST(LASTCLOCKOFFDATE  AS TIMESTAMP) AS LASTCLOCKOFFDATE,
        COALESCE(
            TRY_CAST(COMPLETEDATE AS TIMESTAMP),
            TRY_CAST(LASTCLOCKOFFDATE AS TIMESTAMP)
        )                                      AS eff_end,
        TRIM(CAST(JOBORDERNAME    AS VARCHAR)) AS JOBORDERNAME,
        TRIM(CAST(JOBMODELNAME    AS VARCHAR)) AS JOBMODELNAME,
        TRIM(CAST(SYMPTOMCODENAME AS VARCHAR)) AS SYMPTOMCODENAME,
        TRIM(CAST(CAUSECODENAME   AS VARCHAR)) AS CAUSECODENAME,
        TRIM(CAST(REPAIRCODENAME  AS VARCHAR)) AS REPAIRCODENAME,
        TRIM(CAST(COMPLETE_FULLNAME AS VARCHAR)) AS COMPLETE_FULLNAME,
        TRY_CAST(ASSIGNED_DATE  AS TIMESTAMP) AS ASSIGNED_DATE,
        TRY_CAST(ACK_DATE       AS TIMESTAMP) AS ACK_DATE,
        TRY_CAST(INSPECT_START  AS TIMESTAMP) AS INSPECT_START,
        TRY_CAST(INSPECT_END    AS TIMESTAMP) AS INSPECT_END
    FROM job_raw
    WHERE JOBID IS NOT NULL
      AND RESOURCEID IS NOT NULL
),

-- ── Normalize events ──────────────────────────────────────────────────────────
events AS (
    SELECT
        TRIM(CAST(HISTORYID AS VARCHAR))      AS HISTORYID,
        OLDSTATUSNAME,
        OLDREASONNAME,
        TRY_CAST(event_start AS TIMESTAMP)   AS event_start,
        TRY_CAST(event_end   AS TIMESTAMP)   AS event_end,
        hours,
        fragment_count,
        NULLIF(TRIM(CAST(COALESCE(CAST(JOBID AS VARCHAR), '') AS VARCHAR)), '') AS JOBID
    FROM base_events_merged
),

-- ── Build a stable event_id composite key ────────────────────────────────────
events_with_id AS (
    SELECT
        *,
        HISTORYID || '|' || OLDSTATUSNAME || '|'
            || COALESCE(OLDREASONNAME, '') || '|'
            || strftime(event_start, '%Y-%m-%dT%H:%M:%S') AS event_id
    FROM events
),

-- ── Path A: JOBID direct match ────────────────────────────────────────────────
-- Events where JOBID is present AND found in job_raw.
path_a_raw AS (
    SELECT
        e.event_id,
        e.HISTORYID,
        e.OLDSTATUSNAME,
        e.OLDREASONNAME,
        e.event_start,
        e.event_end,
        e.hours,
        e.fragment_count,
        e.JOBID              AS src_JOBID,
        'jobid'              AS match_source,
        FALSE                AS match_ambiguous,
        j.JOBID              AS JOBID,
        j.JOBORDERNAME,
        j.JOBMODELNAME,
        j.SYMPTOMCODENAME,
        j.CAUSECODENAME,
        j.REPAIRCODENAME,
        j.COMPLETE_FULLNAME,
        j.FIRSTCLOCKONDATE,
        j.LASTCLOCKOFFDATE,
        j.CREATEDATE,
        j.COMPLETEDATE,
        j.ASSIGNED_DATE,
        j.ACK_DATE,
        j.INSPECT_START,
        j.INSPECT_END
    FROM events_with_id e
    INNER JOIN (
        SELECT DISTINCT ON (JOBID) *
        FROM jobs_eff
        ORDER BY JOBID, CREATEDATE ASC
    ) j ON j.JOBID = e.JOBID
    WHERE e.JOBID IS NOT NULL
),

-- ── Detect true orphans (have JOBID but no match in jobs) ────────────────────
path_a_jobids AS (
    SELECT DISTINCT src_JOBID FROM path_a_raw
),

orphan_events AS (
    SELECT e.*
    FROM events_with_id e
    WHERE e.JOBID IS NOT NULL
      AND e.JOBID NOT IN (SELECT src_JOBID FROM path_a_jobids)
),

-- ── Path B events: no JOBID (need overlap join) ───────────────────────────────
path_b_events AS (
    SELECT *
    FROM events_with_id
    WHERE JOBID IS NULL
),

-- ── Path B: time-overlap candidates (RANGE JOIN — ADR-0010) ──────────────────
-- JOIN predicate: HISTORYID = RESOURCEID AND eff_end > event_start AND CREATEDATE < event_end
-- This is a two-sided inequality (interval overlap); ASOF JOIN cannot express this.
path_b_candidates AS (
    SELECT
        e.event_id,
        e.HISTORYID,
        e.OLDSTATUSNAME,
        e.OLDREASONNAME,
        e.event_start,
        e.event_end,
        e.hours,
        e.fragment_count,
        j.JOBID,
        j.CREATEDATE,
        j.eff_end,
        j.JOBORDERNAME,
        j.JOBMODELNAME,
        j.SYMPTOMCODENAME,
        j.CAUSECODENAME,
        j.REPAIRCODENAME,
        j.COMPLETE_FULLNAME,
        j.FIRSTCLOCKONDATE,
        j.LASTCLOCKOFFDATE,
        j.COMPLETEDATE,
        j.ASSIGNED_DATE,
        j.ACK_DATE,
        j.INSPECT_START,
        j.INSPECT_END,
        -- Overlap seconds: LEAST(event_end, eff_end) - GREATEST(event_start, CREATEDATE)
        epoch(
            LEAST(e.event_end, j.eff_end) - GREATEST(e.event_start, j.CREATEDATE)
        ) AS overlap_s
    FROM path_b_events e
    JOIN jobs_eff j
      ON j.RESOURCEID = e.HISTORYID
     AND j.eff_end    > e.event_start
     AND j.CREATEDATE < e.event_end
    WHERE j.eff_end IS NOT NULL
),

-- ── Winner selection: rank by overlap_s DESC, CREATEDATE ASC, JOBID ASC ──────
path_b_ranked AS (
    SELECT
        *,
        ROW_NUMBER() OVER (
            PARTITION BY event_id
            ORDER BY overlap_s DESC, CREATEDATE ASC, JOBID ASC
        ) AS rn,
        LEAD(overlap_s) OVER (
            PARTITION BY event_id
            ORDER BY overlap_s DESC, CREATEDATE ASC, JOBID ASC
        ) AS runner_up_overlap_s
    FROM path_b_candidates
),

-- ── Path B winners with ambiguity flag ────────────────────────────────────────
path_b_winners AS (
    SELECT
        event_id,
        HISTORYID,
        OLDSTATUSNAME,
        OLDREASONNAME,
        event_start,
        event_end,
        hours,
        fragment_count,
        NULL       AS src_JOBID,
        'overlap'  AS match_source,
        -- match_ambiguous = TRUE when runner-up overlap >= 80% of winner overlap
        CASE WHEN runner_up_overlap_s IS NOT NULL
              AND overlap_s > 0
              AND runner_up_overlap_s >= 0.8 * overlap_s
        THEN TRUE ELSE FALSE END AS match_ambiguous,
        JOBID,
        JOBORDERNAME,
        JOBMODELNAME,
        SYMPTOMCODENAME,
        CAUSECODENAME,
        REPAIRCODENAME,
        COMPLETE_FULLNAME,
        FIRSTCLOCKONDATE,
        LASTCLOCKOFFDATE,
        CREATEDATE,
        COMPLETEDATE,
        ASSIGNED_DATE,
        ACK_DATE,
        INSPECT_START,
        INSPECT_END
    FROM path_b_ranked
    WHERE rn = 1
),

-- ── Path B: events with no overlapping job (orphans from Path B) ─────────────
path_b_matched_ids AS (
    SELECT DISTINCT event_id FROM path_b_winners
),

path_b_no_match AS (
    SELECT
        e.event_id,
        e.HISTORYID,
        e.OLDSTATUSNAME,
        e.OLDREASONNAME,
        e.event_start,
        e.event_end,
        e.hours,
        e.fragment_count,
        NULL AS src_JOBID,
        'none' AS match_source,
        FALSE  AS match_ambiguous,
        NULL   AS JOBID,
        NULL   AS JOBORDERNAME,
        NULL   AS JOBMODELNAME,
        NULL   AS SYMPTOMCODENAME,
        NULL   AS CAUSECODENAME,
        NULL   AS REPAIRCODENAME,
        NULL   AS COMPLETE_FULLNAME,
        NULL   AS FIRSTCLOCKONDATE,
        NULL   AS LASTCLOCKOFFDATE,
        NULL   AS CREATEDATE,
        NULL   AS COMPLETEDATE,
        NULL   AS ASSIGNED_DATE,
        NULL   AS ACK_DATE,
        NULL   AS INSPECT_START,
        NULL   AS INSPECT_END
    FROM path_b_events e
    WHERE e.event_id NOT IN (SELECT event_id FROM path_b_matched_ids)
),

-- ── Orphan events (Path A lookup miss) ────────────────────────────────────────
path_orphan AS (
    SELECT
        event_id,
        HISTORYID,
        OLDSTATUSNAME,
        OLDREASONNAME,
        event_start,
        event_end,
        hours,
        fragment_count,
        JOBID  AS src_JOBID,
        'none' AS match_source,
        FALSE  AS match_ambiguous,
        NULL   AS JOBID,
        NULL   AS JOBORDERNAME,
        NULL   AS JOBMODELNAME,
        NULL   AS SYMPTOMCODENAME,
        NULL   AS CAUSECODENAME,
        NULL   AS REPAIRCODENAME,
        NULL   AS COMPLETE_FULLNAME,
        NULL   AS FIRSTCLOCKONDATE,
        NULL   AS LASTCLOCKOFFDATE,
        NULL   AS CREATEDATE,
        NULL   AS COMPLETEDATE,
        NULL   AS ASSIGNED_DATE,
        NULL   AS ACK_DATE,
        NULL   AS INSPECT_START,
        NULL   AS INSPECT_END
    FROM orphan_events
)

-- ── UNION all paths ───────────────────────────────────────────────────────────
SELECT
    event_id,
    HISTORYID,
    OLDSTATUSNAME,
    OLDREASONNAME,
    event_start,
    event_end,
    hours,
    fragment_count,
    match_source,
    match_ambiguous,
    JOBID,
    JOBORDERNAME,
    JOBMODELNAME,
    SYMPTOMCODENAME,
    CAUSECODENAME,
    REPAIRCODENAME,
    COMPLETE_FULLNAME,
    FIRSTCLOCKONDATE,
    LASTCLOCKOFFDATE,
    CREATEDATE,
    COMPLETEDATE,
    ASSIGNED_DATE,
    ACK_DATE,
    INSPECT_START,
    INSPECT_END
FROM path_a_raw
UNION ALL
SELECT
    event_id,
    HISTORYID,
    OLDSTATUSNAME,
    OLDREASONNAME,
    event_start,
    event_end,
    hours,
    fragment_count,
    match_source,
    match_ambiguous,
    JOBID,
    JOBORDERNAME,
    JOBMODELNAME,
    SYMPTOMCODENAME,
    CAUSECODENAME,
    REPAIRCODENAME,
    COMPLETE_FULLNAME,
    FIRSTCLOCKONDATE,
    LASTCLOCKOFFDATE,
    CREATEDATE,
    COMPLETEDATE,
    ASSIGNED_DATE,
    ACK_DATE,
    INSPECT_START,
    INSPECT_END
FROM path_b_winners
UNION ALL
SELECT
    event_id,
    HISTORYID,
    OLDSTATUSNAME,
    OLDREASONNAME,
    event_start,
    event_end,
    hours,
    fragment_count,
    match_source,
    match_ambiguous,
    JOBID,
    JOBORDERNAME,
    JOBMODELNAME,
    SYMPTOMCODENAME,
    CAUSECODENAME,
    REPAIRCODENAME,
    COMPLETE_FULLNAME,
    FIRSTCLOCKONDATE,
    LASTCLOCKOFFDATE,
    CREATEDATE,
    COMPLETEDATE,
    ASSIGNED_DATE,
    ACK_DATE,
    INSPECT_START,
    INSPECT_END
FROM path_b_no_match
UNION ALL
SELECT
    event_id,
    HISTORYID,
    OLDSTATUSNAME,
    OLDREASONNAME,
    event_start,
    event_end,
    hours,
    fragment_count,
    match_source,
    match_ambiguous,
    JOBID,
    JOBORDERNAME,
    JOBMODELNAME,
    SYMPTOMCODENAME,
    CAUSECODENAME,
    REPAIRCODENAME,
    COMPLETE_FULLNAME,
    FIRSTCLOCKONDATE,
    LASTCLOCKOFFDATE,
    CREATEDATE,
    COMPLETEDATE,
    ASSIGNED_DATE,
    ACK_DATE,
    INSPECT_START,
    INSPECT_END
FROM path_orphan
ORDER BY HISTORYID, event_start
