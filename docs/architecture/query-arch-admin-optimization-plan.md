# 查詢架構收斂 ＆ 管理員頁面優化：分階段執行計劃

> 產生日期：2026-06-30
> 分析方式：多代理調查（後端查詢層 / 快取-spool 層 / 前端查詢模式 / 管理員頁面 4 個 agent）＋ 主控綜合
> 狀態：計劃定稿，作為後續分 phase PR 的「改前基礎」
> 關聯文件：本計劃 **承襲並延續** [`query-dataflow-unification.md`](./query-dataflow-unification.md)（後端 RQ+DuckDB 統一設計），並補上該文件未涵蓋的 **前端查詢收斂** 與 **管理員頁面優化**。

---

## 0. 為何需要這份計劃

專案的 16+ 報表頁面是陸續開發的，查詢相關邏輯「各自為政」。`query-dataflow-unification.md` 已經為**後端重查詢路徑**定出統一方向（路徑 A 純快 / 路徑 B 純 RQ，消除路徑 C 假非同步），且其 P0 地基已落地。但有三塊仍未被任何文件統一管理：

1. **後端查詢的「決策 / 併發 / 參數」中間層** —— 統一設計聚焦在「執行層」（chunk→Arrow→DuckDB），但「要不要轉非同步」「併發閘門有沒有接上」「參數怎麼解析」這層仍分裂。
2. **前端查詢模式** —— `query-dataflow-unification.md` 完全是後端視角，前端 23 個 feature app 的過濾 / 多視圖 / 分頁 / loading 各做各的，無人統管。
3. **管理員頁面的即時性與線上人數準確度** —— 與查詢架構無關，但同屬「整合不足」的技術債。

本計劃把這三塊拆成可獨立推進、可獨立回滾的 PR phase。

---

## 1. Part A（後端）：現況 vs 統一設計的落差盤點

### 1.1 已經統一的（地基，勿動）

| 面向 | 現況 | 證據 |
|---|---|---|
| 回應格式 | 28 個 route 全走 `success_response`/`error_response` | `core/response.py` |
| 前端 API client | 23 個 app 全走 `apiGet`/`apiPost`（去重、CSRF、timeout） | `frontend/src/core/api.ts` |
| 路由 / 權限 | 集中於 portal-shell，單一 auth 守衛 | `frontend/src/portal-shell/router.js:123` |
| 重查詢執行層地基 | `BaseChunkedDuckDBJob` / `query_cost_policy` / `oracle_arrow_reader` 已存在並有 domain 採用 | 見 `query-dataflow-unification.md` §4 已落地 |

### 1.2 尚未統一的缺口（本計劃要收斂的目標）

| # | 缺口 | 現況 | 風險 | 對應 Phase |
|---|---|---|---|---|
| A1 | **併發閘門未全接** | ✅ **已於 Phase A-1 處理。** 經逐一核對：CLAUDE.md 點名的 query-tool/hold/resource/reject 在 `rq-semaphore-wiring` 早已接好（reject 為 cache 層內部 acquire）；該註記已過時。**真正的缺口**是統一 job 核心 `BaseChunkedDuckDBJob.run()` 從未 acquire slot，導致 `*_USE_UNIFIED_JOB=on`（eap_alarm/downtime/material_trace 預設 on）的 always-async 重查詢在 production 裸奔。本計劃的 A-1 PR 已在 base `run()` 的 Oracle fan-out 段中央接線（一次補 6 個 job）+ material_trace override 補一處。 | 🔴 高（已關閉） | Phase A-1 ✅ |
| A2 | **`classify_query_cost` 覆蓋不足** | 僅 4/28 route 走統一成本分類；`CostPolicy` 只定義 `eap_alarm/trace/msd`，其餘吃預設。 | 🟠 中 — 「何種查詢轉非同步」無單一可調政策 | Phase A-2 |
| A3 | **參數解析無 facade** | 每個 route 自刻 `_get_*_args` / `_parse_multi_param` / 日期驗證 / 分頁 sanitize。 | 🟡 中 — 加一個共用過濾欄位要改 N 處 | Phase A-3 |
| A4 | **快取 schema 版本嵌 key 不一致** | `reject_dataset` 的 `_CACHE_SCHEMA_VERSION` **未嵌入 query_id**；升版後舊 parquet 不會孤立，有讀到舊欄位的風險。`resource/yield/hold` 已正確嵌入。 | 🟡 中 — 升版資料正確性 | Phase A-4 |
| A5 | **two-phase key resolution 僅 resource 實作** | superset warmup 復用 + exact-match fallback 只有 `resource_history` 有；reject/yield 30 天內查詢每次 miss 90 天 warmup spool。 | 🟢 低 — 效能而非正確性 | Phase A-4（選做） |

> **更正一則調查誤報**：cache-spool agent 宣稱「9 個 spool namespace 漏在 `spool_routes._ALLOWED_NAMESPACES` 導致 HTTP 400」。經核對 `spool_routes.py:20-29`，白名單含 `downtime_analysis_base_events`/`downtime_analysis_job_bridge` 等，且 `material_trace`/`production_history`/`query_tool_*` 多屬內部 DuckDB runtime view 或批次快取，**本就不經 `/api/spool` 下載**，不需進此白名單。此項**非缺陷**，不列入計劃。

---

## 2. Part A（前端）：查詢模式收斂

> 此節為 `query-dataflow-unification.md` **未涵蓋** 的範圍。

### 2.1 現況

| 面向 | 一致性 | 細節 |
|---|---|---|
| API client | ✅ 100% | 全走 `core/api.ts` |
| 過濾邏輯 | ⚠️ 分裂 | 10 app 用 `useFilterOrchestrator`，13 app 自刻 composable |
| 多視圖 fan-out staleness guard | ✗ 1/23 | per-endpoint staleness dict 只有 `eap-alarm/useEapAlarmViews.js:61` 有；其他多視圖頁面快速切過濾會「舊請求覆蓋新結果」 |
| 分頁 | ✗ dead code | `shared-composables/usePaginationState.ts` 定義了但 0 採用；14+ app 各自刻分頁狀態 |
| Loading / Error / 匯出 | ⚠️ 三種風格 | 命名與粒度不一，難抽共用 UI 行為 |

### 2.2 收斂目標（按「低風險高影響」優先）

| # | 目標 | 風險 | 對應 Phase |
|---|---|---|---|
| F1 | 把 `eap-alarm` 的 per-endpoint staleness guard 抽成共用 composable（`useViewFanout`），推廣到其他多視圖頁面 | 🟢 低、影響高（修競態 bug） | Phase F-1 |
| F2 | 決議 `usePaginationState.ts`：要嘛補齊讓 3+ app 採用，要嘛刪除 dead code | 🟢 低 | Phase F-1 |
| F3 | 過濾邏輯逐步收斂到 `useFilterOrchestrator`（13 個自刻 app 評估遷移成本，分批） | 🟡 中 | Phase F-2（後續） |

---

## 3. Part B：管理員頁面優化

### 3.1 線上人數 —— 現況與業界做法

**現演算法**（`core/login_session_store.py:307`，已核實）：
```sql
COUNT(*) WHERE logout_time IS NULL AND last_active >= now - 30min
```

**準確度問題**：
1. 前端**無自動心跳** → 閒置 30 分即算離線（分頁仍開著也一樣）。
2. TTL 30 分鐘**硬編碼**，無法依需求調整。
3. server 重啟會 reopen session（`login_session_store.py:245`）造成失真。
4. **多 worker 下各查各的本機 SQLite**，無跨進程聚合。
5. 不分 active / idle。

**業界（GA / Discord / Slack-style presence）怎麼做**：

| 做法 | 定義 | 適用 |
|---|---|---|
| GA「活躍使用者(30 分鐘)」 | 最近 30 分鐘內有事件 | **engagement 指標**（= 現系統的窗口，但現系統 UI 卻標成「在線」，語意錯置） |
| Presence（真正「現在在線」） | **heartbeat + 短窗口(1~5 分鐘)**，窗口內有心跳才算在線 | **即時在線數** |
| Redis sorted set | `ZADD presence <now> <user>`；`ZCOUNT presence (now-window) +inf` 取數；`ZREMRANGEBYSCORE` 清過期 | **儲存黃金模式**：跨 worker 一致、自動過期、O(log n) |
| WebSocket 連線數 | 活躍 socket 數 | 最精準但需長連線，對報表平台過重 |

**目標設計（採 Redis presence pattern + 輕量心跳，並拆兩個指標）**：

- **指標拆分**：UI 同時呈現
  - 「**在線**」= 最近 ~5 分鐘有心跳（presence，業界主流定義）
  - 「**活躍(30 分鐘)**」= GA 式 engagement（沿用現窗口，正名）
- **底層**：以 Redis sorted set（score = last-seen epoch，member = emp_id）取代「各 worker 各查 SQLite」→ 天然跨 worker 一致、自動過期。
- **前端心跳**：portal-shell 加輕量定時 heartbeat（visibility-aware：分頁隱藏時降頻或暫停），更新 Redis presence。
- **TTL 可調**：心跳間隔與 presence/active 窗口改為環境變數（`PRESENCE_WINDOW_SECONDS`、`ACTIVE_WINDOW_SECONDS`、`HEARTBEAT_INTERVAL_SECONDS`），並補 `env-contract.md` + `env.schema.json` enum/default（依 CLAUDE.md 環境變數契約規則）。
- **SQLite 角色**：保留作為登入歷史 / 稽核與 DAU 計算來源（落地持久），presence 即時數改讀 Redis；Redis 不可用時 fail-open 退回 SQLite 演算法。

### 3.2 系統效能監控 —— 現況與即時性目標

**現況**：`MetricsHistoryCollector` 每 30 秒背景快照（`METRICS_HISTORY_INTERVAL=30`）+ admin 頁 30 秒輪詢；query latency 為各 worker in-memory deque（重啟即丟、無法跨 worker 聚合）。

**即時性目標（先做低風險者）**：
- **採集間隔可調**：把 30 秒硬值改為環境變數（如 `METRICS_HISTORY_INTERVAL`，已存在則改為對齊前端輪詢），admin 頁輪詢頻率對齊，避免採集/顯示落差。
- **（後續，較重）SSE 推送**：以 Server-Sent Events 把指標推到 admin 頁取代輪詢；列為後續 phase，非本輪。

---

## 4. 分階段 PR 路線圖

> 每個 Phase = 一個獨立 PR，可獨立 review / 回滾。Phase 之間無強制依賴者標「並行可」。
> 工作量：S = 半天、M = 1–2 天、L = 3–5 天

| Phase | 範圍 | 內容摘要 | 工作量 | 風險 | 依賴 |
|---|---|---|---|---|---|
| **本 PR** | 計劃基礎 | 本文件（改前基礎） | — | — | — |
| **A-1** | 後端併發 | 逐一核對並補齊 `acquire_heavy_query_slot` wiring；補對應 stress-soak-report（CLAUDE.md 併發模組規則） | M | 🔴 高收益 | — |
| **A-2** | 後端決策 | 為所有 async domain 定義 `CostPolicy`，route 統一走 `classify_query_cost`；移除散落的 `*_ASYNC_DAY_THRESHOLD` env | M | 🟠 | A-1 後較佳 |
| **A-3** | 後端參數 | 抽 `core/route_helpers.py`（`parse_pagination`/`parse_date_range`/`parse_multi_param`），逐 route 遷移 | M | 🟡 | 並行可 |
| **A-4** | 快取一致性 | `reject_dataset` schema 版本嵌入 query_id；（選做）reject/yield two-phase key | S–M | 🟡 | 並行可 |
| **F-1** | 前端競態 | 抽 `useViewFanout` staleness guard 並推廣；處理 `usePaginationState` dead code | M | 🟢 高收益 | 並行可 |
| **F-2** | 前端過濾 | 13 個自刻過濾 app 分批遷移 `useFilterOrchestrator` | L | 🟡 | F-1 後 |
| **B-1** | 線上人數 | Redis presence（sorted set）+ 前端心跳 + active/idle 拆分 + 可調 TTL + fail-open SQLite | L | 🟡 | 並行可 |
| **B-2** | 監控即時性 | 採集間隔/輪詢頻率可調對齊；（後續）SSE 推送 | S（SSE 另計 M） | 🟢 | 並行可 |

**建議推進順序**：本 PR → A-1（止血）→ B-1 ＆ F-1（並行，使用者最有感）→ A-2/A-3/A-4 → F-2 → B-2(SSE)。

---

## 5. 通用工程約束（所有 phase 適用）

- **Feature flag + 回滾**：行為性改動以 flag 預設 off 上線；併發/旗標相關須依 CLAUDE.md 加 `tier-floor-override` 與 stress-soak-report。
- **CDD 流程**：每個 phase 走 `/cdd-new`，`cdd-kit gate --strict` 過關；行為移除/資料形狀變更前先 grep 全測試樹並跑完整 pytest（`gate --strict` 只跑 bounded ladder）。
- **環境變數契約**：新增 env 須同步 `env-contract.md`（pin default）+ `env.schema.json`（enum+default）。
- **OpenAPI 同步**：動到 endpoint table/schema/schema-version 後重生 `contracts/openapi.json` 與 `contracts/api/openapi.json`。
- **前端共用元件**：動 `MultiSelect` 等 12-app 共用元件須先 grep 消費者，且只能加性變更。

---

## 6. 待核實項目（實作前必須先確認，避免依誤報行動）

1. ~~**A-1 前置**：逐一核對 `acquire_heavy_query_slot` 真實接線狀態。~~ ✅ **已完成**：legacy 路徑（query-tool/hold/resource/reject/production/wip）全已接；真缺口在統一核心 `BaseChunkedDuckDBJob.run()`，A-1 PR 已補。**仍待辦**：在具備 Redis + Oracle 的環境跑真實負載，驗證 `peak_concurrent ≤ HEAVY_QUERY_MAX_CONCURRENT`（mock 結構證明不足以放行 production），並補正式 CDD change + stress-soak-report。
2. **A-2 前置**：確認目前哪些 domain 已實際走 `classify_query_cost`（agent 報 4/28，需點數驗證）。
3. **B-1 前置**：確認 Redis 在所有部署環境（gunicorn + RQ worker）皆可用且 `REDIS_ENABLED` 一致；確認多 worker 部署實況（worker 數）。
4. **F-1 前置**：列出所有「多視圖且無 staleness guard」的 app（hold-overview、wip-overview、downtime-analysis 等）作為推廣對象清單。

---

## 附錄：關鍵檔案索引

**後端**
- `src/mes_dashboard/core/global_concurrency.py`（heavy query slot，A-1 參考實作）
- `src/mes_dashboard/core/query_cost_policy.py`（`classify_query_cost` / `CostPolicy`，A-2）
- `src/mes_dashboard/core/response.py`（統一回應，勿動）
- `src/mes_dashboard/core/login_session_store.py:307`（線上人數演算法，B-1）
- `src/mes_dashboard/core/metrics_history.py`（30 秒快照 collector，B-2）
- `src/mes_dashboard/routes/admin_routes.py`（admin API）
- `src/mes_dashboard/services/user_usage_kpi_service.py:115`（KPI / active_sessions）

**前端**
- `frontend/src/core/api.ts`（統一 client，勿動）
- `frontend/src/eap-alarm/composables/useEapAlarmViews.js:61`（staleness guard 正向範例，F-1）
- `frontend/src/shared-composables/useFilterOrchestrator.ts`（過濾編排，F-2）
- `frontend/src/shared-composables/usePaginationState.ts`（dead code，F-1 處理）
- `frontend/src/admin-dashboard/`（admin SPA，B-1/B-2）
- `frontend/src/portal-shell/`（心跳掛載點，B-1）
</content>
</invoke>
