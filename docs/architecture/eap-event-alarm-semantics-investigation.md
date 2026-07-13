# Investigation: `DWH.EAP_EVENT` alarm semantics (`EVENT_TYPE` vs `EVENT_NAME`)

**Status:** Implemented by change `eap-event-alarm-semantics` (2026-07-07) — see ADR-0015 and business rule EA-EVT. Scope: `AlarmDetected`/`AlarmCleared` included with `EVENT_NAME`-based pairing keyed on `AlarmID`; `ProcessAlarm` and `AlarmNeedCountIntoStatistics(MTBA/MTBF)` remain excluded per Finding 3. Follow-up dual-channel overlap measurement (GDBA, 2-day window, same-day): **70.43%** of Shape B `AlarmDetected` (2079/2952) had a Shape A counterpart within ±60s → cross-channel dedup shipped in the same change (Shape B occurrence dropped when a Shape A occurrence matches on `(EQP_ID, ALARM_ID)` within ±60s; Shape A wins). Text-EVENT_NAME families (GWBA-style) remain unmeasured/un-deduped — see ADR-0015 §Consequences.

**Date:** 2026-07-07

**See also:** `docs/architecture/eap-event-uph-collection-investigation.md` —
sibling investigation of UPH / throughput data in the same tables (the
non-alarm `EQP_SECS_EVENT` / periodic `M[60]`/`M[30]` events this doc's Shape-B
analysis brushes past).

## Trigger

While reviewing EAP ALARM data, it was observed that "alarm" information is not
consistently located in a single column of `DWH.EAP_EVENT`: some rows carry
alarm identity in `EVENT_TYPE`-adjacent context, others in `EVENT_NAME`. This
doc records a direct Oracle investigation (read-only, `DB_USER=MBU1_R`) to
characterize the actual shape of the data, bounded to a recent 2-day
`LAST_UPDATE_TIME` window to stay index-safe on this ~385K-rows/day table (per
`docs/adr/0008-eap-alarm-coarse-spool-detail-join.md`). A later attempt to
widen the window to 14 days for a stability check made the query run far past
the app's own `DB_CALL_TIMEOUT_MS` (55s) with no result after 20+ minutes and
was aborted — any follow-up querying against this table must stay within a
narrow `LAST_UPDATE_TIME` bound and avoid correlated per-row subqueries.

## Finding 1: two independent, coexisting alarm-reporting shapes

**Shape A — the shape `eap_alarm_worker.py` currently queries:**

```sql
EVENT_TYPE = 'EQP_SECS_ALARM'   -- fixed category value
EVENT_NAME = <alarm identity>   -- see Finding 2, this is itself inconsistent
```

Resolved further via `EAP_EVENT_DETAIL` EAV rows keyed by `SEQ_ID`
(`AlarmCode` / `AlarmText` / `AlarmCategory`). This is the only shape
`_EAP_EVENT_SQL_TEMPLATE` / `_DETAIL_SQL_TEMPLATE` in
`src/mes_dashboard/workers/eap_alarm_worker.py` selects
(`AND e.EVENT_TYPE = 'EQP_SECS_ALARM'`).

**Shape B — NOT captured by the current worker at all:**

```sql
EVENT_TYPE = 'EQP_SECS_EVENT'   -- same category as ordinary process/track events
EVENT_NAME IN ('AlarmDetected', 'AlarmCleared', 'ProcessAlarm',
               'AlarmNeedCountIntoStatistics(MTBA/MTBF)')
```

Here the alarm semantics live entirely in `EVENT_NAME`, while `EVENT_TYPE`
is the generic "this is a SECS event" bucket shared with thousands of
non-alarm process events. A query that filters
`EVENT_TYPE = 'EQP_SECS_ALARM'` silently skips all of Shape B.

2-day sample volumes (single run, `SYSDATE - 2`; re-running shows minor
variance since this is live production data, not a snapshot):

| EVENT_NAME | rows / 2 days |
|---|---|
| `AlarmDetected` | ~8,100–8,450 |
| `AlarmCleared` | ~6,100–6,550 |
| `ProcessAlarm` | ~2,050–2,110 |
| `AlarmNeedCountIntoStatistics(MTBA/MTBF)` | ~1,870–1,900 |

Combined ≈ 18–19K rows / 2 days, vs. ≈ 113K rows / 2 days under
`EQP_SECS_ALARM` (Shape A) — Shape B is roughly **15–17% the volume of what
the report already shows**. Not a rounding error.

A broader keyword sweep (`UPPER(EVENT_NAME) LIKE '%FAULT%'/'%ERROR%'/'%WARN%'`)
under `EVENT_TYPE='EQP_SECS_EVENT'` in the same window returned **zero**
additional rows — these 4 `EVENT_NAME` values are the complete alarm-alias
set found so far.

## Finding 2: equipment coverage — some equipment are fully invisible to the current report

208 distinct `EQUIPMENT_ID`s emitted Shape-B alarm-alias events in the 2-day
sample, broken down by prefix:

| EQP prefix | emits Shape B | of which also emits Shape A (`EQP_SECS_ALARM`) |
|---|---|---|
| GDBA | 129 | 90 |
| GWBA | 45 | 45 |
| GTMH | 21 | 17 |
| GCBA | 13 | 4 |

That leaves **~52 pieces of equipment that emit Shape B only** — for these,
the current EAP Alarm report shows **zero** alarms, a complete blind spot,
not just an undercount.

## Finding 3: not all 4 `EVENT_NAME` values are the same kind of thing

Detail-row shape differs materially across the 4 values — a naive "just add
these 4 names to the WHERE clause" fix would be wrong:

- **`AlarmDetected` / `AlarmCleared`** — a genuine SET/CLEAR occurrence pair.
  `EAP_EVENT_DETAIL` carries `AlarmID` / `AlarmCount` / `AlarmClock` (and
  sometimes `AlarmSet`). `EVENT_NAME` itself already encodes SET vs CLEAR —
  no ALCD-sign-bit decoding needed, unlike Shape A's `AlarmCode<0` convention.
  Verified `(EQUIPMENT_ID, AlarmID)` as a valid pairing key via a set-based
  join (not correlated-subquery, to stay cheap): 2-day sample had 786
  distinct Detected `(EQUIPMENT_ID, AlarmID)` pairs, 517 distinct Cleared
  pairs, 459 seen in both — consistent with some alarms still open at the
  window edge.
- **`ProcessAlarm`** — **not a discrete alarm occurrence.** Its detail rows
  are `Clock` / `ProcessState` / `PreviousProcessState` (e.g. `ProcessState=4`
  observed repeatedly) — this is a **process-state transition marker**, not
  an alarm with an ID. Needs separate handling if ever included; it cannot be
  paired by `AlarmID` because it doesn't carry one.
- **`AlarmNeedCountIntoStatistics(MTBA/MTBF)`** — an auxiliary tally event
  referencing an `AlarmID` (for MTBA/MTBF statistics), not itself a primary
  occurrence. Likely emitted alongside a real Detected/Cleared pair rather
  than replacing it.

## Finding 4 (separate issue, not data loss): Shape A's `EVENT_NAME` is itself inconsistent

Within `EVENT_TYPE='EQP_SECS_ALARM'` (Shape A, already captured), `EVENT_NAME`
takes two different forms depending on equipment family:

| EQP prefix | `EVENT_NAME` form |
|---|---|
| GTMH, GWBK, GDSD, most GDBA, GCBA, GPRA, GPTA | numeric alarm code (e.g. `6052`, `3047`) |
| GWBA (all), a small subset of GDBA | descriptive text name (e.g. `DieQualityReject`, `FirstBondNonStick(Wire)`, `MissingDieDetected`) |

Both forms resolve correctly via `EAP_EVENT_DETAIL` (`AlarmCode`/`AlarmText`/
`AlarmCategory`), so this is **not a data-loss bug** — the existing EAV-pivot
logic in `eap_alarm_worker.py` already absorbs it. Documented here only so
any future logic keying directly off raw `EVENT_NAME` (bypassing the detail
join) doesn't assume a single shape.

## Impact on current code

`src/mes_dashboard/workers/eap_alarm_worker.py` (`_EAP_EVENT_SQL_TEMPLATE`,
`_DETAIL_SQL_TEMPLATE`, both instances — the legacy `run_eap_alarm_query_job`
path and the `EapAlarmJob` chunked path) filters
`AND e.EVENT_TYPE = 'EQP_SECS_ALARM'` unconditionally. This means:

- Alarms reported via Shape B (`AlarmDetected`/`AlarmCleared`) are missing
  entirely from the EAP Alarm report for ~156 equipment that use both paths
  (undercount), and **completely absent** for the ~52 equipment that only
  use Shape B (full blind spot).
- Even if Shape B rows were included, the existing SET/CLEAR pairing SQL
  (`_PAIR_SQL`, keyed on `ALCD` sign bit) would not correctly pair them —
  Shape B needs its own pairing rule keyed on `EVENT_NAME` (`AlarmDetected`
  = SET, `AlarmCleared` = CLEAR) and `AlarmID`, not `ALCD`.

## Suggested next steps (not yet implemented)

1. Decide whether `ProcessAlarm` / MTBA-MTBF should be in scope at all for
   the EAP Alarm report, or whether only `AlarmDetected`/`AlarmCleared`
   should be added (these two are structurally closest to Shape A's SET/CLEAR
   model).
2. If in scope, open `/cdd-new` for a change to `eap_alarm_worker.py`:
   add a second query branch (or `UNION ALL`) for Shape B, with its own
   pairing rule (`EVENT_NAME`-based SET/CLEAR, `AlarmID` key) distinct from
   the existing `ALCD`-sign-bit rule, and reconcile both into the same
   output schema.
3. Any follow-up querying against `DWH.EAP_EVENT` should stay within a
   narrow `LAST_UPDATE_TIME` window (a few days at most) and avoid
   correlated per-row subqueries — both caused multi-minute-plus runtimes
   against this table during this investigation.
