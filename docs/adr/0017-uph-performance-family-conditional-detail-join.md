# ADR 0017: UPH-performance single chunk query with family-conditional detail JOIN

## Status
proposed

## Context
`/uph-performance` extracts UPH from `DWH.EAP_EVENT ⋈ EAP_EVENT_DETAIL` for two
equipment families only (GDBA→`BondUPH`, GWBA→`fHCM_UPH`; UPH-02/UPH-03). The
detail table is huge (~12M rows/24h; GDBA alone ~9.5M) and a blanket
`LIKE '%UPH%'` detail JOIN over 24h previously timed out at >180s, while ≤6h
windows run in 2–12s (docs/architecture/eap-event-uph-collection-investigation.md).

Two structural questions had to be settled before backend-engineer builds the
worker: (1) how to pick the correct `PARAMETER_NAME` per family without letting
one family's parameter leak onto the other family's rows, and (2) whether GDBA
and GWBA should be one query pass or two unioned passes, and whether cross-chunk
reduction is needed.

The two obvious-but-wrong shortcuts are: a blanket
`d.PARAMETER_NAME IN ('BondUPH','fHCM_UPH')` predicate (would attach a GDBA
`BondUPH` detail row to a GWBA event if one ever co-occurs on the same SEQ_ID —
silent cross-family contamination), and an eap-alarm-style two-query events+EAV-pivot
structure (unnecessary: each M[60] periodic event carries exactly one UPH
parameter, so there is nothing to pivot).

## Decision
1. **One shared `sql/uph_performance.sql` template**, a single JOIN'd chunk query
   per ≤6h TIME window, covering both families. The `EAP_EVENT_DETAIL` JOIN
   selects `PARAMETER_NAME` via a **family-conditional CASE predicate keyed on
   `SUBSTR(EQUIPMENT_ID,1,4)`** (GDBA→`BondUPH`, GWBA→`fHCM_UPH`) — an exact-match
   `d.PARAMETER_NAME = CASE ... END` in the ON clause, never a blanket IN-list.
   This makes the detail JOIN one row per event and structurally prevents
   cross-family parameter leakage.
2. **`requires_cross_chunk_reduction=False` (append path)**, like `EapAlarmJob` —
   each event row is independent; there is no seam-straddling aggregation (unlike
   `ProductionAchievementJob`'s SPECNAME re-aggregation, ADR-0016). `post_aggregate`
   is a plain concat of chunk parquets plus the two enrichment bridges.
3. **Enrichment bridges run in `post_aggregate` (Python), not inline** in the
   Oracle chunk SQL: `LOT_ID`→`DW_MES_CONTAINER` (mirrors eap_alarm_worker) for
   Package/Type, and `EQUIPMENT_ID`→`DW_MES_RESOURCE` for WORKCENTERNAME. Coarse
   user filters on package/type/workcenter remain inline `EXISTS` semi-joins per
   data-shape-contract §3.29.

## Consequences
- Halves Oracle round-trips vs eap-alarm (one JOIN'd query per window vs
  events+detail split), and the exact-match `PARAMETER_NAME` predicate keeps the
  detail cardinality bounded — the timeout risk is confined to the ≤6h chunk cap.
- A future engineer must not "simplify" the CASE predicate into an IN-list;
  UPH-03 and this ADR both lock it. Reversal silently regresses correctness.
- No EAV pivot code path exists here; if a future UPH parameter needs multiple
  detail params per event, this append/single-JOIN shape must be revisited.
- The new `UphPerformanceJob` inherits `BaseChunkedDuckDBJob.run()`, so it becomes
  a 4th consumer of the shared `global_concurrency` semaphore (MAX_CONCURRENT=3);
  see ADR-0011 and design.md Open Risks.
