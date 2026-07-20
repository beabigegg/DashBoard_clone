-- Production Achievement Rate -- MOVE-OUT (轉出) source
-- (production-achievement-moveout, business-rules.md PA-18)
--
-- The "轉出" counterpart to production_achievement.sql's "產出" query. Groups
-- DW_MES_HM_LOTMOVEOUT move-out events by
-- (output_date, shift_code, raw_workcenter_group, PACKAGE_LF), where
-- raw_workcenter_group is the SOURCE station (FROMWORKCENTER, i.e. the station
-- the lot LEFT) -- move-out volume is "what left a station", not "what entered".
-- Unlike the 產出 query this needs NO PA-05 predicate: a move-out event already
-- states its own FROMWORKCENTER, so there is nothing to "guess" about whether a
-- row counts as a given station's output. Which stations appear in the report
-- is decided downstream by the PA-10 workcenter_merge_map INNER JOIN
-- (client-side, useProductionAchievementDuckDB.ts) -- this query stays
-- source-agnostic to that whitelist.
--
-- Derivation vs the IT-provided Live report SQL (025.txt, B subquery) -- every
-- deliberate deviation is documented in the plan's "與 025.txt 的邏輯對照" table:
--   * source station: 025.txt joins PJ_SPECWORKCENTER_V on Fromspecid to get the
--     name; DW already ETLs it into the FROMWORKCENTER column -> no join needed.
--   * shift_code: 025.txt recomputes shift from a TxnDate CASE; DW's SHIFTNAME
--     column is trusted for the shift ASSIGNMENT per the change request (no
--     TxnDate recompute), then normalized to the {D,N} label the pipeline
--     keys on (see the main SELECT's shift_code CASE and PA-18).
--   * qty: 025.txt uses NVL(PJ_GOODDIEQTY, Qty) via the combine-lot table for
--     EVERY station; the change request originally unified on the raw QTY
--     everywhere (no combine-lot join). Real-DB investigation (2026-07,
--     PJMES025 reconciliation) found this raw-QTY simplification silently
--     under-counts TMTT specifically by ~10% (D -9.0%/N -12.1%, 2026-07-15):
--     TMTT physically combines multiple original GA-prefixed lots into one
--     carrier container ("合批") that continues downstream, and that
--     carrier's own QTY does not always reflect the true per-lot good-die
--     total. tmtt_gooddie below reinstates 025.txt's NVL(PJ_GOODDIEQTY, Qty)
--     pattern, scoped ONLY to TMTT (every other station keeps raw QTY,
--     already reconciled clean against Live -- see the 12-station audit in
--     this change's investigation report). Verified against the same
--     PJMES025 detail: after a DW replication gap for the TMTT->品檢 hop was
--     fixed by IT (2026-07-17 re-transfer), this TMTT-only GOODDIEQTY swap
--     reconciles to Live exactly (40,464,399 = 40,464,399, both shifts).
--
--     Separately, 切割 was found to diverge from Live by +20% (2026-07-15)
--     for an UNRELATED reason: 025.txt applies Round(QTY/consumefactor,0) to
--     切割 alone (its WorkCenter10 column) -- no other station, including
--     TMTT, is divided by consumefactor -- and ALSO keeps PKG_SAW as a fully
--     separate report column (WorkCenter85, raw QTY, never summed with
--     切割). This project's workcenter_merge_map used to roll PKG_SAW into
--     切割's parent_group (PA-19), which both double-added PKG_SAW's volume
--     onto 切割 AND masked that 切割's own QTY still needed the consumefactor
--     division. CONSUMEFACTOR lives directly on DW_MES_HM_LOTMOVEOUT (no
--     join needed); dividing 切割's QTY by NVL(CONSUMEFACTOR,1) (Oracle
--     ROUND, matching 025.txt's NVL(CF.consumefactor,1) fallback) plus
--     removing the PKG_SAW seed row (scripts/sql/production_achievement_
--     tables.sql -- PKG_SAW is now D2 excluded, like TCT/MA/IST) reconciles
--     切割 to Live exactly (42,070,354 = 42,070,354, both shifts,
--     2026-07-15).
--
--     ADDENDUM (2026-07-20): the PKG_SAW seed-removal half of the above fix
--     was later reversed at the requester's explicit choice -- PKG_SAW is
--     merged back into 切割's parent_group (scripts/sql/production_
--     achievement_tables.sql) as a DISPLAY-ONLY 大項 rollup, mirroring how
--     電鍍 rolls up 掛鍍/條鍍/滾鍍/委外. This query's own CONSUMEFACTOR
--     division above is UNCHANGED and still keyed strictly on
--     FROMWORKCENTER='切割' (PKG_SAW rows still fall to the ELSE branch,
--     i.e. raw QTY, exactly like Live's own WorkCenter85 column) -- the
--     re-merge only changes which parent_group PKG_SAW's raw_workcenter_group
--     resolves to, client-side in useProductionAchievementDuckDB.ts's
--     _buildRollup(). This dashboard's 切割 大項小計 total will therefore
--     again diverge from Live's own 025.txt report (which never sums
--     WorkCenter10+WorkCenter85) by PKG_SAW's volume -- a known, confirmed
--     tradeoff, not a regression of the reconciliation above.
--   * PACKAGE_LF: 025.txt calls the Live-only PL/SQL PJ_GET_PACKAGE_NEW_F over
--     five OLTP tables that have NO DW equivalent; we approximate by reverse-
--     looking-up DW_MES_LOTWIPHISTORY.PACKAGE_LF via CONTAINERID (documented
--     approximation -- needs real-DB sampling to confirm parity, PA-18).
--
-- output_date (PA-03): move-out has no pre-attributed "shift date" column, so
-- the overnight N-shift tail (TxnDate time-of-day < 07:30:00) is attributed to
-- the PREVIOUS calendar day here, exactly as production_achievement.sql does for
-- TRACKOUTTIMESTAMP. shift_code comes from SHIFTNAME (trusted assignment,
-- normalized to {D,N}); only the DATE bucket is recomputed. The historical
-- 2020-Q1 three-shift regime (PA-02/PA-04) is NOT replicated here -- SHIFTNAME's
-- shift assignment is trusted as-is.
--
-- Parameters (bound via oracledb named params):
--   :start_date     - YYYY-MM-DD (inclusive lower bound on TXNDATE)
--   :chunk_end_excl - YYYY-MM-DD HH24:MI:SS (exclusive upper bound on TXNDATE).
--                     Widened to a full datetime for the same D6/PA-15 reason as
--                     the 產出 query: the worker appends one narrow closing chunk
--                     [end_date+1 00:00:00, end_date+1 07:30:00) so end_date's
--                     overnight N-shift tail is not systematically dropped.
--
-- Tables:
--   DWH.DW_MES_HM_LOTMOVEOUT (alias weh) -- move-out events. Carries
--     FROMWORKCENTER/WORKCENTER, FROMSPECNAME/SPECNAME, SHIFTNAME, QTY,
--     CONSUMEFACTOR, TXNDATE, CONTAINERID, CONTAINERNAME, CALLBYCDONAME.
--   DWH.DW_MES_LOTWIPHISTORY (alias h) -- reverse-lookup for PACKAGE_LF only,
--     joined by the indexed CONTAINERID (DW_MES_LOTWIPHISTORY_IDX1).
--   DWH.DW_MES_PJ_COMBINEDASSYLOTS -- TMTT-only combine-lot table. LOTID is
--     the "carrier" container's own CONTAINERID (verified against 025.txt's
--     B-subquery: CAL.LOTID = FL.CONTAINERID, FL.ContainerId = HM.HistoryId
--     -- i.e. the SAME CONTAINERID scoped_moveout already carries for a TMTT
--     row). CONTAINERID/PJ_GOODDIEQTY are per-original-lot rows under that
--     LOTID; summed, they give the carrier's true good-die quantity.
--
-- MAX_TXN_TS (added for the UI "資料最新一筆時間" freshness indicator): a
-- plain extra aggregate on the outer SELECT, unrelated to this query's own
-- qualifying predicates and NOT part of GROUP BY.

WITH scoped_moveout AS (
    SELECT
        weh.CONTAINERID,
        weh.TXNDATE,
        weh.SHIFTNAME,
        weh.FROMWORKCENTER,
        weh.QTY,
        weh.CONSUMEFACTOR
    FROM DWH.DW_MES_HM_LOTMOVEOUT weh
    WHERE weh.TXNDATE >= TO_TIMESTAMP(:start_date,     'YYYY-MM-DD')
      AND weh.TXNDATE <  TO_TIMESTAMP(:chunk_end_excl, 'YYYY-MM-DD HH24:MI:SS')
      AND weh.CALLBYCDONAME = 'LotMoveOut'
      -- exclude same-station internal moves; '<>' also drops rows where either
      -- side is NULL (mirrors 025.txt's INNER-JOIN "both stations resolve" gate)
      AND weh.FROMWORKCENTER <> weh.WORKCENTER
      -- 20251022 add: exclude 電鍍退火 on either side. NVL so a NULL spec (which
      -- is NOT 電鍍退火) is kept, not silently dropped by NULL '<>' semantics.
      AND NVL(weh.FROMSPECNAME, ' ') <> '電鍍退火'
      AND NVL(weh.SPECNAME,     ' ') <> '電鍍退火'
      -- 不計算重工 (PA-18): exclude rework moveout via the OWNERNAME owner-type
      -- column -- NOT a CONTAINERNAME 'GA%'/'GC%' prefix.
      --
      -- Real-DB validation (2026-07-15, reconciled against the Live PJMES025
      -- 月轉出 detail). The CONTAINERNAME is only 'GA%'/'GC%' at front/mid
      -- stations. At the back end (品檢 / FQC / 成品入庫 / TMTT) the SAME
      -- non-rework lot is re-containered to a numeric '66%'/'67%' name, so a
      -- 'GA%/GC%' NAME filter silently ZEROES those four 大項 (measured: 0 vs
      -- Live's ~585-595M each). Live avoids this by tracing the assembly-lot's
      -- ORIGINAL container -- NVL(AL.CONTAINERNAME, FL.CONTAINERNAME) LIKE
      -- 'GA%'/'GC%' via PJ_COMBINEDASSEMBLYLOTS (025.txt B-subquery). DW's
      -- OWNERNAME is the stable owner-type that survives the re-containering
      -- and directly encodes the report's ONE documented exclusion rule
      -- ("＊重工工單不計算為轉出"): the only rework owner-type is '重工RW'.
      -- Excluding it (and any 重工-prefixed variant) counts every other
      -- owner-type -- 量產/點測/代工/樣品/工程/餘晶/已驗證/降規/… -- exactly as
      -- Live does. Reconciled clean-station total to Live 月轉出 within +0.13%
      -- (a narrow 量產+點測-only whitelist under-counts by 1.35% because Live
      -- also keeps 代工/樣品/工程). TMTT and 切割 each had their own separate
      -- station-specific quantity deviation, both now fixed -- see the qty:
      -- header bullet above.
      AND NVL(weh.OWNERNAME, ' ') NOT LIKE '重工%'
),
tmtt_gooddie AS (
    -- TMTT-only NVL(PJ_GOODDIEQTY, Qty) source (see header comment). Scoped
    -- to TMTT CONTAINERIDs already in scoped_moveout to keep the IN-list
    -- small; other stations never look this CTE up (see the CASE in the
    -- final SELECT), so an empty/no-match row here just falls through to
    -- the existing raw QTY via NVL at the aggregation site.
    SELECT LOTID AS CONTAINERID, SUM(PJ_GOODDIEQTY) AS GOODDIE_QTY
    FROM DWH.DW_MES_PJ_COMBINEDASSYLOTS
    WHERE LOTID IN (
        SELECT DISTINCT CONTAINERID FROM scoped_moveout WHERE FROMWORKCENTER = 'TMTT'
    )
    GROUP BY LOTID
),
container_package AS (
    SELECT CONTAINERID, PACKAGE_LF
    FROM (
        SELECT
            h.CONTAINERID,
            h.PACKAGE_LF,
            ROW_NUMBER() OVER (
                PARTITION BY h.CONTAINERID
                -- prefer a non-NULL PACKAGE_LF, then a deterministic tiebreak;
                -- a container's PACKAGE_LF is stable across its history rows
                ORDER BY CASE WHEN h.PACKAGE_LF IS NULL THEN 1 ELSE 0 END,
                         h.PACKAGE_LF
            ) AS pkg_rn
        FROM DWH.DW_MES_LOTWIPHISTORY h
        WHERE h.CONTAINERID IN (SELECT DISTINCT CONTAINERID FROM scoped_moveout)
    )
    WHERE pkg_rn = 1
)
SELECT
    -- shift_code: SHIFTNAME is trusted for the shift ASSIGNMENT (no TxnDate
    -- recompute, per the change request), but its label is normalized to the
    -- {D,N} codes the whole pipeline keys on. The client rollup buckets
    -- shift_code='D'/'N' verbatim (useProductionAchievementDuckDB.ts) and the
    -- 產出 query (production_achievement.sql) emits exactly 'D'/'N', so any
    -- other encoding (日/夜, DAY/NIGHT, 日班/夜班, lowercase) would fall through
    -- BOTH shift columns and silently zero D班/N班 while 每日 shows the full
    -- total. This CASE is a no-op when SHIFTNAME is already 'D'/'N'; an
    -- unrecognized value passes through unchanged (same as before -- and its
    -- daily total still reconciles, only the D/N split would be blank). The
    -- domain owner confirmed the real column is already 'D'/'N', so this CASE is
    -- a defensive no-op on real data (PA-18).
    CASE
        WHEN UPPER(TRIM(m.SHIFTNAME)) IN ('D', 'DAY', 'D班', '日', '日班', '白', '白班') THEN 'D'
        WHEN UPPER(TRIM(m.SHIFTNAME)) IN ('N', 'NIGHT', 'N班', '夜', '夜班', '晚', '晚班') THEN 'N'
        ELSE TRIM(m.SHIFTNAME)
    END AS SHIFT_CODE,
    CASE
        WHEN m.TXNDATE IS NULL THEN NULL
        WHEN TO_CHAR(m.TXNDATE, 'HH24:MI:SS') < '07:30:00'
        THEN TRUNC(m.TXNDATE) - 1
        ELSE TRUNC(m.TXNDATE)
    END AS OUTPUT_DATE,
    TRIM(m.FROMWORKCENTER) AS RAW_WORKCENTER_GROUP,
    cp.PACKAGE_LF AS PACKAGE_LF,
    -- TMTT: prefer the combine-lot GOODDIEQTY total, fall back to the
    -- carrier's own QTY when it never appears in the combine-lot table
    -- (never combined). Every other station is untouched (gd.CONTAINERID
    -- only has rows for TMTT-sourced CONTAINERIDs -- see tmtt_gooddie).
    -- 切割: 025.txt's Round(QTY/consumefactor,0) (see header comment) --
    -- no other station divides by consumefactor.
    SUM(
        CASE
            WHEN m.FROMWORKCENTER = 'TMTT' THEN NVL(gd.GOODDIE_QTY, m.QTY)
            WHEN m.FROMWORKCENTER = '切割' THEN ROUND(m.QTY / NVL(m.CONSUMEFACTOR, 1), 0)
            ELSE m.QTY
        END
    ) AS ACTUAL_OUTPUT_QTY,
    MAX(m.TXNDATE) AS MAX_TXN_TS
FROM scoped_moveout m
LEFT JOIN container_package cp ON m.CONTAINERID = cp.CONTAINERID
LEFT JOIN tmtt_gooddie gd ON m.CONTAINERID = gd.CONTAINERID
GROUP BY
    CASE
        WHEN UPPER(TRIM(m.SHIFTNAME)) IN ('D', 'DAY', 'D班', '日', '日班', '白', '白班') THEN 'D'
        WHEN UPPER(TRIM(m.SHIFTNAME)) IN ('N', 'NIGHT', 'N班', '夜', '夜班', '晚', '晚班') THEN 'N'
        ELSE TRIM(m.SHIFTNAME)
    END,
    CASE
        WHEN m.TXNDATE IS NULL THEN NULL
        WHEN TO_CHAR(m.TXNDATE, 'HH24:MI:SS') < '07:30:00'
        THEN TRUNC(m.TXNDATE) - 1
        ELSE TRUNC(m.TXNDATE)
    END,
    TRIM(m.FROMWORKCENTER),
    cp.PACKAGE_LF
