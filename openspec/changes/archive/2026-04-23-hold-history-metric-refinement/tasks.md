## 1. Backend — Oracle SQL（Fallback Path）

- [x] 1.1 修改 `src/mes_dashboard/sql/hold_history/duration.sql`：在 `filtered` CTE 分離 released / on-hold 兩組，於最終 SELECT 新增 `avg_released_hours` / `avg_on_hold_hours` / `max_released_hours` / `max_on_hold_hours` 欄位；bucket 分佈邏輯維持不變（仍 `RELEASETXNDATE IS NOT NULL`）
- [x] 1.2 修改 `src/mes_dashboard/sql/hold_history/trend.sql`：在 `daily_hold` 聚合內新增 `repeat_quality_hold_qty = SUM(CASE WHEN h.hold_day = c.day_date AND h.rn_future_reason > 1 AND h.hold_type='quality' THEN h.qty ELSE 0 END)`；既有聚合欄位不動
- [x] 1.3 修改 `src/mes_dashboard/services/hold_history_service.py`：
  - `get_hold_history_duration()` 回傳新增 4 個欄位（round 2 位小數；空集合回 0）
  - `get_hold_history_trend()` 每日 payload 新增 `repeatQualityHoldQty`
- [x] 1.4 確認 `hold_history_service.py` 的 `_normalize_trend_day()` / `_empty_trend_day()` / `_empty_trend_metrics()` 也同步加入 `repeatQualityHoldQty`（預設 0）
- [x] 1.5 確認 Redis trend cache（`_TREND_CACHE_KEY_PREFIX = hold_history:daily`）解碼時能容許舊 payload 缺少新欄位（透過 `_safe_int` 回 0）

## 2. Backend — DuckDB SQL Runtime（Server-side）

- [x] 2.1 修改 `src/mes_dashboard/services/hold_history_sql_runtime.py` 的 `_query_duration()`：
  - 移除 `where_parts = ['"RELEASETXNDATE" IS NOT NULL']` 硬約束，改為只套用在 bucket GROUP BY 子查詢
  - 新增兩條 AVG 查詢 + 兩條 MAX 查詢（一組 released、一組 on-hold），共用 `type_clause + record_clause + reason filter`
  - 使用 `Promise`-style 平行執行（或單一 CTE）以降低 I/O 成本
  - 回傳中加入 `avgReleasedHours` / `avgOnHoldHours` / `maxReleasedHours` / `maxOnHoldHours`（四捨五入 2 位小數）
- [x] 2.2 修改 `_query_trend()`：在日聚合 SQL 中新增 `repeat_quality_hold_qty`（SUM CASE WHEN rn_future_reason > 1 AND hold_type = 'quality'）
- [x] 2.3 確認 `_query_trend()` 取得的 `rn_future_reason` 和 `hold_type` 欄位已存在於 Parquet spool（來自 `base_facts.sql` 的 `RN_FUTURE_REASON` / `HOLD_TYPE`）；若欄位命名有差異需處理
- [x] 2.4 更新 `try_compute_view_from_spool()` 回傳的 meta，新欄位必須為頂層 key（不是包在子物件內）

## 3. Frontend — DuckDB-WASM Local Compute

- [x] 3.1 修改 `frontend/src/hold-history/useHoldHistoryDuckDB.js`：
  - `queryDuration()` 保留既有 bucket 計算（含 `RELEASETXNDATE IS NOT NULL`）
  - 新增四條 AVG / MAX 查詢，使用同樣的 `baseConditions + holdType + reason filter`，分別加上 `RELEASETXNDATE IS NOT NULL` / `IS NULL`
  - 用 `Promise.all` 合併；回傳 `{ items, avgReleasedHours, avgOnHoldHours, maxReleasedHours, maxOnHoldHours }`
- [x] 3.2 修改 `queryTrend()`：在每日 CROSS JOIN SQL 中新增 `repeat_quality_hold_qty` 聚合欄位（和 server 相同條件），回傳時加入每日物件

## 4. Frontend — SummaryCards UI 改造

- [x] 4.1 修改 `frontend/src/hold-history/components/SummaryCards.vue`：
  - `defineProps` default 移除 `avgHoldHours`，新增 `avgReleasedHours` / `avgOnHoldHours` / `maxReleasedHours` / `maxOnHoldHours` / `repeatQualityHoldQty`
  - 調整 `SummaryCardGroup :columns="..."`（依 decision 6 討論後決定最終數量）
  - 新增 6 張（或合併為 5 張）卡片：已解除/持續 平均、已解除/持續 最長、品質重複觸發；移除舊「平均 Hold 時長」
  - 「累計 Future Hold」卡加 tooltip（從 i18n 載入）
- [x] 4.2 評估 `frontend/src/shared-ui/components/SummaryCard.vue` 是否需新增 `tooltip` prop 或 slot 支援；若已支援則直接用，否則擴充元件 API
- [x] 4.3 修改 `frontend/src/hold-history/App.vue`：
  - 刪除 `estimateAvgHoldHours()` 函數（L421–445）
  - `summary` computed：移除 `avgHoldHours`；新增 `avgReleasedHours` / `avgOnHoldHours` / `maxReleasedHours` / `maxOnHoldHours`（from `durationData.value`）；新增 `repeatQualityHoldQty`（from `selectedTrendDays.value` 累加）
  - 其餘 8 張既有卡片不動
- [x] 4.4 若有 i18n 檔（`frontend/src/**/i18n/*.{js,json}`），新增 Future Hold tooltip 與品質重複觸發說明的中英文

## 5. 文件更新

- [x] 5.1 更新 `docs/hold_history.md`：補充 Future Hold 時效衰減行為的說明段落，明示「FUTUREHOLDCOMMENTS 會被 MES 清除，`futureHoldQty` 具時效衰減；`repeatQualityHoldQty` 為穩定替代指標」；保留原 PJMES043 SQL 不變
- [x] 5.2 `contract/api_inventory.md`：若新增 duration / trend payload 欄位被視為契約變更，更新對應條目；否則維持不變

## 6. 測試 — 單元

- [x] 6.1 `tests/test_hold_history_service.py`：
  - `get_hold_history_duration()` 新增回傳欄位斷言，四種情境（全 Release / 全 OnHold / 混合 / 空集合）
  - `get_hold_history_trend()` 每日 payload 包含 `repeatQualityHoldQty`（非負整數）
  - `_normalize_trend_day()` 對舊資料（無新欄位）處理後回傳 0，不拋例外
- [x] 6.2 `tests/test_hold_history_sql_runtime.py`：DuckDB runtime `_query_duration()` / `_query_trend()` 新欄位計算正確，含邊界情況（空 spool、全 released、全 on-hold）
- [x] 6.3 `tests/test_hold_dataset_cache.py`：確認新欄位在 spool 讀寫與序列化過程不遺失

## 7. 測試 — Parity

- [x] 7.1 `tests/test_hold_history_sql_parity.py`：新增 Oracle SQL vs DuckDB server runtime 對 AVG / MAX / repeat 欄位的一致性測試
  - 小型 fixture（10–50 筆）逐筆驗證
  - 大型資料（≥ 1000 筆）抽樣驗證，AVG/MAX 誤差 < 0.01hr，repeat 整數完全一致
- [x] 7.2 `tests/test_frontend_hold_history_parity.py`：新增 Server DuckDB vs Client DuckDB-WASM 對 AVG / MAX / repeat 欄位一致性測試
- [x] 7.3 既有 parity 測試（trend 其他欄位、pareto、duration bucket）保持綠燈，確保「只新增不改變」承諾

## 8. 測試 — E2E 與 CI/CD

- [x] 8.1 `tests/e2e/test_hold_history_e2e.py`：
  - 新增斷言：SummaryCards 卡片數符合 spec
  - 新增斷言：四張新卡片（平均/最長 × released/on-hold）數值為有限非負數
  - 新增斷言：「品質重複觸發」卡片存在且為非負整數
  - 新增斷言：Future Hold 卡 tooltip 可見（hover 觸發）
- [x] 8.2 `tests/playwright/data-boundary/`（若存在對應 hold-history spec）：擴充 duration / trend payload 欄位邊界驗證
- [x] 8.3 確認 `.github/workflows/released-pages-hardening-gates.yml` hold-history 頁面 gate 包含本次 payload 擴充
- [x] 8.4 Real-infra-smoke pre-merge gate：確認 `workflow_dispatch` smoke 跑過後端有回傳新欄位且不 5xx（不引入新 endpoint，無需新增 gate）
- [x] 8.5 Route fuzz（`tests/routes/test_fuzz_routes.py`）：確認 POST /query 與 GET /view 對新 payload 欄位的序列化健壯（malicious query_id 或 filter 值不觸發 5xx）
- [x] 8.6 Property-based tests（若 hold-history 已在 `-m property` 範圍內）：確認 AVG/MAX 不變式（非負、AVG ≤ MAX、空集合為 0）；若未納入範圍，新增 hold-history 專屬 property 測試

## 9. 驗收與清理

- [x] 9.1 本機 `./scripts/start_server.sh start` + 前端 dev server 跑起來，實測 Hold History 頁面：
  - 新卡片正確渲染，無佈局破版
  - 切換 hold_type / record_type / reason 時 AVG/MAX/repeat 值隨之更新
  - Future Hold tooltip hover 可見
  - 對照手動抽樣 detail 清單，AVG/MAX 值合理
- [x] 9.2 `grep -rn "avgHoldHours\|estimateAvgHoldHours" frontend/ src/` 確認無殘留舊字串
- [x] 9.3 `pytest tests/ -k hold_history -v` 全數通過
- [x] 9.4 `cd frontend && npx playwright test tests/playwright/` hold-history 相關通過（3 passed / 1 skipped：pareto 導航測試在無 hold data 環境由 test.skip() 主動跳過，非失敗）
- [x] 9.5 `openspec validate hold-history-metric-refinement` 通過
- [x] 9.6 和 Peeler（PJMES043 原作者）確認「品質重複觸發」卡片語意是否符合業務期望；若有調整回到 spec/design 迭代
