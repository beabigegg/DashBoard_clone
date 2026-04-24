## 1. 前置與相依

- [x] 1.1 確認 `hold-history-metric-refinement` 已合入 main（或至少 feature branch merge 過），以便共用 AVG / MAX / 品質重複觸發計算邏輯
- [x] 1.2 UX review：確認當日模式卡片順序、mode 切換 UI（Tab / 按鈕群 / Radio）、auto-refresh 視覺提示（倒數、脈衝或無提示）
- [x] 1.3 業務方確認：auto-refresh 間隔（建議 60s）、on_hold 資料量上限（建議 10000 lots）、Tooltip 文案
- [x] 1.4 新增 env 設定：`HOLD_TODAY_AUTO_REFRESH_SECONDS=60`、`HOLD_TODAY_CACHE_TTL_SECONDS=60`、`HOLD_TODAY_MAX_SNAPSHOT_ROWS=10000`、`HOLD_TODAY_MODE_ENABLED=true`（feature flag）

## 2. Backend — 新增 Today Snapshot API

- [x] 2.1 新增 `src/mes_dashboard/sql/hold_history/today_snapshot.sql`：
  - 取料 WHERE：`RELEASETXNDATE IS NULL OR release_day = today OR hold_day = today`（使用 Oracle SYSDATE 推算 today 與 07:30 班別分界）
  - 欄位結構與 `base_facts.sql` 對齊（CONTAINERID, LOT_ID, HOLDREASONNAME, QTY, HOLD_HOURS, HOLD_TYPE, IS_FUTURE_HOLD, RN_FUTURE_REASON, FUTURE_HOLD_FLAG 等）
- [x] 2.2 新增 `src/mes_dashboard/services/hold_today_snapshot_service.py`：
  - `execute_today_snapshot(hold_type, record_type, reason, duration_range, page, per_page)` 主函式
  - 獨立 cache namespace `hold_today:*`，TTL = `HOLD_TODAY_CACHE_TTL_SECONDS`
  - 套用 limit = `HOLD_TODAY_MAX_SNAPSHOT_ROWS`；若超量回傳 `_meta.truncated = true`
  - 回傳 `{ query_id, summary, reason_pareto, duration, list }`（無 trend）
  - Summary 卡片各值：`onHoldTotalCount`、`onHoldTotalQty`、`todayNewQty`、`todayReleaseQty`、`todayFutureHoldQty`（interpretation a：`IS_FUTURE_HOLD=1 AND hold_day=today`）、`onHoldAvgHours`、`onHoldMaxHours`
- [x] 2.3 新增 `src/mes_dashboard/routes/hold_history_routes.py` 中 `POST /api/hold-history/today-snapshot`：
  - 複用既有 `success_response` / `validation_error` helper（遵守 API 契約 Rule 1.1）
  - 輸入驗證：`hold_type`、`record_type`、`reason`、`duration_range`、`page`、`per_page`
  - Route 本身 thin，呼叫 service（遵守 API 契約 Rule 1.3）
  - 異常情境：cache miss + Oracle 不可用 → 503 + `database_unavailable`
- [x] 2.4 更新 `contract/api_inventory.md`：新增 `POST /api/hold-history/today-snapshot` 條目（遵守 API 契約 Rule 1.4）
- [x] 2.5 更新 `docs/hold_history.md`：新增當日模式章節，說明資料邊界、SYSDATE 使用、07:30 分界在當日語意下的意涵

## 3. Backend — 既有 Endpoint 調整

- [x] 3.1 `src/mes_dashboard/services/hold_history_service.py`、`hold_dataset_cache.py`：確認 `record_type` 參數仍可接受（API 向後相容）；無需改 SQL 或邏輯
- [x] 3.2 `src/mes_dashboard/routes/hold_history_routes.py`：確認 `POST /query` 和 `GET /view` 接受 `record_type` 參數（defaults to `new`），不破壞既有 API 客戶端

## 4. Frontend — FilterBar 與模式切換

- [x] 4.1 修改 `frontend/src/hold-history/components/FilterBar.vue`：
  - 新增 mode 切換元件（建議按鈕群或 Tab）
  - 當 mode = today 時 disable `start_date` / `end_date` 輸入
  - 新增 mode toggle 的 tooltip
- [x] 4.2 擴充 `frontend/src/hold-history/App.vue` 狀態管理：
  - 新增 `mode` reactive state，綁 URL `mode` 參數
  - `handleModeChange(newMode)` 清空不適用 URL params、呼叫對應 API
  - 區間模式：維持現行 `POST /query` → `/view` 流程
  - 當日模式：呼叫 `POST /today-snapshot`，不啟動 spool eligibility 檢查
- [x] 4.3 URL state：
  - `mode=range|today` 讀寫
  - 模式切換時的 param 清理邏輯（見 design.md Decision 5）
  - 前進後退時讀 URL mode 還原狀態

## 5. Frontend — SummaryCards 模式感知

- [x] 5.1 修改 `frontend/src/hold-history/components/SummaryCards.vue`：
  - 新增 `mode` prop（`'range' | 'today'`）
  - 根據 mode 渲染不同卡片組（range 沿用 metric-refinement 的 10 卡；today 用新 7 卡）
  - 每張卡片加 tooltip 區分語意
- [x] 5.2 `App.vue` 的 `summary` computed：依 mode 組合對應欄位

## 6. Frontend — Record Type 語意轉換

- [x] 6.1 修改 `frontend/src/hold-history/components/RecordTypeFilter.vue`：
  - 接受 `mode` prop；當 mode = range 時隱藏整個元件
  - 當 mode = today 時顯示新 label：
    - `on_hold` → 「現況 on hold（全體）」
    - `new` → 「今日新增」
    - `release` → 「今日 Release」
  - 每選項加 tooltip 說明篩選條件
- [x] 6.2 App.vue：today 模式改變 record_type 時打 today-snapshot API（可能要重打或帶 param）

## 7. Frontend — Trend 隱藏 / Pareto & Duration 連動

- [x] 7.1 `App.vue` template：mode = today 時不渲染 `<DailyTrend>`；layout 自動 reflow
- [x] 7.2 Pareto / Duration / Detail 的 data source：today 模式下一律從 today-snapshot 回傳的物件讀取，不從既有 durationData / paretoData / detailData（可共用 ref 但切 mode 時清空）
- [x] 7.3 EmptyState：today 模式下若 record_type 組合無資料，顯示「今日無符合條件的 lot」訊息

## 8. Frontend — Auto-refresh

- [x] 8.1 `App.vue` 新增 composable（或獨立 `useAutoRefresh.js`）：
  - 接受 `intervalMs` 與 `fetchFn`
  - `document.visibilityState === 'hidden'` 時暫停
  - `visibilitychange` 事件監聽恢復
  - unmount / mode 切換時 clear timer
  - 失敗 retain last snapshot + 顯示 stale indicator
- [x] 8.2 UI：auto-refresh 倒數或脈衝提示（依 UX review 決定）
- [x] 8.3 Env 讀取：interval 從 `/api/config` 或 server-rendered config 取得，預設 60s

## 9. Frontend — Detail Table 欄寬

- [x] 9.1 修改 `frontend/src/hold-history/components/DetailTable.vue`：
  - grid-template-columns 或 column-width 可動態調整
  - pointer event 拖拉邊界（pointerdown / pointermove / pointerup）
  - state 存 Vue ref（非 localStorage）
  - 換頁時 widths 維持；unmount 自動消失
  - touch device fallback：無拖拉、預設寬
- [x] 9.2 CSS：為 column boundary 加 resize cursor 視覺提示

## 10. Feature Flag 與 Rollout

- [x] 10.1 新增 feature flag `HOLD_TODAY_MODE_ENABLED`（env + server render 到前端）
- [x] 10.2 前端依 flag 決定是否顯示 mode toggle；flag = false 時沿用舊 range-only UI
- [x] 10.3 預設 flag = true，但留退路以便快速 disable

## 11. 測試 — 單元

- [x] 11.1 新增 `tests/test_hold_today_snapshot_service.py`：
  - Snapshot 基礎語意：on_hold 全體、今日新增、今日 release
  - 邊界：清晨 07:29 vs 07:31 的日切行為
  - 邊界：全 release、全 on_hold、混合
  - Limit 應用：資料超過 10000 時 `_meta.truncated = true`
  - hold_type / record_type / reason / duration_range filter 套用
- [x] 11.2 新增 `tests/test_hold_history_routes.py` 擴充：`POST /today-snapshot` HTTP 200 / 503 / 422 各情境
- [x] 11.3 既有 `tests/test_hold_history_service.py` / `test_hold_history_routes.py`：確認 record_type 參數 API 相容保留

## 12. 測試 — Parity 與 E2E

- [x] 12.1 E2E `tests/e2e/test_hold_history_e2e.py` 擴充：
  - Mode toggle 切換與 URL 變化
  - Range 模式：RecordTypeFilter 不存在、最末日新增 Hold 卡不存在
  - Today 模式：卡片組正確、DailyTrend 隱藏、Pareto/Duration 隨 RecordType 變動
  - Auto-refresh 啟動 / 停止 / 失敗降級
  - Browser 前進後退還原模式
  - Detail table 欄寬拖拉、換頁維持、unmount 重置
- [x] 12.2 Playwright `tests/playwright/resilience/api-failure.spec.js` 擴充：today API 失敗時頁面不白屏
- [x] 12.3 Playwright `tests/playwright/data-boundary/`：today snapshot payload 邊界驗證

## 13. 測試 — CI/CD Regression Hardening

- [x] 13.1 `.github/workflows/` real-infra-smoke：把 `POST /api/hold-history/today-snapshot` 納入 Stage 4a dispatched smoke list；斷言 200 + envelope + summary keys
- [x] 13.2 `.github/workflows/soak-tests.yml`：新增 scenario 模擬 30 分鐘持續 60 秒間隔打 today-snapshot；驗證 Oracle pool 穩定、Redis TTL 行為正常
- [x] 13.3 `.github/workflows/stress-tests.yml`：加入 today-snapshot 多人並發測試
- [x] 13.4 `.github/workflows/released-pages-hardening-gates.yml`：確保 hold-history 頁面 gate 跑通雙模式
- [x] 13.5 `tests/routes/test_fuzz_routes.py`：新增 today-snapshot 路由的 malicious input 測試
- [x] 13.6 PBT（`pytest -m property`）：若合適（例如 `onHoldTotal >= todayNew - todayRelease` 類不變式），新增 property test

## 14. 驗收與清理

- [x] 14.1 本機跑 `./scripts/start_server.sh start` + 前端 dev server：
  - 區間模式：RecordTypeFilter 不見、最末日新增 Hold 不見、其他 10 卡存在
  - 當日模式：7 卡存在、Trend 不見、auto-refresh 每 60 秒刷新、切 tab 暫停
  - Mode 切換 URL 正確、前進後退還原
  - Detail table 欄寬可拖拉、換頁維持
- [x] 14.2 `grep -rn "最末日新增" frontend/` 確認無殘留（除了歷史 commit 訊息）
- [x] 14.3 `pytest tests/ -k "hold_history or hold_today" -v` 全通過
- [x] 14.4 `cd frontend && npx playwright test` hold-history 相關全通過
- [ ] 14.5 Real-infra-smoke `workflow_dispatch` 手動觸發一次，確認新 endpoint 納入並通過
- [ ] 14.6 Soak local 5 分鐘跑通 (`./scripts/soak_local.sh`)；CI weekly soak 首跑確認
- [x] 14.7 `openspec validate hold-history-today-mode` 通過
- [x] 14.8 UX 最終 review：所有按鈕 / 篩選 / 卡片文案 / tooltip 清楚表達資料來源
- [x] 14.9 業務方試用一週，收集回饋；必要時微調 auto-refresh 間隔或卡片組
