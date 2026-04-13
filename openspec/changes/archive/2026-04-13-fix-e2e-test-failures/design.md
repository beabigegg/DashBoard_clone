## Context

2026-04-13 完整 e2e 測試跑完：本地 40 失敗 / 遠端 44 失敗。經逐項根因分析：

| 類別 | 數量 | 比例 |
|------|------|------|
| A 產品代碼 bug | 3（由 1 個根因引發） | 4% |
| B 測試斷言寫錯 | 17 | 21% |
| C 測試健壯度（等待策略） | 4 | 5% |
| D 環境/並行/資源 | 16+ | 19% |

**關鍵發現**：
1. `production_history` async 路徑在 `make_canonical_spool_id(body)` 的 `try/except (KeyError, ValueError)` 內吞掉了驗證錯誤，讓缺參數的請求繞過驗證直接 enqueue。
2. Admin e2e 測試用 `requests.get()` 預設跟隨 redirect，`before_request` hook 回 302 → 重導到 `/portal-shell/` → 拿到 200 HTML → `resp.json()` 失敗。修 14 個。
3. Query-tool / hold-detail 的 Vue SFC 全部正確，selectors 仍有效 — 失敗是 playwright 硬等時機不足。
4. 本次 84 個失敗中，真正的產品 bug 只有 1 個根因。

**目標**：讓兩端 e2e 都 < 5 個 failure，剩下的都是真實可追蹤的狀態。

## Goals / Non-Goals

**Goals**：
- 修掉唯一的產品代碼 bug（production_history async validation gap）
- 修掉所有測試寫法錯誤（admin redirect、response shape、async 回應）
- 強化測試等待策略，移除 flaky 硬 sleep
- 建立 sequential e2e 執行規範，避免並行壓垮 runner
- 提供 local_only marker 讓遠端 target 自動 skip 需本機 worker 的測試

**Non-Goals**：
- 不重寫任何 UI 元件（selectors 全部仍有效）
- 不新增功能或變更 API 回應 envelope 結構
- 不動產品代碼除了 `production_history_routes.py`
- 不處理不在本次失敗列表內的測試

## Decisions

### D1. Production History validation 放在 route 層而非「spool id 生成時偷偷驗證」

**選擇**：在 `api_production_history_query()` 解析 body 後、任何 spool 判斷或 async 決策之前，顯式呼叫 `validate_query_params(body)` 並捕捉 `ValueError` → 400。

**替代方案**：
- A) 讓 `enqueue_production_history_query(body)` 內部驗證 — 拒絕。job_service 層是 enqueue 機制，不該混進 domain validation。
- B) 新寫一個 lightweight validator — 拒絕。`validate_query_params` 已是純函式、可重複呼叫，沒有副作用。重用它零成本。
- C) 保留 `try/except` 吞錯誤、改為在 async job 內驗證 — 拒絕。語義上違反「validation before accept」，使用者會得到誤導的 202 + 稍後 job 失敗。

**理由**：`validate_query_params` 在 sync 路徑已被 `query_production_history()` 透過 `_make_dataset_id` 呼叫（line 537），多呼叫一次純函式可忽略不計。route 層顯式驗證也讓合約更清楚。

### D2. Admin e2e 測試統一加 `allow_redirects=False`，不改 before_request hook

**選擇**：測試檔全部加 `allow_redirects=False`，讓 302 如實保留，現有 `if status == 200: resp.json()` 分支自然不會進入。

**替代方案**：
- A) 改 before_request hook 對 `/admin/api/*` 一律回 401 JSON，不 redirect — 拒絕。該 hook 影響整個 portal 的 UX（未登入跳 portal-shell 是設計意圖），不應為了測試改產品行為。
- B) 測試用 `requests.Session()` 預先登入一次 — 拒絕。目前 `test_admin_auth_e2e.py` 已有 session 測試，但 admin_dashboard/performance/kpi 設計上是「就算未登入也應回 302 或 401，不崩潰」的 smoke check。不該為了測試硬加 session。
- C) 測試改用 `Accept: application/json` header 觸發 hook 的 AJAX 分支（回 401 JSON）— 可行但侵入性較高。`allow_redirects=False` 更單純、一行就解。

### D3. Playwright 顯式等待採 `expect(locator).to_be_visible(timeout=...)` 模式

**選擇**：移除 `page.wait_for_timeout(1500)` 等硬 sleep，換成 `expect(locator).to_be_visible(timeout=30000)`。網路等待保留 `page.expect_response(...)` 原模式。

**替代方案**：
- A) 改 `wait_until="networkidle"` — 拒絕。query-tool 頁面有背景 polling / websocket，networkidle 可能永不到達。
- B) 自訂 `wait_for_vue_mounted()` helper — 拒絕。多此一舉。playwright 的 `expect().to_be_visible()` 本身就是 auto-retry 的，足夠。

### D4. hold-detail 測試改用同檔已有的 `_wait_for_response` helper

**選擇**：重構 `test_hold_detail_calls_summary_distribution_and_lots` 使用 `_wait_for_response(page, lambda r: ..., timeout_seconds=30.0)`（line 205-212 已經在用的模式），順便統一測試風格。

### D5. `local_only` marker 用自動 skip fixture 實作，而非散落各處 `pytest.skip`

**選擇**：在 `tests/e2e/conftest.py` 新增 `autouse=True` fixture，檢查 `_is_external_e2e_target()` 與 `request.node.get_closest_marker("local_only")`，在外部 target 時自動 skip。測試檔只需 `@pytest.mark.local_only`。

**替代方案**：環境變數 `SKIP_LOCAL_ONLY=1` — 拒絕。已有 `_is_external_e2e_target()` 完整偵測，不需再加環境變數。

### D6. Sequential e2e 腳本放在 `scripts/run_e2e.sh`，不動 pytest-xdist

**選擇**：單純的 bash 腳本，先跑本地、再跑遠端（若 `E2E_REMOTE_URL` 已設）。不使用 pytest-xdist / parallel。

**理由**：e2e 本質上是 I/O bound + 單一伺服器對象，並行 = Chromium 進程爆炸。sequential 是正確預設。

## Risks / Trade-offs

| Risk | Mitigation |
|------|-----------|
| `POST /api/production-history/query` 400 vs 202 是 API 契約 BREAKING | 內部唯一消費者 `useProductionHistory.js` 已透過表單驗證先過濾必填欄位。API inventory 更新說明此變更。|
| `allow_redirects=False` 對其他非 admin 測試可能產生副作用 | 只在 admin e2e 3 個檔案改，不碰其他檔 |
| `to_be_visible(timeout=30000)` 若 CI 機器很慢仍可能超時 | 時限維持 30s（playwright 預設同），可視 CI 結果調整 |
| `local_only` marker 若誤用標在 API-only 測試，遠端會 skip 掉應該跑的測試 | 明確 docstring 規範：marker 僅用於「依賴 in-process worker 狀態」的測試 |
| sequential e2e 執行時間比並行長 | 可接受。遠端 19 分 + 本地 22 分 = 41 分，對照並行但不穩定的 22 分 → 41 分可接受。|

## Migration Plan

1. **Step 1 - 產品代碼補丁**：修 `production_history_routes.py`，本地測試 A 類 3 個 test 確認綠燈。
2. **Step 2 - 測試寫法修正**：B1 / B2 / B3 批次改，跑對應檔案測試確認。
3. **Step 3 - 健壯度重構**：C1 / C2 重構，跑對應 browser 測試確認（需要可用的 display/headless）。
4. **Step 4 - 基礎設施**：新增 `scripts/run_e2e.sh`、`conftest.py` fixture、`pytest.ini` marker。
5. **Step 5 - 完整回歸**：用新腳本跑 local + remote sequential，比對失敗數。

**Rollback**：所有變更都是 additive（新加 validate call、新加 fixture、改測試等待策略），單一 git revert 即可回到現況。產品代碼部分若要 rollback 只需把 validate 呼叫註解掉。

## Open Questions

- [ ] 是否需要把 `test_trace_pipeline` 標 `local_only` 之前先確認遠端 RQ worker 的 queue 設定？（若遠端單純沒啟 trace worker，local_only 就是對的決定；若是啟了但狀態不同，可能需要 pre-reset fixture）
- [ ] CI 是否有 runner 規格升級空間？若仍是 8GB RAM，即便 sequential 也可能在某些 browser 測試 peak 時吃緊。
