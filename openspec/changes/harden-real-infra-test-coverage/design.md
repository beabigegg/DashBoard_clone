## Context

本提案承接 `2026-04-20-harden-production-test-coverage` 留下的三個缺口（見 proposal Why）。事實核對確認：

- **Oracle 測試全部 mock**：`tests/integration/test_oracle_error_codes.py` 用 `patch.object(engine, 'execute', side_effect=cx_Oracle.DatabaseError('ORA-01017...'))`（上一個 change 的 D3 決策）、`tests/test_oracle_pool_exhaustion.py:6` 直接 `side_effect=DatabasePoolExhaustedError`、`tests/test_oracle_error_path.py:13-19` 服務邊界 monkeypatch、`tests/test_oracle_connection_leak.py:29-67` 全是 `_make_mock_engine()`——但檔頭 docstring 第 4 行寫「Real-Oracle connection leak detection (session kill, listener stop, network flap) is tracked separately under the **future integration_real suite**」。這個 future suite 從未落地。
- **`integration_real` 已有真實 subprocess 測試**：`tests/integration/conftest.py:128-180` 有真 `redis-server` fixture、`:184-279` 有真 gunicorn fixture、`test_redis_chaos.py:1-12` 真的 SIGKILL redis、`test_real_multi_worker.py` 跑真 gunicorn——**但沒有真 Oracle**。基建缺口是 Oracle container 與 network fault injection。
- **soak 完全不存在**：`tests/stress/` 是 spike test（`test_cross_module_stress.py:40-41` 把 Timeout 計為 success、`:224` 接受 200/500/503——spike 下可接受，但不能捕捉漸進式 leak）。搜尋專案無任何 `soak` marker、無任何 `_metrics` endpoint、無任何時序量測 artifact。
- **pre-merge gate 現況**（`backend-tests.yml:16,26,51-52`）：ignore `tests/stress`；`integration_real` 在 conftest `pytest_collection_modifyitems` 預設 skip；`backend-tests.yml:85` 明確 `if: schedule || workflow_dispatch`。三個真實整合測試（`test_multi_worker_concurrency.py` / `test_redis_chaos.py` / `test_real_multi_worker.py`）因此 0 分鐘貢獻給 pre-merge。
- **既有基建可重用**：`gunicorn_workers`、`local_redis`、`temp_spool_dir` fixtures 已在 `tests/integration/conftest.py`；pytest `integration_real` 閘門與 `--run-integration-real` 流程已建立；`@pytest.mark.multi_worker` marker 已註冊且 stress 有平行機制 `backend-tests.yml:132-167`。

核心約束（沿用 `harden-production-test-coverage`）：
- **禁止執行 `playwright install`**（瀏覽器位於 `~/.cache/ms-playwright/`，CLAUDE.md hard rule #2）
- **禁止 commit `.env`**（hard rule #3）
- Python 透過 `conda run -n mes-dashboard` 執行（hard rule #1）
- 新增 endpoint 必須用 `core/response.py` helpers（契約 1.1）
- 若新增 endpoint 必須同步更新 `contract/api_inventory.md`（契約 1.4）
- 架構/文件變動必須驗證至 source（契約 4.1–4.6）

## Goals / Non-Goals

**Goals:**

- **G1**：提供真實 Oracle driver + 真實 TCP socket 的故障注入測試套件，覆蓋 mock 層無法驗證的情境（session kill、listener stop、snapshot too old、network flap 下的 pool 歸還與 driver 重連）。
- **G2**：提供可量測的 soak 工作負載，能偵測 pool / spool / Redis / RSS / circuit breaker 的漸進式 regression；跑完產出時序 artifact 供 regression bisect 使用。
- **G3**：以數據（stability measurement）決定 pre-merge gate 是否升級，不是憑感覺；達不到門檻時保留 nightly 並針對每個 flakiness 根因開 follow-up change。
- **G4**：所有新測試附 mutation check 證明它真的會 FAIL；新 endpoint 附安全性測試（gate 失效時拒絕連線）。
- **G5**：遵循 `harden-production-test-coverage` 相同的 triage 三分類（TEST_BUG / CODE_BUG / FLAKY_TEST）；CODE_BUG 另開 `fix-<slug>` OpenSpec change。

**Non-Goals:**

- 不修正「前端 CI 只跑 3 檔」的 glob bug — 獨立 `fix-frontend-ci-test-glob` change 處理（事實核對已確認 57 檔被漏掉，但與本提案基建無依賴）。
- 不重寫 stress 斷言的寬容度（Timeout→success、接受 500/503）— 獨立 `fix-stress-assertions-leniency` change 處理。
- 不把 stress 納入 pre-merge — stress 本質是容量探測，定位不變。
- 不引入 `testcontainers-python`（D1 詳述）。
- 不改動 `/api/*` 任何 user-facing endpoint — 只新增 `/internal/metrics`（Internal tier）。
- 不改動 `core/response.py` 或 envelope 契約。
- 不重構現有 `test_oracle_error_codes.py`（mock 層仍保留作為 contract tier；新層是 real-driver tier 疊加）。
- 不導入 Prometheus 或 push gateway — `/internal/metrics` 只服務測試內觀測，不進監控 stack。

## Decisions

### D1: Oracle container 用 GitHub Actions service container + `gvenzl/oracle-xe:21-slim`，不用 testcontainers-python 或官方 23c Free

- **選擇**：在 `.github/workflows/backend-tests.yml` 的 `oracle-fault-injection` job 用 `services:` 宣告 **`gvenzl/oracle-xe:21-slim`**（Oracle XE 21c 社群 slim image，~1.5GB）；fixture 只負責：(a) wait-for-ready polling、(b) 建立 schema + 測試 user、(c) 提供 DSN 給測試、(d) teardown drop schema。GHA `services:` 與 `docker-compose.test.yml` 的拓撲（port / service name / proxy name / healthcheck / env var key）由 `tests/integration/_infra_topology.py` 匯出的常數單一來源產出，避免兩份 YAML 漂移。
- **替代 A（棄）**：官方 `container-registry.oracle.com/database/free:latest`（23c Free，~6GB） → 本輪驗的是 driver / socket / pool / fault path，不吃 23c-specific 特性；CI cold start 成本與 image pull 成本壓力過大。若未來有 23c 行為要驗再開 follow-up change 升級。
- **替代 B（棄）**：`testcontainers-python` → 新依賴、local dev 需要 Docker daemon、container 生命週期被 Python 控制（multi-process test 共享不易）。
- **替代 C（棄）**：跑 mock oracledb listener（`oracledb.thin_mode` 的 fake server） → 無法驗證真實 driver 的 socket timeout 與 reconnect 路徑。
- **替代 D（棄）**：要求本地裝 Oracle XE → 違反「開發機不需額外依賴」的既有紀律（CLAUDE.md 全域規則）。
- **理由**：GitHub Actions service container 是官方機制、啟停由 CI 管、與既有 `redis-server` nightly job 同模式；fixture 只需 `oracledb.connect(dsn=...)` 就能拿真實連線；`gvenzl/oracle-xe:21-slim` 在 CI 經驗上 pull + boot 時間約 60–120s（官方 23c Free 常超過 300s），對 nightly budget 友善；本地 dev 透過 `docker-compose.test.yml` 啟同一個 image，CI/local 行為一致。

### D2: Network fault injection 用 toxiproxy-go sidecar，不用 iptables

- **選擇**：CI service container 再加一個 `shopify/toxiproxy:2.9` sidecar；測試透過 toxiproxy HTTP API（`POST /proxies/oracle/toxics`）注入 latency / timeout / slice / reset-peer；應用連 toxiproxy listen port 而非直連 Oracle listener。
- **替代 A（棄）**：`iptables -A OUTPUT ...` → 需要 root、CI runner 禁止、無法精準控制流向特定 port。
- **替代 B（棄）**：Python layer monkeypatch `socket.send` → 回到 mock 世界、不能驗證真實 driver。
- **替代 C（棄）**：`tc netem` → 同樣需要 NET_ADMIN capability、CI 不給。
- **理由**：toxiproxy 是專為 fault injection 設計、API 乾淨、CI 無特權需求、可程式化啟停故障；proxy 放 sidecar 讓應用的連線字串只需 host/port 切換，對測試程式零侵入。

### D3: 分兩層職責——mock 層（contract tier）+ real-driver 層（integration_real tier），不合併也不取代

- **選擇**：
  - 保留 `tests/integration/test_oracle_error_codes.py`（mock）不動——它驗證「error handler 對 ORA-code 的字串解讀是否正確」，pre-merge 2 秒內跑完。
  - 新增 `tests/integration/test_real_oracle_fault_injection.py`（real）——它驗證「真實 driver 在故障下是否真的拋對應 ORA-code、pool 歸還是否正確、reconnect 是否在 timeout 內完成」。
  - 修正 `tests/test_oracle_connection_leak.py:4-12` docstring：明確標示為「pool bookkeeping contract tier」，刪掉「future integration_real suite」誤導文案（契約漂移修正）。
- **替代（棄）**：把 mock 層改寫成 real-driver → pre-merge 時間爆炸（+8 分鐘 Oracle cold start）、且 mock 能驗證的「error code 解讀分支」被埋沒。
- **理由**：兩層驗證**不同契約**——mock 驗證「解讀」、real 驗證「driver 行為」。分層有助於 debug（mock fail → handler 邏輯錯；real fail → driver 或基建問題）。這也是 `harden-production-test-coverage` D3 選 mock 的理由延伸：mock 層該留，但要有 real-driver 疊加層補破口。

### D4: `/internal/metrics` 採 app-config + env-gate + loopback 三層 gate，純 JSON，不是 admin API 雛形

- **選擇**：
  - **Layer 1（registration-time gate）**：Flask blueprint 只在 app config `register_internal_metrics=True` 時被 `register_blueprint()`。只有 testing / nightly / soak 對應的 config factory 會把此 flag 設為 True；production 的 config factory 連 blueprint 都不 import，讓 route 在 URL map 裡根本不存在。這是最強的一層——即使 env 被誤設、即使 TCP 接口錯誤曝光，沒註冊的 route 連 404 之外的任何洩漏路徑都不存在。
    - **實作注意**：實際 attribute 名稱是 `REGISTER_INTERNAL_METRICS`（大寫），因為 Flask `Config.from_object()` 只複製 UPPERCASE 屬性；若寫成小寫會被 Flask 忽略，`app.config.get("register_internal_metrics")` 恆回 `None`，gate 永遠不觸發。本 design/spec 描述以小寫呈現以提升可讀性，實作 MUST 用大寫。
  - **Layer 2（runtime env gate）**：blueprint 被註冊後，route handler 第一件事檢查 `os.getenv("INTERNAL_METRICS_ENABLED") == "1"`，未設或非 `"1"` 回 `not_found_error()`。這層守 config factory 誤用（例如開發者手滑在非 testing config 開了 flag）。
  - **Layer 3（network-layer defense-in-depth）**：gunicorn `--bind 127.0.0.1:<port>` 單獨監聽 loopback；route 內 assertion `request.remote_addr in {"127.0.0.1", "::1"}`，非 loopback 仍回 404。這層只是縱深防禦——不單獨依賴 `remote_addr`（proxy / gunicorn 組合下 `remote_addr` 不可靠）。
  - Response：`success_response(data={...})`，不用 Prometheus exposition format、不用 OpenMetrics；純 JSON dict 7 類鍵 `pool / duckdb / redis / spool / worker_rss / circuit_breaker / rq`。
- **替代 A（棄）**：只用 env-gate + loopback（原 design） → 單靠 `remote_addr` 在 testing / proxy / gunicorn 組合下容易判斷失準；必須把 gate 前移到「route 根本不存在」的 registration 層。
- **替代 B（棄）**：Prometheus `/metrics` exposition format → 誘導 production 接 Prometheus、scope creep。
- **替代 C（棄）**：存在於主 `/api/admin/*` 下 → 權限、i18n、API contract 都要過——負擔太重，且 admin surface 可能被線上誤觸。這個 endpoint **刻意不是 admin API 的雛形或過渡階段**，未來若要做 observability admin 面請另開 change，不從此 endpoint 演進。
- **理由**：endpoint 存在目的是「soak 測試抓時序 delta」，不是 production observability；三層 gate 讓「此 endpoint 不應該在 production 被執行到」從一個紀律變成一個架構約束。

### D5: Soak 跑 30 分鐘、每 30 秒一次 sample，用時序判斷單調性，不用瞬時閾值

- **定位聲明（寫進 docstring / policy doc，不隱在 design 內）**：30 分鐘**不是**「證明沒有 leak」，而是「**有能力抓到短至中期的 leak**（30 分鐘內可觀察到斜率的退化）」。更慢的 regression（8h+ pool drift、幾小時才累積的 Redis key、稀有 code path triggered leak）**本測試無法涵蓋**；這類問題由 `workflow_dispatch` 覆寫 `duration_seconds` 到最多 120 分做針對性調查，超過 120 分的長跑不在自動 CI 範圍。
- **選擇**：
  - 跑長：CI soak 30 分鐘（default）、本地 smoke 5 分鐘、dispatch 覆寫上限 120 分。
  - 取樣：每 30 秒 HTTP GET `/internal/metrics` 一次，累積 60 筆（30 分鐘 CI）/ 10 筆（5 分鐘本地）/ 最多 240 筆（120 分鐘 dispatch）時序。
  - 斷言（全部看時序性質、不看單點）：
    - (a) `pool.checkout - pool.checkin` 的 linear regression slope 絕對值 < 0.05 / sample
    - (b) `duckdb.temp_bytes` 封頂：max ≤ first-quartile × 3
    - (c) Redis key 收斂：尾段 5 筆平均比首段 5 筆 ±10% 以內
    - (d) `worker_rss_bytes` growth：每個 worker 從 baseline 到 max 增長 < 15%
    - (e) circuit breaker 狀態轉換總次數 < 3
    - (f) **RQ queue depth**（D11 新增類別對應）：尾段 5 筆的各 queue 深度平均 ≤ 首段 5 筆平均 × 1.5；抓「沒 leak 但 backlog 長期上升」退化
- **替代 A（棄）**：2 小時 default → runner 額度不夠、開發反饋太慢；把 120 分作為 opt-in 覆寫而非 default 才合理。
- **替代 B（棄）**：瞬時閾值（「任何時刻 pool 利用率 < 80%」） → 跟 stress 測試重複、抓不到「慢速 leak」。
- **理由**：soak 的價值在「漸進式 regression」，時序性質才是訊號；30 分鐘 × 30 秒 = 60 samples 足以跑線性回歸並做 F-test；時序 artifact 在 CI 上傳後，bisect 時可視覺化（`soak-metrics-YYYYMMDD.json`）；定位聲明寫清楚可避免未來被誤引用成「soak 通過 = 沒有 leak」的強宣告。

### D6: Pre-merge gate 升級走量測 → 決策 → 升級三步，門檻寫成數學上誠實的 100%

- **門檻（Phase 0 定案）**：**20-day × 60-run window 下 pass rate = 100%**，且每檔 p95 wall time < 180s。**不用「99%」這種在 60-run 下數學上意義等於 100% 的假寬鬆寫法**。
- **數學說明**：60 runs 下，0 次失敗 = 100%、1 次失敗 = 98.3%。寫 99% 看似允許偶發、實際需要 0 次失敗——這會在 debug 時造成「為什麼寫 99% 卻不允許一次失敗」的認知成本，也讓政策文件失去可信度。誠實的寫法：
  - **現況（60 runs）**：門檻 = `pass_rate == 100%`
  - **未來若要放寬到 99.0%**：必須先把樣本擴大到 ≥ 100 runs（例如 34 晚 × 3 檔 = 102 runs，允許 1 次失敗即 99.02%）；此擴展需另開 change 調整 `measure-stability.yml` 的 rolling window。
- **流程**：
  - Phase 1（量測）：PR #1 + PR #2 加 `scripts/measure_real_infra_stability.py` + `.github/workflows/measure-stability.yml`，每晚 CI 跑一輪、加總 20 天（20 × 3 = 60 runs）；輸出 `docs/real_infra_stability_report.md`。
  - Phase 2（決策）：reviewer 看 report，若 60-run window pass rate = 100% 且各檔 p95 < 180s → 批准升級；否則對每個 flakiness 根因開 `fix-<slug>` change。
  - Phase 3（升級）：PR #N 才動 `backend-tests.yml` 把這 3 檔搬到 `real-infra-smoke` pre-merge required check；保留 nightly `integration-real` job 繼續跑（兩處並存，不是搬家）。
  - 降回機制：`docs/ci_real_infra_gate_policy.md` 明訂——若 pre-merge `real-infra-smoke` 過去 7 天 flaky rate > 1%（計算：非 red 卻 re-run 後變 green 的次數 / 總跑次），自動降回 nightly（手動 revert PR），避免污染 trunk velocity。
- **替代（棄）**：PR #1 一次把 gate 升級 → 沒數據支撐、flaky 時會全面癱瘓 pre-merge。
- **理由**：測試穩定性是**分布問題**不是點問題；升級前必須有量化證據，且門檻寫法必須與樣本數匹配，不搞看起來寬鬆實際等於 100% 的假數字。

### D7: toxiproxy 只做 socket-level 故障，不做應用層錯誤注入

- **選擇**：toxiproxy 只注入 TCP 層故障（latency / timeout / slice / reset-peer）。ORA-code 語意錯誤（例如偽造 ORA-01555 payload）仍由 mock 層（D3）負責。
- **替代（棄）**：用 `mitmproxy` 改寫 Oracle TNS protocol payload → 風險高、維護成本爆炸、跨版本不穩。
- **理由**：Oracle TNS protocol 是二進位、不公開細節；試圖偽造會得到不精確的還原（且可能打到 server-side 的 protocol bug）。職責分層：mock 管 payload 語意、toxiproxy 管 socket 行為。

### D8: Fixture 共享策略——session-scoped `oracle_xe`、function-scoped `oracle_xe_fault`

- **選擇**：
  - `oracle_xe`（session-scoped）：container 起一次、schema 建一次、session 結束才 teardown；所有測試共用 DSN。避免 30 秒 cold start × 檔數累加。
  - `oracle_xe_fault`（function-scoped）：每個測試獨立 toxiproxy toxic；teardown 清光 toxic。避免跨測試 toxic 污染。
  - 每個 test 自己建 table、自己 drop table（cleanup at teardown via `try/finally`）；不共用 table state。
- **替代（棄）**：每個 function 都起一次 container → 動輒 10 分鐘起動時間，nightly 跑不完。
- **理由**：container 的 cold start 是固定成本、toxic 是輕量狀態；分 scope 平衡啟動成本與測試隔離性。

### D9: Soak 的 `metrics` client 實作與測試共用；不依賴 httpx / requests-toolbelt

- **選擇**：在 `tests/integration/_metrics_probe.py` 寫一個 <50 行 `MetricsProbe` class，用 `urllib.request`（stdlib）輪詢 `/internal/metrics`；支援 `.snapshot()` → 回 dict、`.stream(duration, interval)` → 回 iterator。
- **替代（棄）**：導入 `httpx` 或 `aiohttp` → 新依賴、無實質好處、soak test 不需要 async。
- **理由**：stdlib 足夠；probe 只有 snapshot 與 streaming 兩個方法。

### D10: Triage 沿用 `harden-production-test-coverage` 的 D9，寫進 tasks

- **選擇**：實作完成跑全量（backend / frontend / integration_real / soak 本地 5 分鐘版），每個 failure 走四步 triage（步驟 A/B/C/D 同前一個 change）；CODE_BUG 在本 PR `xfail`，另開 `fix-<slug>` change；triage 紀錄在 `triage.md`。
- **理由**：已驗證成熟流程；`fix-missing-fuzz-validation`、`fix-map-service-errors-propagates-degraded` 等 follow-up 都走這條路，成效顯著。

## Risks / Trade-offs

- **[Oracle container cold start 在 CI 可能超時]** 官方 Oracle 23c Free image 冷啟動 GitHub Actions hosted runner 通常 90–180 秒，偶發 > 300 秒。 → 緩解：job `timeout-minutes: 30`、`actions/cache` 快取 `/var/lib/docker/*` layer、readiness polling 最多等 240 秒即 fail fast 標記環境問題。
- **[toxiproxy 與 Oracle driver 的邊界行為不一致]** 某些 toxic（如 `slicer`）可能在 Oracle TNS protocol 層導致 driver 拋不穩定例外（不是我們想驗的 ORA-code，是解析層 crash）。 → 緩解：先用 `latency` / `timeout` / `bandwidth`（行為明確）、謹慎引入 `slicer`；每個 toxic 先做「what does driver throw」的探測測試再寫斷言。
- **[`/internal/metrics` endpoint 洩漏]** 若環境變數 gate 被誤開啟到 production，會洩漏 pool 配置、RSS、Redis key pattern。 → 緩解：env-gate + loopback assertion + 單元測試明確驗證「非 loopback 連入時回 404」；部署文件明確宣告 `INTERNAL_METRICS_ENABLED` 只能在 test environment 設為 1。
- **[soak 30 分鐘消耗 runner 額度]** 每週一次 × 30 分鐘 + workflow_dispatch。 → 可接受；若 GHA runner 額度緊繃，降到每兩週。
- **[Pre-merge gate 升級後 flakiness 影響 velocity]** 升級後若 flaky rate 上升污染 trunk。 → D6 的降回機制 + 量測門檻 99%。
- **[`measure_real_infra_stability.py` 跑 20 輪 × 3 檔本地耗時 > 60 分鐘]** 開發者不想本地跑。 → 設計成「每晚 CI 自動跑一輪、累積 20 天」，本地只需開發時跑 2–3 輪驗證 fixture。
- **[Oracle XE / Free 授權]** Oracle 23c Free 是 Free for development/testing，CI 使用合規；需在 `docs/ci_real_infra_gate_policy.md` 明確記錄授權條款連結。 → 緩解：決策前確認 Oracle 官方 Free license 是否允許 CI 用；若不允許改用 XE 21c（仍 free）。

## Migration Plan

- **Phase 0（對齊）**— 本 proposal merge 前與 owner 對齊 6 個 Open Questions（見下）；不寫 code。
- **Phase 1（基建 + 量測，PR #1 + PR #2）**：
  - PR #1：`_oracle_xe_fixture.py` + `docker-compose.test.yml` + 空 `test_real_oracle_fault_injection.py`（只有 fixture smoke test）+ CI service container 宣告
  - PR #2：`measure_real_infra_stability.py` + 每晚 CI schedule 跑一輪，累積 stability data
- **Phase 2（Oracle fault 測試，PR #3 + PR #4）**：
  - PR #3：真 Oracle fault injection 測試 session kill / listener stop（2 支）
  - PR #4：snapshot too old + network flap（2 支）+ 修正 `test_oracle_connection_leak.py` docstring
- **Phase 3（Soak，PR #5）**：`/internal/metrics` endpoint + `test_soak_workload.py` + `soak-tests.yml` + `scripts/soak_local.sh` + `contract/api_inventory.md` 更新
- **Phase 4（Gate 升級，PR #6）**：收齊 Phase 1 的 20 天 stability data → 達標才建 `real-infra-smoke` job 搬 3 檔進 pre-merge；`docs/ci_real_infra_gate_policy.md` 落地；不達標則拆成 `fix-<slug>` follow-up
- **Phase 5（全量驗收 + triage）**：跑全量 + soak 5 分鐘本地版，分類 TEST_BUG / CODE_BUG / FLAKY_TEST；CODE_BUG 另開 change
- **回滾策略**：
  - 每個 PR 獨立；PR #1 的 container fixture 若啟動不穩 → revert PR，回到純 mock 層
  - PR #5 的 `/internal/metrics` 若 env-gate 有漏 → 立即 patch 關閉（env 變數全域改 0）
  - PR #6 的 gate 升級若 flaky rate > 1% → 走 D6 降回 nightly 的手續

## Open Questions

### 已在 Phase 0 定案（見 proposal.md「Phase 0 Pinned Decisions」表）

以下六題已取得 owner 對齊、寫進 proposal 與 delta specs，Phase 1 起不再討論：

- **Oracle image**：`gvenzl/oracle-xe:21-slim` 優先，官方 23c Free 不在本提案範圍
- **toxiproxy 部署**：CI `services:` + local `docker-compose.test.yml`，配置由 `tests/integration/_infra_topology.py` 單一常數模組產出
- **soak 長度**：default 30 分、dispatch 最多 120 分、本地 smoke 5 分；定位為「抓短至中期 leak」而非「證明無 leak」
- **`/internal/metrics` 欄位**：**7 類** — 新增 `rq` queue depth
- **stability 門檻**：20-day × 60-run window 下 **pass rate = 100%**（不用數學上不誠實的假 99%）；未來要放寬到 99% 需先擴樣到 ≥ 100 runs
- **pre-merge gate 範圍**：`oracle-fault-injection` 只進 nightly，不進 pre-merge required check

### 真正尚待觀察（實作後再評估，不擋 Phase 1 起跑）

1. **oracle-xe 21-slim 的 ORA-01555 觸發門檻**：本 image 的 `UNDO_RETENTION` 預設行為未知；實作 `test_snapshot_too_old_long_running_query` 時可能需要 SQL script 先手動降低 retention 再造條件，步驟細節 Phase 2 才會確定。
2. **`_infra_topology.py` 的 code-gen vs 手寫兩份 YAML**：定義常數模組是 Phase 0 承諾；是否進一步寫 generator script 自動產 GHA yaml fragment，或只用 docstring 約束兩份手工同步，Phase 1.1 實作時拍板（視工作量）。
3. **Soak 60 分鐘 dispatch 是否夠用**：120 分上限是本提案劃的紅線；若實作後發現某些慢速 leak 需要 4–6 小時才能觀察，視當時的 runner budget 判斷要不要另開 change 加長，**不在本提案範圍**。
4. **降回機制的自動化程度**：`docs/ci_real_infra_gate_policy.md` 目前定義「人工 revert PR」；未來若累積足夠 flaky rate 資料，可考慮寫 GH Actions workflow 自動發 revert PR（本提案先手動）。
