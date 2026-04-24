## Why

Hold History 頁面目前的主軸是「日期區間內的 Hold 事件回顧」，所有資料錨點都是 `hold_day`——無法回答現場每天最關心的兩個即時問題：

1. **「此刻」有多少 lot 還在 Hold？**（不限 `hold_day`，也要包含 3 個月前 hold 至今未 release 的老 lot）
2. **「今天」發生了什麼？**（今天新增、今天 release、今天品質重複觸發——全部聚焦在今日一天）

目前頁面既有資料範圍受 `hold_day BETWEEN start AND end` 限制，無法在區間外取到仍在 hold 的老 lot；Record Type 篩選雖可過濾 on_hold，但仍要受 hold_day 區間限制。把兩個業務語意硬塞在同一組 UI（日期區間 + Record Type 多選）導致使用者認知負擔高、且數字容易誤讀。

此次變更新增「當日」快捷模式，以**當下快照 + 今日事件**為主軸，與既有「區間回顧」並列；同時清理區間模式的認知複雜度（移除 Record Type 篩選、移除最末日相關卡片、加入 Detail 欄寬調整）。

## What Changes

### 模式切換架構
- 在 FilterBar 新增 **模式切換**：「區間查詢 / 當日」
- URL 新增 `mode=range|today` 參數；切換模式時清空不適用的 URL params
- 模式切換透過專屬 composable（或擴充 `useFilterOrchestrator`）管理狀態轉換

### 區間查詢模式（既有模式的簡化）
- **移除 Record Type 多選篩選**（`RecordTypeFilter.vue`）；既有 spool 的資料等同 `new`（hold_day 在區間內），已完整覆蓋需求
- **移除「最末日新增 Hold」卡片**（原設計作為「當日」概念的延伸，現在由當日模式完整承接）
- 保留 Daily Trend / Pareto / Duration / Detail 等圖表的現況語意

### 當日模式（新增）
- 日期鎖定：起訖 = 今日，以 **Server SYSDATE（UTC+8）+ 07:30 班別分界** 為準
- 隱藏 Daily Trend（單日無趨勢意義）
- 保留 Pareto / Duration 圖，與新的 Record Type 連動（語意重新定義）
- **新增 Record Type 篩選（新語意）**：
  - `on_hold`：**所有**現況仍在 Hold 的 lot（**不限** hold_day）
  - `new`：**今日** 新增 Hold（hold_day = today）
  - `release`：**今日** Release（release_day = today）
- 頂部 SummaryCards：
  - **On Hold 總量**（當下全體，非區間）
  - **今日新增**（hold_day = today）
  - **今日 Release**（release_day = today）
  - **今日 Future Hold**（hold_day = today AND `IS_FUTURE_HOLD=1`；Q1.3 確認為 interpretation (a)——直覺語意）
  - **On Hold 平均時長**（AVG(HOLD_HOURS) WHERE RELEASETXNDATE IS NULL）
  - **On Hold 最長時長**（MAX(HOLD_HOURS) WHERE RELEASETXNDATE IS NULL）
- **Auto-refresh**：前景時每 N 秒自動重打當日快照 API（N 由 env 控制，建議 60–180 秒）

### 獨立 API
- 新增 `POST /api/hold-history/today-snapshot`（無參數或僅 `hold_type`）
  - 回傳 `{ query_id, summary, pareto: {...}, duration: {...}, list: {...} }`
  - 內部以 `hold_day >= 特定日期`（由當下 on_hold 最早 hold_day 決定）重建 spool，避開既有 `hold_history/query` 的區間限制
  - 獨立 cache 命名空間 `hold_today:*`，TTL 建議 60 秒（配合 auto-refresh）
- 或者：以 `hold_history/query` + 特殊參數（`mode=today`）復用，但獨立 API 邊界更清楚 → **採獨立 API（Decision 1）**

### Detail Table 加強
- 新增欄位寬度調整（拖拉欄邊界）
- **不** 做欄位 filter（Q3.2 已決定跳過）
- 寬度設定**不持久化**：同一頁面內切頁維持、整頁切走重置（Q3.3）

### 說明文字（共通要求）
- 所有按鈕、篩選、圖表標題 / 副標、卡片 tooltip 必須清楚標示「現在看到的資料是在什麼篩選條件下」——UX review 時必檢項

### 回歸防護
- 大規模改動 UX / 新增 API，需納入所有既有 CI/CD gate：parity、E2E、real-infra smoke、route fuzz、released pages gate、soak、PBT
- 保證區間模式既有行為不變（Record Type 移除除外）；當日模式全新測試
- 模式切換的 URL state transition 邏輯必須有獨立測試覆蓋

## Capabilities

### New Capabilities
- `hold-history-today-snapshot-api`：新的即時快照 API 規範（`POST /api/hold-history/today-snapshot`），資料來源獨立於既有 dataset cache，生命週期與語意不同

### Modified Capabilities
- `hold-history-api`：既有 `query` / `view` endpoint 保持不變；但新增 today-snapshot 為並列第三個 endpoint
- `hold-history-page`：FilterBar 加入模式切換；區間模式移除 Record Type 篩選；當日模式新增卡片組、隱藏 Trend、重新詮釋 Record Type；Detail table 新增欄寬調整

## Impact

**前提**
- 本 change **依賴** `hold-history-metric-refinement` 的「品質重複觸發」與 AVG/MAX 指標邏輯已 land（當日模式部分卡片會複用）。建議 `metric-refinement` 先上線，本 change 後上線

**後端**
- 新增 `src/mes_dashboard/routes/hold_history_routes.py` 中 `POST /api/hold-history/today-snapshot` 路由與對應 service 函式
- 新增 `src/mes_dashboard/services/hold_today_snapshot_service.py`（或擴充 `hold_dataset_cache.py` 以獨立 namespace 支援）
- 新增 `src/mes_dashboard/sql/hold_history/today_snapshot.sql`：以 `RELEASETXNDATE IS NULL OR release_day = today OR hold_day = today` 為取料條件；partition / 計算邏輯沿用 `base_facts.sql` 結構
- 確認 Oracle SYSDATE（UTC+8 已驗證）作為「今日」基準
- 新增 env 設定：`HOLD_TODAY_AUTO_REFRESH_SECONDS=60`、`HOLD_TODAY_CACHE_TTL_SECONDS=60`

**前端**
- `frontend/src/hold-history/App.vue`：引入模式切換狀態、依 mode 條件渲染 / 取資料；移除既有區間模式的 Record Type 節點；新增當日模式專屬 summary card set、auto-refresh timer（頁面可見時啟動、切走停止）
- `frontend/src/hold-history/components/FilterBar.vue`：新增模式切換按鈕（或 Tab）、當日模式下 disable 日期輸入
- `frontend/src/hold-history/components/SummaryCards.vue`：接受 `mode` prop，依 mode 呈現不同卡片組
- `frontend/src/hold-history/components/RecordTypeFilter.vue`：當日模式新語意（label 文字不同）；區間模式不呈現
- `frontend/src/hold-history/components/DetailTable.vue`：欄寬拖拉功能（非持久化）
- 移除 / 簡化：區間模式移除 `RecordTypeFilter` 使用、移除「最末日新增 Hold」卡片
- URL state 管理：擴充既有 URL sync 或新增專屬 composable，處理 `mode` 參數與模式切換時的 params 清理

**路由契約與文件**
- `contract/api_inventory.md`：新增 `POST /api/hold-history/today-snapshot` 條目
- `contract/api_development_contract.md`：若新 API 型態不符既有 pattern（例如沒有 query_id），補充說明
- `docs/hold_history.md`：補充當日模式的語意與資料邊界

**測試 — 回歸防護（重點）**

*單元測試*
- `tests/test_hold_today_snapshot_service.py`（新）：today-snapshot service 的邊界（無 hold、全 release、跨時區邊界）
- `tests/test_hold_history_routes.py`：新增 POST /today-snapshot route 測試（含 rate limit / payload shape / error shape）
- `tests/test_hold_history_service.py`：確認既有 service 因 Record Type 移除而未破壞

*Parity*
- `tests/test_frontend_hold_history_parity.py`：當日模式前後端一致（若當日模式有本地 compute；否則標註 N/A）

*E2E*
- `tests/e2e/test_hold_history_e2e.py` 擴充：
  - 模式切換 URL 正確變化
  - 當日模式卡片數與語意
  - Record Type 在當日模式下的三種語意（on_hold 全體、new 今日、release 今日）
  - Auto-refresh 在背景啟動 / 停止
  - 區間模式 Record Type 節點已移除

*Playwright Resilience*
- `tests/playwright/resilience/api-failure.spec.js` 擴充：當日模式 API 掛掉時的降級（顯示錯誤 / 保留上次快照）

*Route fuzz*
- `tests/routes/test_fuzz_routes.py`：新增 POST /today-snapshot 的 malicious input（超長 hold_type、非法 mode 值等）

*Real-infra smoke*
- `.github/workflows/` 中的 real-infra-smoke pre-merge gate：**必須** 把新 endpoint 納入 smoke dispatch
- Soak test（`.github/workflows/soak-tests.yml`）：當日模式 auto-refresh 穩定性（長時間跑不 memory leak）
- Stress test：auto-refresh 在多人並發下 Oracle 連線不爆

*PBT*
- 若有相關 invariant（例如 today-snapshot 的 `onHoldTotal >= todayNew - todayRelease`），新增 property-based test

*Released pages hardening gate*
- `released-pages-hardening-gates.yml` 必跑 hold-history 頁面的完整路徑（包含當日模式）

**風險**
- 新增 API 和獨立 cache 增加後端資源消耗；auto-refresh 可能在多人線上時加重 Oracle 負擔 → soak / stress 測試必須涵蓋
- 模式切換的 URL state 管理容易踩邊界（切走又回來、瀏覽器前進後退）→ E2E 重點覆蓋
- 當日模式「on_hold 全體」會撈到很老的 lot，可能資料量大 → 需要 limit / pagination / 初始資料量 smoke 測試
- UX 改動大，使用者需要教育 → UI copy / tooltip 必須清楚

**依賴**
- 無新後端套件
- 前端可能需要 column-resize 的輕量 library（或自己實作 pointer event 拖拉）；需 UX review 決定
- 依賴 `hold-history-metric-refinement`（品質重複觸發、AVG/MAX 卡片邏輯共用）
