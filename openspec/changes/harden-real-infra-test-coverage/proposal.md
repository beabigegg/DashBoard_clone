## Phase 0 Pinned Decisions

以下項目已由 proposal 審查階段定案，**Phase 1 起不再討論**，直接按此實作：

| 項目 | 決議 |
| :--- | :--- |
| Oracle image | `gvenzl/oracle-xe:21-slim`（XE 21c，~1.5GB）。官方 `container-registry.oracle.com/database/free:latest`（23c Free，~6GB）不在本提案範圍；若未來有 23c-specific 行為要驗再開 follow-up change |
| toxiproxy 部署 | CI 用 GHA `services:`、local 用 `docker-compose.test.yml`；port / service name / proxy name / healthcheck / env var key 由 `tests/integration/_infra_topology.py` 單一常數模組生成，兩份 YAML 皆由此產出，避免手動漂移 |
| `/internal/metrics` 三層 gate | **Layer 1**：Flask blueprint 只在 app config `register_internal_metrics=True` 時註冊（僅 testing / nightly / soak config factory 會設；實作屬性名為 `REGISTER_INTERNAL_METRICS` 大寫，因 Flask `Config.from_object()` 只吸收 UPPERCASE 屬性）；**Layer 2**：runtime 檢查 `INTERNAL_METRICS_ENABLED=1`；**Layer 3**：route 內 `request.remote_addr` loopback 檢查。明確定位為 internal-only app surface，**不是 admin API 過渡階段**，不進任何 production deploy config |
| `/internal/metrics` 指標類別 | **7 類**（含 `rq` queue depth）：`pool` / `duckdb` / `redis` / `spool` / `worker_rss` / `circuit_breaker` / `rq` |
| Stability 門檻 | **20-day × 60-run window 下 pass rate = 100%** 且每檔 p95 wall time < 180s 才可升 gate。數學理由：60 runs 下 1 次失敗即 98.3%，寫 99% 是假寬鬆。若未來要放鬆到 99.0%，必須先把樣本擴到 ≥ 100 runs 再談 |
| `oracle-fault-injection` CI 定位 | 只進 nightly + workflow_dispatch，**不進 pre-merge required check**。理由：高價值高成本、受環境影響較大，作為 regression sentinel 而非 gate |
| Soak 定位聲明 | 30 分鐘 default 不是「證明沒 leak」，而是「有能力抓到短至中期 leak」；8h+ 的漸進式問題靠 `workflow_dispatch` 覆寫到 120 分調查，超過不在自動 CI 範圍 |

下面的 Why / What Changes / Impact 已依上表修訂；Open Questions 則縮減為尚未定案的次要細節。

## Why

`harden-production-test-coverage` 已補上「Playwright 故障注入」「ORA-code envelope 驗證」「Redis timeout fallback」「Race condition」「輸入模糊化」五層，但事實核對後發現仍有三塊硬殼還沒碰到真實故障面，且互相依賴：

1. **Oracle fault injection 全部是 in-process mock**。`tests/integration/test_oracle_error_codes.py` 用 `patch` 注入 `cx_Oracle.DatabaseError` 字面量、`tests/test_oracle_pool_exhaustion.py:6` 直接 `side_effect=DatabasePoolExhaustedError`、`tests/test_oracle_error_path.py:13-19` 是 service-boundary monkeypatch、`tests/test_oracle_connection_leak.py:4` 甚至在註解裡宣告「Real-Oracle connection leak detection ... tracked separately under the future integration_real suite」——但這個 future suite 從未建立。我們沒有任何測試會在**真實 oracledb driver + 真實 TCP socket + 真實 listener** 的情境下驗證：session kill 後連線是否歸還 pool、listener 停擺時客戶端 backoff 行為、網路斷流時 circuit breaker 的真實 latency、ORA-01555 snapshot 過期是否真由 Oracle server 拋出。Mock 的 error class instance 通過測試不等於 driver 的真實路徑通過。

2. **沒有任何 soak 工作負載**。現有 `stress-tests.yml` 只在 `workflow_dispatch` 觸發，且 `test_cross_module_stress.py:40-41` 把 `Timeout` 視為 success、`test_cross_module_stress.py:224` 接受 `200/500/503` —— 這是尖峰壓測（spike test），不是長跑穩定性測（soak test）。我們無法偵測：連線池的漸進式 leak、DuckDB 臨時檔案的 disk growth、Redis key 的無意識累積、gunicorn worker 的 memory creep、circuit breaker 在長時間 retryable error 下的 oscillation。這些 regression 只會在 production 跑了幾小時後才顯現，當下 commit diff 通常看起來無辜。

3. **pre-merge gate 仍放過三個關鍵真實測試**。`test_multi_worker_concurrency.py`、`test_redis_chaos.py`、`test_real_multi_worker.py` 都掛 `integration_real` marker，`tests/integration/conftest.py:65-76` + `backend-tests.yml:79-85` 決定它們只在 nightly 跑。但這三個檔案恰好涵蓋：cross-worker spool 共享（違反時 export 會拿到錯的 parquet）、distributed lock exclusion（違反時 cache refresh 會炸 Oracle）、control-plane Redis 重連（違反時整個 async job 系統停擺）。這種 blast radius 的 bug 放到 nightly 才發現意味著**整天的 PR 合進來都可能是壞的**。

三者互相依賴：沒有 Oracle container + toxiproxy 基建（#1），就沒辦法在 pre-merge 時間內跑真實 Oracle 故障；沒有 soak workload（#2），就無法量測 pre-merge 升級（#3）後的長期穩定性是否足夠。單獨做任何一項都會卡在基建或量測缺口。

## What Changes

### 主軸 A：真實 Oracle 故障注入基建 + 測試套件

- 新增 `tests/integration/_oracle_xe_fixture.py` 提供 `oracle_xe` pytest fixture：啟動 **`gvenzl/oracle-xe:21-slim`** container（Phase 0 已定案；見下文 Pinned Decisions）、建立專用 schema、透過 toxiproxy-go sidecar 注入 network fault（latency / slice / timeout / reject），teardown 乾淨。官方 Oracle 23c Free 保留為未來 follow-up change 的升級備援，不在本提案範圍。
- 新增 `tests/integration/test_real_oracle_fault_injection.py`（掛 `@pytest.mark.integration_real`）：真實 driver + 真實 socket 情境下驗證 session kill / listener stop / snapshot too old / network flap 的 envelope、pool 歸還、circuit breaker 計數、retryable 分類、`Retry-After` 標頭。
- 修正 `tests/test_oracle_connection_leak.py:4` 的契約漂移：docstring 宣告是 "future integration_real suite"，現實是純 mock——改成「pool bookkeeping contract tier」職責清楚的 docstring，並在新套件 cover 對應的真 Oracle 情境。
- 新增 `docker-compose.test.yml` 在 GitHub Actions 與本地容器化 `gvenzl/oracle-xe:21-slim` + toxiproxy；並新增 `tests/integration/_infra_topology.py`（單一事實來源）匯出 service name / port / proxy name / healthcheck / env var key 等常數，由該檔生成 GHA `services:` 宣告與 `docker-compose.test.yml` 的 YAML fragment，避免兩份 YAML 慢慢漂移；文件化「為什麼不用 testcontainers-python」決策。
- CI：新增 `oracle-fault-injection` nightly job（GitHub Actions service container 跑 Oracle XE 21-slim，預估 +4–8 分鐘 cold start）；**不**進 pre-merge——pre-merge 只跑對 fixture 本身的 smoke test（fixture 起得來、拋得出故障）。

### 主軸 B：Soak workload + 觀測端點

- 新增 `/internal/metrics` endpoint — **internal-only app surface，不是 admin API 雛形、不進任何 production deploy config**。三層保護：(1) blueprint 只在 app config `register_internal_metrics=True` 時註冊（只有 testing / nightly / soak workflow 的 config factory 會設）；(2) runtime 仍檢查 `INTERNAL_METRICS_ENABLED=1` 作為 env 層 fail-safe；(3) route 內 `request.remote_addr` loopback 檢查作為縱深防禦。匯出 **7 類**指標：pool 利用率、DuckDB 臨時檔大小、Redis key 數量、spool 目錄磁碟、gunicorn worker RSS、circuit breaker 狀態、**RQ queue depth**（pending / started / failed / finished / deferred 各隊列長度）。這個 endpoint 只服務測試觀測，不進 Prometheus、不進 dashboard、不是未來 admin API 的過渡階段。
- 新增 `tests/integration/test_soak_workload.py`（掛 `@pytest.mark.soak`，獨立於 `integration_real`）：使用既有 `gunicorn_workers` fixture 對五個高流量 endpoint 發 30 分鐘低壓請求（每秒 2–5 req），過程中每 30 秒抓 `/internal/metrics` 取 delta，驗證 (a) pool checkout/checkin 差值不單調增長；(b) DuckDB 臨時檔大小封頂；(c) Redis key 數量收斂到 baseline ± 10%；(d) worker RSS 增長 < 15%；(e) 無 circuit breaker 開關震盪（狀態轉換次數 < 3）；**(f) RQ queue depth 尾段不超過首段 × 1.5**（抓「沒 leak 但 backlog 長期上升」退化）。**定位聲明**：30 分鐘不是「證明沒 leak」，而是「有能力抓到短至中期 leak」。更慢的 regression（8h+ pool drift、稀有 code path 累積）靠 `workflow_dispatch` 覆寫到 120 分調查；超過 120 分的長跑不在自動 CI 範圍。
- 新增 `.github/workflows/soak-tests.yml`：週日夜跑 + `workflow_dispatch` 手動觸發；default 跑 30 分鐘 soak；支援 dispatch input 覆寫 `duration_seconds`（上限 120 分）；把 metrics 時序上傳為 artifact；失敗時標記 soak-regression label（不進 pre-merge、不擋 nightly）。
- 新增 `scripts/soak_local.sh`：本地跑 5 分鐘縮水 soak 用於開發驗證。

### 主軸 C：Pre-merge gate 升級

- 量測階段：新增 `scripts/measure_real_infra_stability.py`，對 `test_multi_worker_concurrency.py`、`test_redis_chaos.py`、`test_real_multi_worker.py` 每晚一輪、連續 20 晚（total 20 runs × 3 files = 60 runs），輸出 pass rate、wall time 分布、flakiness index。作為升級決策的 go/no-go data。
- **門檻採數學上誠實的寫法，不用看起來寬鬆實際等於 100% 的假 99%**：升級前置條件為「**20-day × 60-run window 下 pass rate = 100%**」，且每檔 p95 wall time < 180s。若未來想放鬆到 ≤ 1 次失敗（99.0%），必須先把樣本數擴到 ≥ 100 runs（例如 34 晚 × 3 檔 = 102 runs）再談——寫進 `docs/ci_real_infra_gate_policy.md`。
- 達標才動 gate：把三檔從 nightly 搬到 pre-merge 的新 job `real-infra-smoke`（`backend-tests.yml` 的 required check），並繼續保留 nightly 的「全量真實整合」job。
- 達不到門檻時保持 nightly 並在 triage.md 登記 flakiness 根因（race / 環境依賴 / fixture 洩漏），針對每個根因開 follow-up `fix-<slug>` change。
- 新增 `docs/ci_real_infra_gate_policy.md`：記錄 pre-merge 升級決策流程、門檻定義（含上述數學說明）、回滾手續（若 pre-merge 中該 job flaky rate > 1% 即自動降回 nightly）。

### 其他

- **遵循 harden-production-test-coverage 相同的 triage 紀律**：每個新測試提交前跑 mutation check（拿掉對應 handler → 測試應 FAIL）；實作完成跑全量，failure 分 `TEST_BUG` / `CODE_BUG` / `FLAKY_TEST`；CODE_BUG 另開 `fix-<slug>` OpenSpec change。
- **文件同步**：若 `/internal/metrics` 新增 endpoint，同步更新 `contract/api_inventory.md`（Internal tier）。

## Capabilities

### New Capabilities

- 無新增 user-facing capability。`/internal/metrics` 屬於 internal-only observability surface，只為 soak 測試服務，不面向終端使用者。

### Modified Capabilities

- `real-environment-integration-tests`: 新增「真實 Oracle driver + toxiproxy 故障注入」「soak workload 長跑穩定性量測」「`oracle_xe` fixture」「`/internal/metrics` 端點」四類 requirements。現有 gunicorn / local_redis / temp_spool_dir / job-abandon / shared-volume 既有 requirements 保留不動。
- `backend-integration-test-coverage`: 新增「真實 Oracle driver 觀測的 session kill / listener stop / snapshot too old / network flap 情境」作為 `test_oracle_error_codes.py` mock 層之上的疊加層。明確標示現有 mock 層為「contract boundary tier」、新層為「real-driver tier」的分層關係。
- `multi-worker-concurrency-test-coverage`: 新增「pre-merge gate 升級的量測前置條件」「穩定性門檻定義」「自動降級回 nightly 的觸發條件」三類 requirements。

## Impact

- **新增程式檔**（~7 檔）：
  - `tests/integration/_oracle_xe_fixture.py`
  - `tests/integration/_infra_topology.py`（**單一事實來源**：service / port / proxy / env var 常數；GHA services 與 docker-compose 皆由此生成）
  - `tests/integration/test_real_oracle_fault_injection.py`
  - `tests/integration/test_soak_workload.py`
  - `scripts/measure_real_infra_stability.py`
  - `scripts/soak_local.sh`
  - `docker-compose.test.yml`
- **新增 endpoint**：`/internal/metrics`（Flask route + service；app-config + env + loopback 三層 gate；7 類指標含 RQ queue depth）
- **修改既有**：
  - `.github/workflows/backend-tests.yml` — 新增 `oracle-fault-injection` job + 條件升級 `real-infra-smoke` 到 pre-merge
  - `.github/workflows/soak-tests.yml` — 新檔
  - `tests/test_oracle_connection_leak.py` — 修正 docstring 的契約漂移（純文件變更）
  - `contract/api_inventory.md` — 新增 `/internal/metrics` **Internal-only** 分類並註記「不屬於 admin API 面、不進任何 production deploy config」
  - `CLAUDE.md` — Project Commands 區新增 soak / oracle-xe / measure-stability 指令
- **CI 時間影響**：
  - pre-merge：升級成功後 +60–120 秒（`real-infra-smoke` job）；失敗則維持現狀
  - nightly：+4–8 分鐘（Oracle XE 21-slim cold start + fault injection suite）
  - weekly soak：獨立 workflow，default 30 分、dispatch 最多 120 分
- **依賴**：
  - 新增 CI service：`shopify/toxiproxy:2.9`、**`gvenzl/oracle-xe:21-slim`**（~1.5GB，比官方 23c Free 的 ~6GB 輕 4 倍；官方 23c Free 留作 follow-up 升級）
  - 不新增 Python package（fixture 用 `subprocess` + `urllib.request` + 既有 `oracledb`）
  - 不新增前端 package
- **風險**：
  - Oracle XE 21-slim 在 GitHub Actions hosted runner cold start 通常 60–120 秒 → 緩解：用 `actions/cache` 快取 container layer、readiness polling 最多 240 秒 fail fast
  - `/internal/metrics` endpoint 若任一層 gate 失效仍可能洩漏 → 緩解：三層獨立 gate（app-config / env / loopback），單元測試覆蓋每層失效組合、預設關閉、loopback bind、不納入 production deploy config
  - soak 測試 30 分鐘消耗 runner 額度 → 緩解：週跑 + workflow_dispatch，不進日常 loop
- **不包含**：
  - 前端 CI 的 `frontend/tests/*.test.js` glob 只收到 3 檔、實際 57 檔未跑的 bug（事實核對已確認，但該 bug 的修正範圍與本提案的基建無依賴，應獨立為 `fix-frontend-ci-test-glob` change 處理）
  - Stress 測試將 `Timeout` 計為 success、接受 500/503 的契約漏洞（獨立為 `fix-stress-assertions-leniency` change）
  - 視覺回歸、chaos framework、CSRF 驗證（延續上一個 change 的界線，仍為非目標）
  - 把 stress 納入 pre-merge（本提案只處理 real-infra，不動 stress 定位）

## Discovered Regressions

待實作 → triage 階段補齊；預期會在 soak 工作負載與真實 Oracle 故障下暴露若干既有 bug（現有 mock 層看不到的漸進式資源洩漏與 driver 層邊界），依慣例每個 CODE_BUG 另開 `fix-<slug>` OpenSpec change 並連結於此。
