## Why

目前 E2E 與後端整合測試大量落在「正確輸入 → 正確輸出」的契約層，對使用者異常操作（返回鍵、連點、reload 中途）、外部系統故障（API 500 / 503、Oracle ORA-* 連線錯誤、Redis timeout）、資料邊界（空結果 UI、極長輸入、Unicode、SQL 特殊字元）的瀏覽器層與端到端覆蓋率不足。實驗室環境能通過並不代表生產環境能撐得住，必須補上故障注入與邊界壓測才能真正捕捉 regression。

## What Changes

- **新增 Playwright resilience specs（4 支）**：`api-failure`（mock 500 / 503 / Retry-After）、`slow-network`（延遲回應驗證 loading 三層）、`rapid-interaction`（連點防呆、查詢中匯出被擋）、`browser-history`（back / forward / reload-mid-flow 保留 URL state）。
- **新增 Playwright data-boundary specs（2 支）**：`malformed-input`（SQL 特殊字元、極長字串、Unicode、空白、日期格式異常）、`empty-result`（mock API 回空，驗證每頁 empty-state 正確渲染而非白畫面）。
- **新增後端 integration 測試（3 支，掛 `integration_real` marker）**：`test_oracle_error_codes.py`（真實 `cx_Oracle.DatabaseError` with ORA-01017 / ORA-12514 / ORA-01555）、`test_redis_timeout_fallback.py`（真實 Redis socket timeout → in-memory fallback）、`test_race_conditions.py`（同 key cache 並發寫入、spool 檔名衝突）。
- **既有 route 測試擴充輸入模糊化**：對每個接受查詢條件的 route 加 `@pytest.mark.parametrize`，跑 6–8 個惡意 payload（長字串、emoji、SQL 特殊字元、超範圍日期、負數 limit/offset），斷言皆回 `VALIDATION_ERROR` 而非 500 / traceback。
- **新增 Playwright helper**：`frontend/tests/playwright/_auth.js` 擴充 `mockApiError(page, pattern, status, options)`，封裝 `page.route` + `route.fulfill` 常見故障注入樣板。
- **Reverse-verification 紀律**：新測試提交前必須執行「臨時拿掉對應錯誤處理 → 測試應 FAIL」的 mutation check，避免 test pass 但實際未驗證到目標路徑。
- **CI 整合**：新 Playwright specs 加入 pre-merge gate（`frontend-tests.yml` / `e2e-tests.yml`），新 backend integration 掛 nightly `--run-integration-real` job。
- **實機全量驗證 + Triage 流程**：實作完成後以 `./scripts/start_server.sh start` 啟動真實服務，跑前後端所有測試。對每筆失敗逐一歸類為 `TEST_BUG`（測試寫錯 → 於同 PR 修正）或 `CODE_BUG`（測試真的抓到程式 bug → 不在本 PR 修，另開 follow-up OpenSpec change 並於 `triage.md` 登記）。

## Capabilities

### New Capabilities

無新增 capability — 本變更屬既有測試覆蓋度 spec 的進一步硬化，不引入新語意。

### Modified Capabilities

- `e2e-test-coverage`: 新增「瀏覽器層故障注入」「瀏覽器歷史與連點 / 邊界輸入」「空結果 UI 正確渲染」三類新 requirements；現有「Every user-facing page SHALL have at least one e2e test」保留不動。
- `backend-integration-test-coverage`: 新增「Oracle ORA-* 特定錯誤碼整合測試」「Redis 真實 timeout fallback 整合測試」「Cache 與 spool 並發競態整合測試」「Route 模糊化輸入 parametrize」四類新 requirements；現有 pool / circuit breaker / cache lifecycle requirements 保留不動。

## Impact

- **新增程式檔**（約 ~9 個測試檔 + 1 helper）：
  - `frontend/tests/playwright/resilience/api-failure.spec.js`
  - `frontend/tests/playwright/resilience/slow-network.spec.js`
  - `frontend/tests/playwright/resilience/rapid-interaction.spec.js`
  - `frontend/tests/playwright/resilience/browser-history.spec.js`
  - `frontend/tests/playwright/data-boundary/malformed-input.spec.js`
  - `frontend/tests/playwright/data-boundary/empty-result.spec.js`
  - `tests/integration/test_oracle_error_codes.py`
  - `tests/integration/test_redis_timeout_fallback.py`
  - `tests/integration/test_race_conditions.py`
  - `frontend/tests/playwright/_auth.js`（擴充 helper，不新增檔）
- **修改既有**：`tests/routes/test_*_routes.py`（約 10–15 檔加 parametrize fuzz case）。
- **CI 設定**：`.github/workflows/e2e-tests.yml` / `frontend-tests.yml` 確認新 specs 被收錄；nightly job 新增跑 `tests/integration/test_oracle_error_codes.py` / `test_redis_timeout_fallback.py` / `test_race_conditions.py`。
- **依賴**：不需要新套件。利用既有 `@playwright/test`、`pytest`、`cx_Oracle` / `oracledb`、`redis-py`、integration conftest 的 `gunicorn_workers` / `local_redis` / `temp_spool_dir` fixtures。
- **風險**：新增的 Oracle / Redis 真實測試會拉長 nightly 時間（估計 +2–5 分鐘）；Playwright resilience specs 使用 `page.route` mock，不會壓到 Flask/Oracle，pre-merge 成本可控。
- **不包含**：視覺回歸（Percy / Chromatic）、chaos framework（Toxiproxy）、CSRF 驗證補強 — 留待後續獨立 change。


## Discovered Regressions

The following pre-existing PRODUCT_BUG was uncovered during triage (not introduced by this change):

| Bug | Description | Follow-up Change |
|-----|-------------|-----------------|
| Query Tool equipment tab `aria-current` not restored after reload | After hard reload, tab button lacks `aria-current="page"` even when URL params are correct. Test marked `test.fixme` in `query-tool-url-state.spec.js:45`. | [fix-query-tool-equipment-tab-url-state](../fix-query-tool-equipment-tab-url-state/) |
