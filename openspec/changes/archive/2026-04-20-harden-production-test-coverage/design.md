## Context

MES Dashboard 已累積 237 個後端測試檔 + 62 個 Vitest 單元/composable + 5 支 Playwright E2E。盤點後發現：

- **Playwright 僅 5 支**且全部為 happy path：`hold-overview`、`query-tool`、`query-tool-url-state`、`reject-history`、`job-abandon-on-unload`。只有 `query-tool-url-state.spec.js:7-37` 使用過 `page.route` fulfill mock data，但從未 fulfill 錯誤 (status ≥ 400)。
- **後端 integration tier（12 檔）**已涵蓋 circuit breaker、pool exhaustion、cache lifecycle、cross-worker sharing、async job timeout、RQ crash recovery，但 **mock 的是 generic `Exception`，不是 `cx_Oracle.DatabaseError` 攜帶 ORA-* code**；Redis 在預設 conftest 是 `REDIS_ENABLED=false`，真實 timeout 行為沒跑過。
- **Route 層測試**覆蓋 400 / 403 / 404 / 503 envelope，但輸入驗證測試通常只餵「missing / empty / wrong type」，沒餵 SQL 特殊字元、Unicode、極長字串、超範圍日期。
- **既有 spec 可被擴充**：`e2e-test-coverage`、`backend-integration-test-coverage`、`real-environment-integration-tests` 都已存在，本變更屬於新增 requirements 到前兩者。
- **基礎設施已就緒**：`@playwright/test` 已安裝、`playwright.config.js:5-13` 有 retries / trace / video、`tests/integration/conftest.py` 已有 `gunicorn_workers` / `local_redis` / `temp_spool_dir` fixtures。

核心約束：
- **禁止執行 `playwright install`**（瀏覽器位於 `~/.cache/ms-playwright/`，CLAUDE.md 全域 hard rule #2）
- **禁止 commit `.env`**
- Python 必須透過 `conda run -n <env>` 執行
- 新測試必須遵循 i18n 同步紀律（若 UI 文案改動）
- Loading 狀態必須遵守三層政策（`LoadingOverlay tier=...` / `BlockLoadingState` / `ui-btn is-loading`）
- API 錯誤回應必須從 `core/response.py` 的常數對照，不能硬編 string

## Goals / Non-Goals

**Goals:**
- 將測試覆蓋率從「happy path 契約驗證」提升到「能攔截生產環境 regression」的水準。
- 新增的 Playwright spec 可在 pre-merge 5 分鐘內完成（用 `page.route` mock，不壓 Flask/Oracle）。
- 新增的後端 integration tests 可跑在 nightly `--run-integration-real` job（可接受 +5 分鐘）。
- 每個新測試必須有 **mutation check 證明它真的會 fail** —— 避免寫出 test pass 但實際沒驗到錯誤路徑的假驗證。
- 對既有 10–15 個 route test 檔加 parametrize 模糊化輸入，確保所有 route 對惡意 payload 都以 `VALIDATION_ERROR` 回應而非 500。

**Non-Goals:**
- 不導入視覺回歸（Percy / Chromatic / Playwright snapshot diff）。
- 不引入 chaos framework（Toxiproxy、litmus）—— 用 `page.route` + `unittest.mock.patch` 已能涵蓋 80% 情境。
- 不補 CSRF / token 過期中途攔截測試 —— 獨立成另一個 change。
- 不重構既有 happy path spec —— 只新增 resilience / boundary / fault 維度的新 spec。
- 不改動 `core/response.py` 的 error code 定義 —— 新測試是驗證「現有契約被正確執行」。
- 不改動 `playwright.config.js` 的 retries 或 timeout —— 共用 60s timeout 與 `chromium` project 即可。

## Decisions

### D1: Playwright fault injection 走 `page.route` + `route.fulfill`，不引入 proxy

- **選擇**：在 Playwright spec 開頭 `page.route('**/api/<pattern>', route => route.fulfill({ status: 500, body: ... }))`。
- **替代 A（棄）**：Toxiproxy / mitmproxy 當 reverse proxy 注入故障 → 過重、需額外服務、CI 設定複雜。
- **替代 B（棄）**：真實讓後端 500 → 破壞測試環境、難以 deterministic。
- **理由**：`query-tool-url-state.spec.js:7-37` 已在用相同技術，開發者熟悉；Playwright `route.fulfill` 可精準控制 status、delay（`await new Promise(r => setTimeout(r, 5000))`）、body。

### D2: 新 Playwright specs 放獨立子目錄，不混進現有 spec

- **選擇**：`frontend/tests/playwright/resilience/` 與 `frontend/tests/playwright/data-boundary/`。
- **替代（棄）**：加在既有 `hold-overview.spec.js` 等檔內 → 檔案過大、職責混淆、grep 難定位。
- **理由**：Playwright `testDir: './tests/playwright'` 會自動遞迴收錄子目錄；分目錄便於 CI 條件執行（例如 pre-merge 跑 `resilience/`，nightly 加跑全量）。

### D3: 後端 Oracle ORA-* 錯誤用 `unittest.mock.patch` 注入，不依賴真實 DB

- **選擇**：在 `tests/integration/test_oracle_error_codes.py` 內用 `patch.object(engine, 'execute')` 拋出 `cx_Oracle.DatabaseError('ORA-01017: invalid username/password')`。
- **替代（棄）**：用 testcontainers 跑真實 Oracle XE → 啟動 5+ 分鐘、CI 環境負擔重。
- **理由**：`cx_Oracle.DatabaseError` 本身是純 Python class，可實例化並攜帶 ORA-code 訊息；目的是驗證 **我們的 error handler 對 ORA-* code 的解讀是否正確**，不是驗證 Oracle server 行為。真實 Oracle 留給既有 `--run-integration-real` job。

### D4: Redis timeout fallback 用 `local_redis` fixture + socket-level 延遲

- **選擇**：在 `tests/integration/test_redis_timeout_fallback.py` 使用既有 `local_redis` fixture 啟動真實 redis-server，再以 `redis.Redis(socket_timeout=0.1)` 搭配 `DEBUG SLEEP 5` 指令強制 timeout。
- **替代 A（棄）**：`unittest.mock.patch('redis.Redis.get', side_effect=TimeoutError)` → 不足以驗證 connection pool 的重試與 reconnect。
- **替代 B（棄）**：`iptables -A OUTPUT -p tcp --dport <redis> -j DROP` → 需要 root、CI 環境不允許。
- **理由**：`DEBUG SLEEP` 是 Redis 原生指令、deterministic；既有 `local_redis` fixture 已包辦啟動與清理；可驗證 filter_cache / realtime_equipment_cache 的 `_ProcessLevelCache` fallback 路徑。

### D5: Race condition 用 `threading.Thread` + `threading.Barrier` 控制並發時點

- **選擇**：在 `tests/integration/test_race_conditions.py` 用 `Barrier(n=2)` 讓兩條 thread 在同一指令同時釋放，觸發 cache write 或 spool file 命名競態。
- **替代（棄）**：`asyncio.gather` → Python 的 GIL 使 I/O 並發不等於 race，需要真正的 thread 觸發底層 lock / file 競態。
- **理由**：`Barrier` 是 stdlib、無額外依賴；可 deterministic 觸發 race 並驗證 `try_acquire_lock` / spool filename dedup 的行為。

### D6: Route fuzz 用 `@pytest.mark.parametrize` 共享 payload fixture

- **選擇**：新增 `tests/routes/_fuzz_payloads.py` 匯出 `MALICIOUS_INPUTS` 常數（list of 8 payloads），每個 route test 檔 `parametrize` 套上去。
- **替代（棄）**：導入 `hypothesis` property-based testing → 過重、學習成本高、CI 時間爆炸。
- **理由**：固定 8 個代表性 payload 已能覆蓋 SQL 特殊字元 / 極長字串 / Unicode / 日期異常 / 負數；deterministic、易 reproduce、易維護。每個 route 約 +8 個 test case，整體 CI 時間增加 < 30 秒。

### D7: Mutation check 紀律寫進 tasks.md 驗收標準，不自動化

- **選擇**：在 tasks.md 的 DoD 明列「提交前執行 mutation check — 拿掉對應 error handler → test 應 FAIL」，審 PR 時確認執行過。
- **替代（棄）**：導入 `mutmut` / `cosmic-ray` 自動化 mutation testing → 跑一次小時級、false positive 多、不適合此次 scope。
- **理由**：核心目的是逼開發者**確認新測試有效**，而非長期掛在 CI 監控；人工紀律 + PR 要求即足夠。

### D8: Helper `mockApiError` 寫在 `_auth.js`，不另開檔

- **選擇**：擴充 `frontend/tests/playwright/_auth.js` 匯出 `mockApiError(page, urlPattern, status, { body, delay } = {})`。
- **替代（棄）**：新開 `_fault.js` → 過度切分、import 分散。
- **理由**：`_auth.js` 已是 shared helper 收納處，新增一個 export 不影響既有 api。

### D9: Triage 分 `TEST_BUG` / `CODE_BUG` / `FLAKY_TEST` 三類，follow-up 另開 OpenSpec change

- **選擇**：新測試實作完後以真實服務（`./scripts/start_server.sh start`）跑全量 pytest + Vitest + Playwright。對每筆失敗走四步驟 triage：(A) 比對 spec Scenario → 不符就是 TEST_BUG；(B) 手動重現 → 違反 spec 就是 CODE_BUG；(C) mock shape 與 `core/response.py` envelope 不一致 → TEST_BUG；(D) timing 不穩 → FLAKY_TEST。`TEST_BUG` 於本 PR 修；`CODE_BUG` 保持 `xfail` 讓 regression 可見，另開 `fix-<bug-slug>` OpenSpec change 處理。
- **替代 A（棄）**：發現 bug 就於同 PR 順手修 → 違反 CLAUDE.md「A bug fix doesn't need surrounding cleanup」原則，模糊本次變更範圍，也讓 review 變大。
- **替代 B（棄）**：CODE_BUG 直接寫成 issue / TODO 註解 → 資訊分散、沒納入 OpenSpec 的 spec-driven 追蹤；未來 regression 時無法快速對到 requirement。
- **替代 C（棄）**：遇到 failure 就直接 `xfail` 不做 triage → 會把 TEST_BUG 跟 CODE_BUG 都掃進地毯下，失去本次變更的價值。
- **理由**：triage 是本次變更的核心產物之一 —— 我們投入測試的目的就是**抓到真實 bug**，必須有明確流程把發現物轉換成可追蹤的修復工作。三分類讓每筆 failure 都有明確 owner；CODE_BUG 走 OpenSpec new change 則確保修復本身也受 spec-driven 紀律約束，而不是散落的 hotfix。記錄在 `triage.md` + proposal 的 `Discovered Regressions` 區段，可在 archive 時永久保留這批發現物的來源脈絡。

## Risks / Trade-offs

- **[Playwright mock 漂移] `page.route` mock 的 response shape 若與真實後端 envelope 不同步，測試可能通過但實際壞掉。** → 緩解：mock body 的結構統一從 `src/mes_dashboard/core/response.py` 的 helper 推導，並在 spec 開頭加註釋指向常數；後端 envelope 若變動，API contract test (`tests/test_api_contract.py`) 會先 fail 作為早期警示。
- **[ORA-code 驗證不等於真實 Oracle]  `patch` 注入 `cx_Oracle.DatabaseError` 可能跟真實 Oracle 拋出的行為（例如：connection 是否自動歸還 pool）有細節差異。** → 緩解：本次新增是「error handler 對 ORA-code 解讀」的驗證；真實 Oracle 的連線歸還行為由既有 `test_oracle_connection_leak.py` 與 `--run-integration-real` nightly 負責，責任分層清楚。
- **[Redis DEBUG SLEEP 影響並行 test] 若多個 test 共享同一個 `local_redis`，`DEBUG SLEEP` 會阻塞所有其他 test。** → 緩解：`test_redis_timeout_fallback.py` 使用 `function`-scoped `local_redis` fixture 並明確宣告 serial 執行（`@pytest.mark.serial` 或在 conftest 限制）。
- **[Race test flaky] `Barrier` 控制的並發測試可能在 CI slow runner 上偶發失敗。** → 緩解：`Barrier(timeout=5)` 明示超時、retry=1（pytest-rerunfailures）、失敗時自動截取 thread dump。
- **[Route fuzz 暴露既有 bug]  既有 route 可能對某些惡意 payload 確實回 500 而非 `VALIDATION_ERROR`。** → 這是**期望的 regression exposure**，不是風險。實作時若發現，按 Priority 4 的 task 在同一 PR 修補或拆成 follow-up issue。
- **[Nightly 時間拉長] 新增 3 個 integration test 會把 nightly job 拉長 ~5 分鐘。** → 可接受；若超過 10 分鐘門檻，再評估平行化。
- **[Playwright spec 跑在 CI 的穩定性] 新 resilience specs 會頻繁使用 `page.route` 與 `waitForResponse`，timing 敏感。** → 緩解：採用 `expect.poll` / `expect().toBeVisible({ timeout })` 顯式等待，避免 `wait_for_timeout(N)`（符合 `e2e-test-coverage` 既有 requirement）。

## Migration Plan

- **Phase 1 (PR #1)** — Priority 1 Playwright resilience specs（4 支）+ `_auth.js` helper。加入 `frontend-tests.yml` pre-merge gate。
- **Phase 2 (PR #2)** — Priority 2 Playwright data-boundary specs（2 支）。同樣 pre-merge gate。
- **Phase 3 (PR #3)** — Priority 3 Backend integration tests（3 支）+ nightly job 配置。
- **Phase 4 (PR #4)** — Priority 4 Route fuzz parametrize（影響 10–15 檔）+ `_fuzz_payloads.py`。若 parametrize 暴露出真實 bug，於同 PR 修補或拆 follow-up。
- **回滾策略**：每個 PR 獨立；若某批 spec 在 CI 頻繁 flaky，可透過 `.github/workflows/*.yml` 中 matrix exclude 暫時停用，不影響其他 phase。

## Open Questions

- 是否需要把 resilience specs 從 pre-merge 降到 nightly？（目前設計為 pre-merge，若 CI 時間超過 5 分鐘再評估。）
- Route fuzz 的 `MALICIOUS_INPUTS` 是否要涵蓋 CSV 注入（`=SUM(A1)`）？目前先不加，若專案未來有 CSV 匯入 API 再補。
- `test_race_conditions.py` 的 export spool race 情境需要 `QUERY_SPOOL_DIR` 的真實共享磁碟；單一 CI runner 足夠，但若未來改成分散式 runner 需重新評估。
