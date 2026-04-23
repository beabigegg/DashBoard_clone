## Why

Hold History 頁面目前有 3 個指標層級的問題需要同時處理：

1. **「平均 Hold 時長」是用 bucket 中點做加權估算**（`<4h`=2、`4-24h`=14、`1-3d`=48、`>3d`=96），`>3d` 統一算 96hr，但實際可能 hold 好幾週，誤差過大
2. **「累計 Future Hold」語意隱晦且具時效衰減性**——現行計算和 PJMES043 原廠 SQL 一致，但數值會隨 MES 清除 `FUTUREHOLDCOMMENTS` 而減少（確認過 3 個 LOT：4/22 07:35 Excel 生成時為 Future Hold，release 後 FH 欄位被清除，再查時變 0），使用者容易誤讀
3. **缺少穩定的「品質重複觸發」指標**——現行 Future Hold 依賴 `FUTUREHOLDCOMMENTS`（會被清空），而業務方實際關心的是「品質異常重複發生」的警示，應該以**純 `(lot, reason)` 重複歷史**為準，不看備註欄位

本次變更純粹在指標層（後端計算 + UI 卡片），不動模式切換 / 篩選條件 / API 契約；當日模式等 UX 改造另行於 `hold-history-today-mode` 處理。

## What Changes

### 卡片層
- 移除前端 `estimateAvgHoldHours()` bucket 加權估算邏輯
- **BREAKING**：「平均 Hold 時長」拆成兩張卡
  - **已解除平均時長**：`AVG(HOLD_HOURS) WHERE RELEASETXNDATE IS NOT NULL`（精確值）
  - **持續 Hold 平均時長**：`AVG(HOLD_HOURS) WHERE RELEASETXNDATE IS NULL`（spool 建立當下的 SYSDATE 快照值）
- **新增**「已解除最長時長」與「持續 Hold 最長時長」兩張卡（`MAX(HOLD_HOURS)`，相同拆分語意）
- 「累計 Future Hold」卡片保留，但 UI 加上 tooltip 說明「**當下仍標記為 Future Hold 的總量；lot release 後 MES 可能清除此標記，數值具時效衰減特性**」
- **新增**「品質重複觸發」卡片：`RN_CONHOLD > 1 AND hold_type='quality'`（純粹依歷史重複推斷，不看 `FUTUREHOLDCOMMENTS`），定位為「品質異常再次發生」的穩定監控指標

### API 契約
- duration 回傳 payload 從 `{ items: [...] }` 擴充為 `{ items: [...], avgReleasedHours, avgOnHoldHours, maxReleasedHours, maxOnHoldHours }`
- trend 回傳新增 `repeatQualityHoldQty`（每日，對應「品質重複觸發」卡片）
- 前端 `summary` computed 物件同步新增 `avgReleasedHours` / `avgOnHoldHours` / `maxReleasedHours` / `maxOnHoldHours` / `repeatQualityHoldQty`，移除 `avgHoldHours`

### 文件與追溯
- 於 `docs/hold_history.md` 加入 Future Hold 時效衰減行為的技術說明，引用 PJMES043 原廠 SQL 作為 ground truth
- 確認現行 `FUTURE_HOLD_FLAG` 邏輯與原廠一致（無 bug），本次變更不動 trend.sql 的 `futureHoldQty` 計算

### 回歸防護
- 指標層改動必須保證既有圖表數值不變（只新增欄位，不改舊欄位計算）
- 新增 Oracle SQL ↔ DuckDB SQL runtime ↔ 前端 DuckDB-WASM 三路徑 parity 測試

## Capabilities

### New Capabilities
（無）

### Modified Capabilities
- `hold-history-api`：duration 回傳擴充兩組 AVG / MAX 欄位；trend 回傳新增 `repeatQualityHoldQty`；既有欄位語意不變
- `hold-history-page`：SummaryCards 從 7 格擴充為 10 格（拆平均、新增最長、新增品質重複觸發）；移除 bucket 加權估算；Future Hold 卡新增 tooltip

## Impact

**後端**
- `src/mes_dashboard/sql/hold_history/duration.sql`：新增 `avg_released_hours` / `avg_on_hold_hours` / `max_released_hours` / `max_on_hold_hours` 欄位至最終 SELECT
- `src/mes_dashboard/sql/hold_history/trend.sql`：在日聚合中新增 `repeat_quality_hold_qty = SUM(QTY) WHERE hold_day=day AND rn_conhold>1 AND hold_type='quality'`
- `src/mes_dashboard/services/hold_history_service.py`：`get_hold_history_duration()`、`get_hold_history_trend()` 回傳擴充
- `src/mes_dashboard/services/hold_history_sql_runtime.py`：`_query_duration()` / `_query_trend()` 擴充
- `src/mes_dashboard/sql/hold_history/base_facts.sql`：無需改動（欄位已存在）

**前端**
- `frontend/src/hold-history/useHoldHistoryDuckDB.js`：`queryDuration()` / `queryTrend()` 新增 AVG/MAX/repeat 查詢
- `frontend/src/hold-history/components/SummaryCards.vue`：卡片結構由 7 改 10
- `frontend/src/hold-history/App.vue`：刪除 `estimateAvgHoldHours()`；`summary` computed 改用 API 回傳
- SummaryCards 新卡片樣式 + Future Hold tooltip（shared-ui 的 `SummaryCard.vue` 可能需支援 `tooltip` prop）

**文件**
- `docs/hold_history.md`：補充 Future Hold 時效衰減現象、與 PJMES043 原廠 SQL 對照
- `openspec/changes/hold-history-metric-refinement/` 本身

**測試 — 遵循最近的 CI/CD 回歸防護強化**
- 單元：`tests/test_hold_history_service.py`、`tests/test_hold_history_sql_runtime.py`、`tests/test_hold_dataset_cache.py` 新增欄位與空集合邊界
- SQL parity：`tests/test_hold_history_sql_parity.py` 新增 Oracle vs DuckDB server 對 AVG/MAX/repeat 欄位
- 前後端 parity：`tests/test_frontend_hold_history_parity.py` 新增 server DuckDB vs client DuckDB 誤差 < 0.01hr（平均/最長）、整數一致（repeat）
- E2E：`tests/e2e/test_hold_history_e2e.py` 新增 10 張卡片斷言、Future Hold tooltip 存在
- Released pages gate（`.github/workflows/released-pages-hardening-gates.yml`）納入此頁
- Real-infra-smoke：新 API 欄位不引入新 endpoint，無需 gate 變更；但需確認既有 smoke 測試未因 payload 擴充失敗
- Route fuzz：既有 fuzz 測試（POST /query、GET /view）無新參數引入，但要確認新欄位序列化不造成 5xx

**依賴**
- 無新套件；Oracle DB timezone 已驗證為 `+08:00`，SYSDATE 可信
- 無向下相容層——同次 PR 前後端一併更新

**風險**
- 若既有 duration / trend 回傳被第三方（例如 Hold Overview 頁）讀取，新欄位不影響現有使用者；驗收時確認 hold-overview-page 是否會被波及
