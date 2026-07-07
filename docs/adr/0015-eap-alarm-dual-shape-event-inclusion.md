# ADR 0015: EAP ALARM dual-shape event inclusion (EQP_SECS_EVENT alarm aliases)

## Status
accepted

## Context
A production investigation (docs/architecture/eap-event-alarm-semantics-investigation.md, 2026-07-07) found that `DWH.EAP_EVENT` carries alarm occurrences in two independent, coexisting reporting shapes. Shape A (`EVENT_TYPE='EQP_SECS_ALARM'`, identity in `EVENT_NAME`, SET/CLEAR from the ALCD sign bit in the detail `AlarmCode` param) is the only shape the EAP ALARM worker queried. Shape B rides the generic `EQP_SECS_EVENT` bucket with alarm semantics entirely in `EVENT_NAME` (`AlarmDetected`/`AlarmCleared`/`ProcessAlarm`/`AlarmNeedCountIntoStatistics(MTBA/MTBF)`), identity in the detail `AlarmID` param. Shape B volume is ~15-17% of Shape A, and ~52 pieces of equipment emit Shape B **only** — a complete blind spot in the report, not just an undercount. The four Shape B `EVENT_NAME` values are not the same kind of thing: only `AlarmDetected`/`AlarmCleared` are genuine SET/CLEAR occurrences; `ProcessAlarm` is a process-state transition marker with no AlarmID; the MTBA/MTBF name is an auxiliary tally emitted alongside a real Detected/Cleared pair.

## Decision
1. **Include** `EVENT_TYPE='EQP_SECS_EVENT' AND EVENT_NAME IN ('AlarmDetected','AlarmCleared')` in both worker Oracle queries (events + detail), alongside the existing Shape A predicate. The driving index predicate stays `LAST_UPDATE_TIME BETWEEN` (EA-03).
2. **Exclude** `ProcessAlarm` (not an alarm occurrence; no AlarmID to pair on) and `AlarmNeedCountIntoStatistics(MTBA/MTBF)` (auxiliary tally; including it would double-count). Adding either later requires its own rule revision.
3. **Per-shape pairing, never cross-shape:** Shape B pairs `AlarmDetected`→`AlarmCleared` on `(EQP_ID, AlarmID)`; Shape A keeps the ALCD sign-bit rule. The pairing key gains `ALARM_SOURCE` (= raw `EVENT_TYPE`) so a CLEAR from one shape can never close a SET from the other — the two identity namespaces are not guaranteed to be the same number space.
4. **New `ALARM_SOURCE` spool column** (raw `EVENT_TYPE`), surfaced additively in the detail endpoint/UI; `_SCHEMA_VERSION` 3→4 so all Shape-A-only v3 parquet is invalidated by key-miss (EA-06).
5. **No dedup of dual-channel duplicates yet.** ~156 equipment emit both shapes; whether the same physical alarm is reported on both channels is unmeasured. Occurrences stay distinguishable via `ALARM_SOURCE`; a dedup rule is deferred until production overlap is measured (set-based join, narrow `LAST_UPDATE_TIME` window — this table punishes correlated subqueries and wide windows).

## Consequences
- The ~52 Shape-B-only equipment appear in the EAP ALARM report for the first time; dual-emitters gain their Shape B occurrences (+~15-17% row volume expected).
- `ALARM_CATEGORY_CODE` is NULL for Shape B rows (no ALCD byte) and decodes to "未知" per EA-05 — the category Pareto/filter treats Shape B as uncategorized rather than guessing.
- If dual-channel duplication is confirmed later, summary counts are inflated for dual-emitters until a dedup rule ships; `ALARM_SOURCE` makes the inflation measurable from the spool itself.
- Rollback to v3 code is key-safe: v3 keys never resolve v4 files; orphaned v4 parquet expires via TTL/cleanup daemon. `GET /detail` DESCRIBE-detects `ALARM_SOURCE`, so in-flight v3 query_ids survive the deploy window.
- Cross-chunk SET/CLEAR pairing stays in `post_aggregate` (ADR-0009) — Shape B pairs that straddle a daily chunk seam pair correctly.
