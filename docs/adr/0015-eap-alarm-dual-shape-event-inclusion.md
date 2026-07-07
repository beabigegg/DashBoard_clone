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
5. **Cross-channel dedup, Shape A wins.** Production measurement (2026-07-07, GDBA family, 2-day `LAST_UPDATE_TIME` window, set-based join): **70.43%** of Shape B `AlarmDetected` events (2079/2952) had a Shape A event with the same identity on the same equipment within ±60s — dual-channel duplication is real, not incidental. Rule: after per-shape pairing, a Shape B occurrence is dropped when a Shape A occurrence exists with the same `(EQP_ID, ALARM_ID)` (string equality) and `ALARM_START` within `_SHAPE_B_DEDUP_TOLERANCE_SECONDS = 60`. Shape A wins deterministically — even when the Shape A occurrence is unpaired — because it carries the ALCD category byte and is the continuation of what the report historically showed. The dedup runs in DuckDB at spool-write time (existence check per Shape B occurrence, not 1:1 assignment): if the two channels ever emit asymmetric flap counts inside one 60s window, the B side can be over-dropped by design — accepted as marginal against the measured 70% duplication. The 60s tolerance is the measured window; changing it requires a new measurement.

## Consequences
- The ~52 Shape-B-only equipment appear in the EAP ALARM report for the first time; dual-emitters gain only their non-duplicated Shape B occurrences (the ~30% unmatched share of the measurement), not a doubled count.
- `ALARM_CATEGORY_CODE` is NULL for Shape B rows (no ALCD byte) and decodes to "未知" per EA-05 — the category Pareto/filter treats Shape B as uncategorized rather than guessing.
- **GWBA is mixed, not purely text**: contrary to the original investigation's Finding 4 table, GWBA's Shape A `EVENT_NAME` is a mix of descriptive text (`DieQualityReject`, `FirstBondNonStick(Wire)`, ...) and numeric alarm codes (`28`, `44`, `46`, `100`, ...) depending on the specific alarm. Only the text-named subset is outside the dedup rule's reach (string never equals a numeric Shape B `AlarmID`); the numeric-named subset dedups correctly through the existing string-equality rule — see Follow-up measurement below.
- Rollback to v3 code is key-safe: v3 keys never resolve v4 files; orphaned v4 parquet expires via TTL/cleanup daemon. `GET /detail` DESCRIBE-detects `ALARM_SOURCE`, so in-flight v3 query_ids survive the deploy window.
- Cross-chunk SET/CLEAR pairing stays in `post_aggregate` (ADR-0009) — Shape B pairs that straddle a daily chunk seam pair correctly, and the dedup window sees all chunks together (a Shape A occurrence in day 1 can dedup a Shape B occurrence at the day-2 seam edge).

## Follow-up measurement (2026-07-07, 7-day window, all equipment)

The 2-day/GDBA-only measurement above was re-run at full scale to check the dedup
direction wasn't backwards, and to characterize GWBA's actual behavior (`docs/architecture/eap-event-alarm-semantics-investigation.md` scope). Method: 7 daily
`LAST_UPDATE_TIME` windows (a single multi-day raw pull, and even a 7-day
`GROUP BY` aggregate, both timed out — must stay chunked to 1 day per query),
detail fetched via batched `SEQ_ID IN (...)` equality lookups (not a date-range
join) — 564,793 events / 1,685,896 detail rows, no timeouts.

**Dedup direction confirmed correct, not reversed.** Across all equipment,
Shape A's own ALCD pairing is self-sufficient: 97.8% of all Shape A paired
occurrences (194,808/199,111) resolve their own END without needing Shape B;
of the Shape A occurrences with no Shape B counterpart at all, 97.9%
(182,801/186,749) still have a clean, self-contained END. Where both shapes
report the same occurrence (12,362 matched pairs, GDBA+GCBA+GWBA), the median
`ALARM_END` difference between shapes is 0 seconds. This is the "S5F1 already
has complete ALCD start/end, S6F11 is a duplicate channel" case, not the
"ALCD can't stand on its own" case — Shape A wins stands.

**GWBA-specific finding: Shape B never emits `AlarmCleared` for this family.**
Across the full week, GWBA's Shape B channel logged 16,909 `AlarmDetected`
events and **zero** `AlarmCleared` events (contrast: GDBA 12,118
Detected/16,155 Cleared, GCBA 1,325 Detected/132,576 Cleared — both channels
present). This looked like a risk that un-deduped GWBA Shape B occurrences
would misrepresent already-closed Shape-A alarms as permanently open, so it
was measured directly: of the 16,909, only 1 has an `(EQP_ID, ALARM_ID)`
identity that also appears as a Shape A SET outside the ±60s dedup window (a
true near-miss); the remaining 14,341 unmatched occurrences have an identity
Shape A has **never** used on that equipment at all — these are genuinely
Shape-B-exclusive alarm signals (GWBA's Shape A side is dominated by
text-named alarms per the mixed-identity note above), not duplicates the
60s tolerance failed to catch. Their `ALARM_END=NULL` is an accurate
reflection of the equipment's own reporting (SET-only, no CLOSE signal ever
sent on this channel for this family) — not a pairing defect. No rule change
follows from this; recorded so a future reader doesn't mistake permanently-open
GWBA Shape B rows for a bug.

Also noted in passing (not acted on): `GCBA-0011` alone contributed 127,018 of
GCBA's 132,576 `AlarmCleared` rows, nearly all `AlarmID='0'` — looks like a
non-alarm heartbeat/placeholder ID rather than a real alarm; worth filtering
if Shape B's scope ever widens beyond `AlarmDetected`/`AlarmCleared`.
