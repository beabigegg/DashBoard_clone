## Why

2026-04-13 完整 e2e 測試套件（本地 + 遠端 `10.1.8.31:13006`）執行後共 **84 個失敗**（本地 40、遠端 44）。深入分析後，只有 1 個是真正的產品代碼 bug，其餘皆為測試寫法、測試健壯度、CI 執行策略問題。必須將「真正的 bug 訊號」從「噪音」中分離出來，讓 e2e 測試成為可信的品質閘道。

## What Changes

- **BREAKING（API 契約修正）**：`POST /api/production-history/query` 在缺少必要參數（`pj_types`、`start_date`、`end_date`）或日期區間超過 `MAX_DATE_RANGE_DAYS=730` 時，SHALL 回傳 HTTP 400 而非 HTTP 202。目前非同步路徑略過 `validate_query_params` 直接 enqueue，導致無效請求被當成 async job 接受。
- 修正 14 個 admin e2e 測試預設跟隨 redirect 的寫法錯誤（`requests.get()` 需要 `allow_redirects=False`，否則最終命中 `/portal-shell/` 的 HTML 200，再 `resp.json()` 爆炸）。
- 修正 `test_type_options_returns_pj_types_list` 斷言格式（API 回傳 `{data:{items:[...]}}`，測試仍在檢查過時的 `pj_types` key）。
- 修正 `test_summary_accepts_within_limit_range` 斷言，接受 yield-alert `/summary` 合法的 HTTP 202（cache miss enqueue）。
- 強化 `test_query_tool_ui_ux_e2e.py` 三個測試的顯式 visibility 等待，替換依賴 1.5s 硬 sleep 的脆弱寫法（selectors 經驗證仍有效，問題是 Vue hydration 時機）。
- 重構 `test_hold_detail_calls_summary_distribution_and_lots` 使用同檔已存在的 `_wait_for_response` helper，取代 `wait_until="commit"` + 自行 polling 的雙重等待機制。
- 新增 `scripts/run_e2e.sh` 強制 sequential 執行本地/遠端 e2e，避免並行 Chromium 進程導致記憶體競爭與 `test_global_connection` 的 120s ReadTimeout。
- 新增 `local_only` pytest marker 與 `tests/e2e/conftest.py` 的 skip fixture，將 `test_trace_pipeline_e2e.py`（需要 in-process RQ worker）在遠端 target 時自動 skip。
- 補強 `_pick_hold_reason` / `_pick_workcenter` helper 的空陣列檢查，缺測試資料時 skip 而非 fail。

## Capabilities

### New Capabilities

（無）

### Modified Capabilities

- `production-history-async-worker`：新增「Query route validates required parameters before async enqueue」requirement。現況：spool 未命中 → 直接 enqueue → 回 202（無論參數是否完整）。修正後：在 enqueue 前呼叫 `validate_query_params(body)`，ValueError → 回 400。
- `e2e-test-coverage`：
  - Admin e2e 測試必須使用 `allow_redirects=False` 避免 JSON parsing 於 HTML。
  - Browser e2e 測試必須使用顯式 visibility / response 等待，不得依賴 fixed `wait_for_timeout`。
  - Response shape 斷言必須匹配 `success_response` envelope 的實際結構。
  - 非同步 API 的「合法 accept」斷言必須同時接受 200/202。
- `ci-test-orchestration`：
  - 提供 sequential e2e 執行腳本，禁止並行多 target（本地 + 遠端）對抗同一 runner 的記憶體池。
  - 支援 `local_only` marker 自動 skip 需要 in-process 服務的測試。

## Impact

**產品代碼**（1 檔）：
- `src/mes_dashboard/routes/production_history_routes.py`（約 5 行改動）

**測試代碼**（8 檔）：
- `tests/e2e/test_admin_dashboard_e2e.py`
- `tests/e2e/test_admin_performance_e2e.py`
- `tests/e2e/test_admin_user_usage_kpi_e2e.py`
- `tests/e2e/test_production_history_e2e.py`
- `tests/e2e/test_yield_alert_e2e.py`
- `tests/e2e/test_query_tool_ui_ux_e2e.py`
- `tests/e2e/test_wip_hold_pages_e2e.py`
- `tests/e2e/test_mid_section_defect_e2e.py`
- `tests/e2e/test_trace_pipeline_e2e.py`

**測試基礎設施**（3 檔）：
- `tests/e2e/conftest.py`（資源檢查 + skip marker fixture）
- `pytest.ini`（註冊 `local_only` marker）
- `scripts/run_e2e.sh`（新檔）

**API 消費者影響**：
- `POST /api/production-history/query` 的呼叫者（目前僅內部 `useProductionHistory.js` composable）在缺參數時將收到 400 而非 202。由於 composable 透過 UI 表單驗證已先過濾必填欄位，實際影響面為零；但直接打 API 的工具/腳本需配合修正。

**預期回歸效益**：
- 本地失敗：40 → ~3（減 ~37）
- 遠端失敗：44 → ~2（減 ~42）
- 剩餘為真正需要測試資料或已知環境差異的少數案例
