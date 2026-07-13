# Investigation: UPH data in `DWH.EAP_EVENT` / `DWH.EAP_EVENT_DETAIL`

**Status:** Investigation only — **not implemented**. No code consumes any UPH
parameter today; the EAP tables are read solely by `eap_alarm_worker.py` for
alarm occurrences, which filters UPH-carrying events out entirely (see
§Impact on current code). This doc records where UPH physically lands in the
raw EAP tables and which equipment report it, so a future UPH-report change has
a verified data source. Sibling of
`docs/architecture/eap-event-alarm-semantics-investigation.md`.

**Date:** 2026-07-08

## Trigger

Question raised while reviewing EAP data: *does the Oracle EAP table actually
receive UPH (units-per-hour) information — e.g. via periodic `M[60]`-style
timed collection reports?* This doc records a direct read-only Oracle
investigation (`DB_USER=MBU1_R`, host `10.1.1.58`, service `DWDB`) that
confirms **yes**, and characterizes coverage by equipment family.

All queries were bounded to short recent `LAST_UPDATE_TIME` windows (3h / 6h /
24h, stated per finding) and avoid correlated per-row subqueries — mandatory on
these tables (see §Query-cost notes). Numbers are single-run snapshots of live
production data; re-running shows minor variance.

## Finding 1: UPH is collected — via dedicated events and periodic reports

Detail values live in `DWH.EAP_EVENT_DETAIL` as EAV rows
(`SEQ_ID, PARAMETER_NAME, PARAMETER_VALUE`) joined to `DWH.EAP_EVENT` on
`SEQ_ID`. Four literal UPH parameters exist (3h window):

| `PARAMETER_NAME` | Carrier event (`EVENT_TYPE` / `EVENT_NAME`) | Family | Cadence |
|---|---|---|---|
| `CurrentLotUPH` | `EQP_SECS_EVENT` / `UPHUpdate`, `EquipmentPerformanceData` | GTMH | event-driven, every few seconds |
| `NetUPH` | `EQP_SECS_EVENT` / `UPHUpdate` | GTMH | event-driven, every few seconds |
| `RuntimeUPH` | `GTMH-####_M[30]` / `ProcessJob_Periodic`; also `TRACKIN` | GTMH | **timed, M[30]** (~30 min) + at track-in |
| `UPHBonded` | `GDBA-####_M[60]` / `ProcessJob_Periodic` | GDBA | **timed, M[60]** (~60 min) |

The `M[60]` / `M[30]` events are periodic SECS collection reports. Notably, in
the sampled window the GDBA `M[60]` (`ProcessJob_Periodic`) events carried
**`UPHBonded` as their only detail parameter** — that periodic report is
essentially a dedicated UPH collection channel. `EVENT_TYPE` on these rows is
the per-report string `<EQP>-####_M[60]` (not the generic `EQP_SECS_EVENT`
bucket); `EVENT_NAME` is `ProcessJob_Periodic`.

Sample `UPHUpdate` values (GTMH, 2026-07-08 08:5x):

| EQUIPMENT_ID | CurrentLotUPH | NetUPH |
|---|---|---|
| GTMH-0071 | 24326 | 4938 |
| GTMH-0005 | 23968 | 10331 |
| GTMH-0066 | 21645 | 12124 |
| GTMH-0064 | 21955 | 12804 |
| GTMH-0043 | 13360 | 5067 |

- Join key: `EAP_EVENT_DETAIL.SEQ_ID = EAP_EVENT.SEQ_ID`; equipment from
  `EAP_EVENT.EQUIPMENT_ID`. **`LOT_ID` was empty on these `UPHUpdate` rows** —
  lot attribution would need a separate lookup (e.g. `CurrentLotID` detail
  param, or a MES container join) if the report is to be lot-keyed.
- `NetUPH` is consistently `< CurrentLotUPH` — plausibly current-lot
  instantaneous rate vs. downtime-adjusted net rate, **but this interpretation
  is unverified** against the equipment SECS spec.
- ⚠️ **Value scale is unresolved.** e.g. `24326` may be `243.26` UPH (×100) or
  a raw integer. Confirm against the SECS spec or one known-good shop-floor UPH
  before using the numbers.

## Finding 2: coverage — only 2 of 10 active families collect literal UPH

Active-equipment universe (24h window, `EAP_EVENT` group-by only):

| Family | active equip | events / 24h |
|---|---|---|
| GDBA | 128 | 9,508,816 |
| GWBK | 66 | 669,923 |
| GWBA | 58 | 672,071 |
| GTMH | 30 | 113,619 |
| GCBA | 21 | 507,678 |
| GDSD | 16 | 78,914 |
| GPRA | 10 | 133,304 |
| GWMT | 1 | 256,217 |
| GWAC | 1 | 901 |
| GPTA | 1 | 90 |

Per-family literal-UPH coverage (6h window, `uph_equip` = distinct equipment
emitting any `%UPH%` param, out of `active_equip` in the same window):

| Family | active (6h) | UPH-emitting | UPH params seen |
|---|---|---|---|
| **GTMH** | 29 | **20** | `CurrentLotUPH`, `NetUPH`, `RuntimeUPH` |
| **GDBA** | 125 | **70** | `UPHBonded` |
| GCBA | 18 | 0 | — |
| GDSD | 16 | 0 | — |
| GPRA | 10 | 0 | — |
| GWBA | 58 | 0 | — |
| GWBK | 66 | 0 | — |
| GWAC / GWMT / GPTA | 1 each | 0 | — |

Reading the coverage correctly:

- **Family-level "0" is robust.** GWBA (58 active) and GWBK (66 active) emitted
  UPH from **zero** machines — a strong signal those machine types are not
  configured to report UPH, not a sampling gap.
- **Within-family ratios (GTMH 20/29, GDBA 70/125) are lower bounds.** Machines
  that were idle / not in production during the 6h window emit no periodic
  report, so "not seen" ≠ "not UPH-capable". Do **not** read GDBA as "45% lack
  UPH".

## Finding 3: fallback — count/quantity params for families without literal UPH

Distinct count/quantity-type detail params (`%COUNT%`/`%QTY%`/`%QUANTITY%`/
`ProcessedDie`/`BondedUnit`/`%OUTPUT%`) by family (6h window):

| Family | literal UPH | count/qty params | derive UPH? |
|---|---|---|---|
| GTMH | yes | 77 | already has UPH |
| GDBA | yes | 14 | already has UPH |
| GCBA | no | 7 | yes — `GoodDieCount`, `TotalGoodQuantity`, `Tester*Count`, `MultiBin*` (looks like final-test / tape-&-reel) |
| GDSD | no | 6 | yes |
| GPRA | no | 4 | yes |
| GWBA | no | 2 | marginal |
| GWAC | no | 2 | marginal |
| **GWBK / GWMT / GPTA** | no | **0** | **no** — neither UPH nor usable counts in EAP detail |

Broader throughput/count params observed in `EAP_EVENT_DETAIL` (3h window, not
family-attributed here): `NumberofProcessedDie`, `UnitBondedCount`,
`CurrentStripBondedUnitCount`, `GoodDieCount`, `TotalGoodQuantity`,
`TotalUnitQuantity`, `ProductiveTime`, `IdleTime`, `DownTime`, and the
MTBF/MTBA/MUBF/MUBA family (`CurrentLotMTBF`, `CurrentLotMTBA`, …). So for
GCBA/GDSD/GPRA a UPH could be derived as output ÷ time from EAP data alone.
GWBK/GWMT/GPTA would have to source throughput from MES tables instead
(`DWH.DW_MES_HM_LOTMOVEOUT`, `DW_MES_LOTWIPHISTORY`, `DW_MES_JOBTXNHISTORY`).

## Impact on current code

`src/mes_dashboard/workers/eap_alarm_worker.py` restricts both Oracle queries
to alarm rows: `EVENT_TYPE='EQP_SECS_ALARM'` plus the v5 alarm-alias predicate
(`EVENT_TYPE='EQP_SECS_EVENT' AND EVENT_NAME IN ('AlarmDetected','AlarmCleared')`).
Its detail pivot only pulls `AlarmCode` / `AlarmText` / `AlarmID`. Therefore
`UPHUpdate`, `EquipmentPerformanceData`, `ProcessJob_Periodic` (`M[30]`/`M[60]`)
and `TRACKIN` — every UPH carrier — are filtered out. **No UPH value reaches any
spool, route, or report today.** A UPH feature is a brand-new extraction path,
not a tweak to the alarm worker.

## Query-cost notes (mandatory for any follow-up)

- `DWH.EAP_EVENT` is far larger than the "~385K rows/day" figure in the
  alarm-semantics doc: **~12M rows/24h** here, GDBA alone **9.5M/24h**. The
  detail table is a multiple of that.
- A `LIKE '%UPH%'` join across `EAP_EVENT ⋈ EAP_EVENT_DETAIL` over a **24h**
  window **exceeded 180s and was aborted**. The same join over **3h / 6h** runs
  in **2–12s**. An `EAP_EVENT`-only group-by over 24h ran in ~41s.
- Keep `LAST_UPDATE_TIME` windows narrow (≤6h for detail joins), pre-filter on
  the indexed `LAST_UPDATE_TIME`, and avoid correlated per-row subqueries.

## Suggested next steps (not yet implemented)

1. Resolve the **value scale** of `CurrentLotUPH`/`NetUPH`/`UPHBonded`/
   `RuntimeUPH` against the SECS spec or a known shop-floor UPH before any
   reporting use.
2. Decide the reporting grain: GTMH is event-driven (`UPHUpdate`, sub-minute)
   vs. GDBA/GTMH periodic (`M[60]`/`M[30]`). A UPH report likely wants the
   periodic channel (bounded volume) rather than every `UPHUpdate`.
3. Decide lot attribution: `UPHUpdate` carried empty `LOT_ID`; needs
   `CurrentLotID` (detail) or a container join.
4. Decide scope for the no-UPH families: derive from EAP counts
   (GCBA/GDSD/GPRA) vs. source from MES (GWBK/GWMT/GPTA).
5. If pursued, open `/cdd-new` for a new EAP-UPH extraction path (its own event
   predicate, detail pivot, spool namespace) — do not overload the alarm worker.

## Reproduction

Read-only probe scripts used for this investigation (bounded windows,
`call_timeout` capped) were run ad hoc against `MBU1_R`; the queries above are
self-describing (window in each finding). Re-run against a narrow
`LAST_UPDATE_TIME` window per §Query-cost notes.
