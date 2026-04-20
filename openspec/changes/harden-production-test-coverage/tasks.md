## 1. 共用基礎設施

- [x] 1.1 擴充 `frontend/tests/playwright/_auth.js` 新增 `mockApiError(page, urlPattern, status, options)` helper，支援 `{ body, delay, headers }`，預設 body 依 `src/mes_dashboard/core/response.py` 的錯誤碼常數產生
- [x] 1.2 在 `_auth.js` 補一個 `waitForIdleUi(page)` helper（封裝「loading overlay 消失 + button 非 busy」的複合等待），供 resilience spec 共用
- [x] 1.3 新建 `tests/routes/_fuzz_payloads.py` 匯出 `MALICIOUS_INPUTS` 常數（至少 6 筆：SQL 特殊字元、100k 字元、Unicode/emoji、whitespace-only、倒置日期、負數分頁）
- [x] 1.4 在 `tests/integration/conftest.py` 確認（或補上）`local_redis` fixture 支援 `DEBUG SLEEP` 並為 function-scoped，避免跨測試互相干擾

## 2. Priority 1 — Playwright resilience specs（pre-merge gate）

- [x] 2.1 建立 `frontend/tests/playwright/resilience/` 目錄
- [x] 2.2 撰寫 `api-failure.spec.js`：對 Query Tool、Reject History、Hold Overview 分別注入 500 / 503+Retry-After / `route.abort('timedout')`，驗證 overlay 收回、error toast 顯示、button 重新 enabled、無 stale data 殘留
- [x] 2.3 撰寫 `slow-network.spec.js`：以 `setTimeout(5000)` 延遲關鍵查詢 API，驗證頁級 `LoadingOverlay` 500ms 內出現與消失、按鈕 `aria-busy` 同步、動畫遵守 `prefers-reduced-motion`
- [x] 2.4 撰寫 `rapid-interaction.spec.js`：驗證（a）查詢按鈕連點 5 次只發 1 個請求、（b）查詢中匯出按鈕 disabled 或顯示 guard toast、（c）匯出按鈕連點 3 次只觸發 1 個 download
- [x] 2.5 撰寫 `browser-history.spec.js`：驗證 back / forward / reload-mid-flight 在至少 2 個頁面（Query Tool 與 Reject History）上 URL state 正確還原
- [x] 2.6 對每支 spec 執行 **mutation check**：暫時移除對應的前端 handler（如 `useRequestGuard`、`error toast` dispatch、URL state 寫入），確認 spec FAIL；測試完再還原並在 PR 描述附驗證紀錄
- [x] 2.7 本地跑 `cd frontend && npx playwright test tests/playwright/resilience/` 全綠
- [x] 2.8 加入 `.github/workflows/frontend-tests.yml` pre-merge job 跑 resilience 目錄

## 3. Priority 2 — Playwright data-boundary specs（pre-merge gate）

- [x] 3.1 建立 `frontend/tests/playwright/data-boundary/` 目錄
- [x] 3.2 撰寫 `malformed-input.spec.js`：對 Query Tool 與 Reject History 輸入 SQL-style payload、100k 字串、Unicode/emoji、倒置日期，驗證 client validator 阻擋或 API 回 `VALIDATION_ERROR`，且無 500 / 無白畫面
- [x] 3.3 撰寫 `empty-result.spec.js`：對 Hold Overview / Reject History / Query Tool 的主 API 用 `page.route` 回空結果，驗證每頁顯示 `empty-state` 元件；export 按鈕 disabled 或改文案
- [x] 3.4 Mutation check：暫時移除空結果的 empty-state 渲染與 inverted date validator，確認 spec FAIL，記錄於 PR
- [x] 3.5 本地跑 `cd frontend && npx playwright test tests/playwright/data-boundary/` 全綠
- [x] 3.6 確認這兩支 spec 被 pre-merge CI 收錄

## 4. Priority 3 — Backend integration tests（nightly gate）

- [x] 4.1 撰寫 `tests/integration/test_oracle_error_codes.py`：用 `unittest.mock.patch` 注入 `cx_Oracle.DatabaseError` 攜帶 ORA-01017 / ORA-12514 / ORA-01555，驗證 response envelope error code 對應、circuit breaker 計數、retryable 分類與 `Retry-After` 標頭
- [x] 4.2 撰寫 `tests/integration/test_redis_timeout_fallback.py`：用 `local_redis` fixture + `DEBUG SLEEP` 觸發 socket timeout，驗證 filter cache fallback 到 `_ProcessLevelCache`、route 仍回 200；timeout 解除後下一次 request 正常重連
- [x] 4.3 撰寫 `tests/integration/test_race_conditions.py`：以 `threading.Barrier(2)` 觸發（a）同 cache key 並發寫入、（b）相同 `(user, report_type, params_hash)` 的並發 export、（c）spool read 與 cleanup 的 race
- [x] 4.4 全部三檔掛 `@pytest.mark.integration_real`
- [x] 4.5 Mutation check：逐檔暫時移除對應 handler（ORA-code 映射分支、Redis fallback try/except、spool lock 機制），確認測試 FAIL；PR 描述紀錄證據
- [x] 4.6 本地跑 `conda run -n <env> pytest --run-integration-real tests/integration/test_oracle_error_codes.py tests/integration/test_redis_timeout_fallback.py tests/integration/test_race_conditions.py -v` 全綠
- [x] 4.7 在 `.github/workflows/*.yml` 新增或擴充 nightly job 跑這三檔（使用現有 `--run-integration-real` 流程）

## 5. Priority 4 — Route 測試輸入模糊化

- [x] 5.1 盤點 `tests/routes/test_*_routes.py` 中接受查詢條件的 route test（預估 10–15 檔），輸出清單
- [x] 5.2 對每個盤點到的 test 檔加 `@pytest.mark.parametrize("payload", MALICIOUS_INPUTS)` 包一個 `test_<route>_rejects_malicious_input` case
- [x] 5.3 斷言每筆 malicious payload 回 400/422，`error.code == 'VALIDATION_ERROR'`，response 是合法 UTF-8 JSON，且不產生 500
- [x] 5.4 若 parametrize 暴露真實 bug（route 真的 500），於同 PR 補驗證邏輯，或拆 follow-up issue 並在本次 PR 用 `xfail` 標記
- [x] 5.5 本地跑 `conda run -n <env> pytest tests/routes/ -v` 全綠

## 6. 文件與 CI

- [x] 6.1 在 `contract/` 或現有測試規範文件補一段說明「resilience / data-boundary / fault integration 三層定位」，避免未來誤把 happy path 與 resilience 混在同一檔
- [x] 6.2 在 `CLAUDE.md` 專案規則「Project Commands」附近補一行 Playwright resilience spec 的本地執行指令
- [x] 6.3 確認 `.github/workflows/frontend-tests.yml` 的 job timeout 足以跑完 resilience + data-boundary（估計 +3 分鐘）
- [x] 6.4 確認 nightly workflow 把 3 個新 integration test 正確收錄並且失敗會 block nightly build

## 7. 實機全量驗證（Full Stack Smoke）

- [x] 7.1 啟動完整服務：`./scripts/start_server.sh start`；確認 `server-ops` 檢查 Gunicorn / Redis / Oracle 連線健康（讀 `/api/health`）
- [x] 7.2 跑後端全量：`conda run -n <env> pytest tests/ -v` （3466 passed, 131 skipped）
- [x] 7.3 跑後端 integration real：`conda run -n <env> pytest --run-integration-real tests/integration/ -v` （20 passed）
- [x] 7.4 跑前端 Vitest 全量：`cd frontend && npm test` （270 passed）
- [x] 7.5 跑 Playwright 全量（含新 resilience + data-boundary）：`cd frontend && npx playwright test`（禁跑 `playwright install`，用 `~/.cache/ms-playwright/`）
- [x] 7.6 收集所有 fail/error/skip 輸出，逐案填入下一步的 triage 表

## 8. Triage：測試問題 vs 程式 Bug（每筆 failure 必做）

- [x] 8.1 建立 `openspec/changes/harden-production-test-coverage/triage.md` 作為 triage log；每筆失敗案例紀錄：`{ test_id, 錯誤摘要, root_cause_category, 證據, 後續動作 }`
- [x] 8.2 對每筆 failure 執行 triage 流程：
      - **步驟 A**：讀 test 的斷言與期望行為；比對 spec 的 `#### Scenario`。若 test 期望與 spec 不符 → **TEST_BUG（測試問題）**
      - **步驟 B**：手動在瀏覽器 / curl / Flask client 重現該情境；觀察實際行為是否違反 spec 的 WHEN/THEN。若實際行為違反 spec → **CODE_BUG（程式 bug）**
      - **步驟 C**：若 test 假設的 mock shape 與 `src/mes_dashboard/core/response.py` envelope 不一致 → **TEST_BUG**
      - **步驟 D**：若 race / timing 相關且無法穩定重現 → **FLAKY_TEST**（歸入 TEST_BUG，但需加 `@pytest.mark.flaky` 或 `expect.poll` 重寫）
- [x] 8.3 **TEST_BUG 處理**：在同一個 PR 中修正測試（調整斷言、修 mock shape、改用顯式等待），重跑驗證通過；triage.md 紀錄「修正前 vs 修正後」差異
- [x] 8.4 **CODE_BUG 處理**：
      - [x] 8.4.1 不在本次 PR 修程式 bug — 保持測試 FAIL 或暫時 `@pytest.mark.xfail(strict=False, reason='...')`，讓 regression 持續被看見
      - [x] 8.4.2 為每個 CODE_BUG 開一個新 OpenSpec change：`openspec new change fix-<bug-slug>`，內容包含 repro 步驟、受影響的 route/service、預期 vs 實際行為、建議修法方向
      - [x] 8.4.3 在 triage.md 裡登記新 change 的名稱與路徑，並在本次變更的 proposal.md 底部加一段「Discovered Regressions」連結這些 follow-up change
- [x] 8.5 所有 failure 必須歸類完畢（沒有「待確認」殘留）才進入下一步
- [x] 8.6 Triage 完成後重跑 7.1–7.5，確認剩下的 FAIL 只有已登記的 `xfail` CODE_BUG；其餘全綠

## 9. PR 切分與最終驗收

- [ ] 9.1 PR #1：Priority 1（resilience specs + `_auth.js` helper）
- [ ] 9.2 PR #2：Priority 2（data-boundary specs）
- [ ] 9.3 PR #3：Priority 3（backend integration + nightly job）
- [ ] 9.4 PR #4：Priority 4（route fuzz parametrize + `_fuzz_payloads.py`）
- [ ] 9.5 每個 PR 描述中列出該批次的 mutation check 紀錄與 triage 結論摘要
- [ ] 9.6 最終驗收：
      - [ ] `openspec verify --change harden-production-test-coverage` 通過
      - [ ] 所有新測試 green（或標記為 `xfail` 指向已登記的 CODE_BUG follow-up change）
      - [ ] `triage.md` 每筆 failure 有明確分類與後續動作
      - [ ] `Discovered Regressions` 區段列出所有 CODE_BUG 衍生的 follow-up change 與連結
