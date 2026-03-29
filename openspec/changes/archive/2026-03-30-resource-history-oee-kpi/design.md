## Context

Resource-history 頁面目前基於 `DW_MES_RESOURCESTATUS_SHIFT` 單一數據源，透過兩階段快取架構（Oracle → Parquet spool → DuckDB runtime）提供設備稼動率指標。現在要擴充 OEE（= Availability × Yield），需要新增第二個數據源（LOTWIPHISTORY + LOTREJECTHISTORY）並整合進現有管線。

現有架構（Phase 5+ sole-path）：
- `base_facts.sql` → Oracle 查 RESOURCESTATUS_SHIFT → Parquet spool
- `resource_history_sql_runtime.py` → DuckDB 讀 Parquet → 計算 KPI/Trend/Heatmap/Detail（唯一 compute path）
- `resource_dataset_cache.py` → 管理 spool lifecycle；`apply_view()` 呼叫 DuckDB runtime，失敗回傳 None → route 回 410 cache_expired，前端重新查詢
- Canonical base dataset：spool key 只含 date_range + granularity，filter 在 DuckDB view-time 套用（不同 filter 組合共用同一份 spool）
- 長日期範圍走 `batch_query_engine`（時間分片 → chunk merge → spool）

OEE 驗證結果（焊接_DB, 2026-03-01~25）：產出 99.7%、NG 98.1%、Yield 差 0.01%。

## Goals / Non-Goals

**Goals:**
- 在現有 resource-history 頁面新增 OEE% 指標（KPI 卡片、趨勢折線、Detail 欄位、Heatmap 切換）
- 與現有稼動率數據整合，在同一查詢流程中取得產量/不良數據
- 維持現有 API 結構的向下相容

**Non-Goals:**
- 補償 DWH 缺少的 LotTerminate 數據（已知 NG 偏低 ~1.9%，未來待 DWH 提供新資料源）
- 即時 OEE（目前仍是班次後批次計算）
- Performance 因子（固定 1.0，無標準週期時間數據）
- 新增獨立的 OEE 頁面

## Decisions

### D1: 產量數據查詢策略 — 第二條 Oracle SQL 平行查詢

**選擇：** 新增 `oee_facts.sql`，在 `execute_primary_query()` 中與 `base_facts.sql` **平行執行**，結果寫入第二份 Parquet spool（prefix `resource_oee`）。長日期範圍時，oee_facts 也走 `batch_query_engine` 分片路徑（與 base_facts 相同策略）。

**替代方案：**
- (A) 合併進 base_facts.sql 用 JOIN → 拒絕：RESOURCESTATUS_SHIFT 用 TXNDATE 日曆日，LOTWIPHISTORY 用 TRACKOUTTIMESTAMP shift-adjusted 07:30 日期，時間軸不同無法直接 JOIN
- (B) 前端獨立呼叫新 API → 拒絕：增加前端複雜度和額外 roundtrip

**理由：** 兩條 SQL 獨立且時間軸不同（日曆日 vs 班別日期），平行查詢可最大化效率。DuckDB runtime 在計算 OEE 時 JOIN 兩份 spool。

### D1b: OEE spool key 策略 — 跟進 canonical base dataset pattern

**選擇：** OEE spool 的 key 也只含 `date_range + granularity`（不含 filter params），與 base_facts 的 canonical pattern 一致。`oee_facts.sql` 查詢全部設備的產量數據，filter（workcenter/family/resource）在 DuckDB view-time 套用。

**理由：** 同一份 OEE spool 可被不同 filter 組合共用，避免重複 Oracle 查詢。OEE 數據粒度小（EQUIPMENTID × SHIFT_DATE），全量查詢不會造成效能問題。

### D2: OEE spool 的 JOIN 粒度 — HISTORYID × SHIFT_DATE

**選擇：** `oee_facts.sql` 輸出粒度為 `EQUIPMENTID × SHIFT_DATE`（與 base_facts 的 `HISTORYID × DATA_DATE` 對齊），其中 `SHIFT_DATE = TRUNC(TRACKOUTTIMESTAMP - 450/1440)`。

DuckDB runtime 用 `HISTORYID = EQUIPMENTID AND DATA_DATE = SHIFT_DATE` JOIN 兩份 spool。

**注意：** 日曆日 vs 班別日期可能有 ±1 天偏移（07:30 切分），但因 KPI 是全期間彙總、Trend 是按日分群，微小偏移不影響整體趨勢。Detail 和 Heatmap 同理。

### D3: NG 歸屬邏輯 — Compound key 不含日期

**選擇：** NG 用 `CONTAINERID + SPECNAME + WORKCENTERNAME` 配對到設備（不含 reject 操作日期）。NG 歸到 WIP 的 TrackOut 設備和 TrackOut 日期。

**理由：** Reject 操作日期是「發現時間」，不是「生產時間」。跨日 reject 佔 unmatched 的 62%（249/403），去掉日期後 NG 匹配從 94.1% 提升到 98.1%。

**實作方式：** `oee_facts.sql` 內完成 JOIN — WIP 取 fingerprint（CONTAINERID+SPEC+WC+EQUIPMENTID），REJECT 按 CONTAINERID+SPEC+WC 彙總，SQL 內 JOIN 後輸出已歸屬的 `EQUIPMENTID × SHIFT_DATE × TRACKOUT_QTY × NG_QTY`。

### D4: Reject 日期範圍 — 擴大查詢窗口

**選擇：** Reject 查詢日期範圍比生產查詢窗口前後各擴大 30 天（`start_date - 30` ~ `end_date + 30`）。

**理由：** Reject 可能在 TrackOut 數天甚至數週後才記錄。擴大窗口確保跨期 reject 能配對到生產記錄。

### D5: 產出計算 — 不做 dedup

**選擇：** 直接 `SUM(TRACKOUTQTY)`，不做 ROW_NUMBER dedup。

**理由：** 每筆 partial trackout 都是真實產出。Dedup（取最新一筆）會少 24%。

### D6: OEE 公式各層一致性

| 層 | 計算位置 | 說明 |
|---|---|---|
| Oracle SQL | `oee_facts.sql` | 只輸出 TRACKOUT_QTY + NG_QTY per equipment per shift_date |
| DuckDB runtime | `_query_kpi()` 等 | `yield_pct = trackout / (trackout + ng) * 100`；`oee_pct = availability_pct * yield_pct / 100`（唯一 compute path） |
| Frontend | `compute.js` | `calcOeePct(avail, yield)` = avail × yield / 100；`calcYieldPct(trackout, ng)` |

> **Note:** Pandas fallback 已於 Phase 5 退役，DuckDB runtime 為唯一計算路徑。runtime 失敗時 `apply_view()` 回傳 None → route 回 410，前端重新查詢。

### D7: 前端 KPI 卡片佈局 — 10 → 10 張

**選擇：** 新增 OEE% 卡片，放在 OU% 和 AVAIL% 之間。9 → 10 張。

**排列：** `OU% | OEE% | AVAIL% | PRD | SBY | UDT | SDT | EGT | NST | 機台數`

### D8: Heatmap 指標切換

**選擇：** Heatmap 新增下拉選單，可切換 OU% / OEE% / AVAIL%。預設 OU%。

## Risks / Trade-offs

**[日曆日 vs 班別日期偏移]** → DuckDB JOIN 時 DATA_DATE (00:00 切分) 和 SHIFT_DATE (07:30 切分) 可能差 1 天。Mitigation: KPI 全期間彙總不受影響；Trend/Detail 的 1 天偏移在實務上可接受（同一筆設備-日期的 E10 時間和產出已各自正確，只是可能落在相鄰日期）。若未來需要精確對齊，可在 base_facts.sql 改用 07:30 切分。

**[NG 偏低 ~1.9%]** → 已知 DWH 缺少 TrackIn 前報廢的 container。Mitigation: 差距穩定且小（Yield 差 0.01%），等 DWH 新增資料源後可直接調整 SQL。

**[Reject 擴大窗口的查詢效能]** → 前後各 30 天會增加 LOTREJECTHISTORY 的查詢量。Mitigation: LOTREJECTHISTORY 的數據量遠小於 RESOURCESTATUS_SHIFT（~2% 的 lot 有 reject），且 SQL 內 JOIN 後只輸出彙總結果。

**[Parquet spool 檔案數量翻倍]** → 新增第二份 spool（oee_facts）。Mitigation: OEE spool 粒度為 EQUIPMENTID × SHIFT_DATE（遠小於 base_facts 的逐筆 shift 記錄），檔案體積 < 1MB。
