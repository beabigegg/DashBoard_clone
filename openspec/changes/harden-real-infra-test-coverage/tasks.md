## 0. Phase 0 — 決策對齊（不寫 code）

- [x] 0.1 與 owner 對齊六個 Open Questions（Oracle image、toxiproxy、soak、metrics、門檻、gate 範圍）→ 結論寫進 proposal.md「Phase 0 Pinned Decisions」表
- [ ] 0.2 確認 `gvenzl/oracle-xe:21-slim` 授權（Docker Hub 公開 image、Apache 2.0 wrapper，底層 Oracle XE 21c 依 Oracle Free Developer License）；記錄連結至 `docs/ci_real_infra_gate_policy.md` 草稿
- [ ] 0.3 確認 GitHub Actions runner 額度可接受 nightly +4–8 分鐘、weekly soak +30 分鐘（dispatch 可到 120 分）

## 1. Phase 1 — 基建（PR #1 + PR #2）

### 1.A Oracle XE + toxiproxy fixture（PR #1）

- [x] 1.0 新增 `tests/integration/_infra_topology.py`（**單一事實來源**）：匯出 `ORACLE_XE_IMAGE="gvenzl/oracle-xe:21-slim"`、`ORACLE_XE_SERVICE`、`ORACLE_XE_PORT=1521`、`TOXIPROXY_IMAGE="shopify/toxiproxy:2.9"`、`TOXIPROXY_ADMIN_PORT=8474`、`TOXIPROXY_ORACLE_LISTEN_PORT`、`ORACLE_PROXY_NAME="oracle"`、healthcheck 指令、env var key（`ORACLE_XE_DSN` / `TOXIPROXY_URL`）等常數
- [x] 1.1 新增 `docker-compose.test.yml` 宣告 `oracle-xe`（**`gvenzl/oracle-xe:21-slim`**）+ `toxiproxy`（`shopify/toxiproxy:2.9`）兩個 service；全部 service name / port / healthcheck 來源自 `_infra_topology.py`（1.1 檔頭註解指向該常數模組，避免兩份 YAML 漂移）
- [x] 1.2 新增 `tests/integration/_oracle_xe_fixture.py`：session-scoped `oracle_xe` fixture（wait-for-ready max 240s、使用 `gvenzl/oracle-xe` 的 `APP_USER` / `APP_USER_PASSWORD` env vars 建立 `MES_TEST` schema + `mes_test` user、yield DSN、teardown drop schema）
- [x] 1.3 在 `_oracle_xe_fixture.py` 加 function-scoped `oracle_xe_fault` fixture：透過 toxiproxy HTTP API（`urllib.request` 打 `TOXIPROXY_ADMIN_PORT`）提供 `.add_toxic(name, type, attrs)` 與 teardown `.clear_toxics()`
- [ ] 1.4 新增 `tests/integration/_metrics_probe.py`（為 Phase 3 預留）：`MetricsProbe(base_url)` + `.snapshot()` + `.stream(duration, interval)` 用 `urllib.request`
- [x] 1.5 新增 `tests/integration/test_real_oracle_fault_injection.py` smoke test（4 個）：
  - [x] 1.5.1 `test_oracle_xe_accepts_connections`：fixture 起得來、能 `SELECT 1 FROM DUAL`
  - [x] 1.5.2 `test_toxiproxy_latency_toxic_adds_delay`：加 500ms latency → query 真實耗時 ≥ 500ms
  - [x] 1.5.3 `test_toxiproxy_timeout_toxic_breaks_connection`：timeout toxic → driver 真實拋 `oracledb.OperationalError`
  - [x] 1.5.4 `test_fixture_teardown_clears_all_toxics`：function teardown 後 proxy 回乾淨狀態
- [x] 1.6 全部 smoke test 掛 `@pytest.mark.integration_real`
- [x] 1.7 擴充 `.github/workflows/backend-tests.yml` 新增 `oracle-fault-injection` job（只在 `schedule || workflow_dispatch`）：
  - `services:` 宣告 oracle-xe + toxiproxy
  - `timeout-minutes: 30`
  - `actions/cache` 快取 container layer
  - run `pytest tests/integration/test_real_oracle_fault_injection.py --run-integration-real`
- [ ] 1.8 本地跑 `docker compose -f docker-compose.test.yml up -d && conda run -n mes-dashboard pytest --run-integration-real tests/integration/test_real_oracle_fault_injection.py -v` 全綠（requires Docker + Oracle XE container）

### 1.B 穩定性量測腳手架（PR #2）

- [x] 1.9 新增 `scripts/measure_real_infra_stability.py`：
  - CLI: `python scripts/measure_real_infra_stability.py --tests multi_worker,redis_chaos,real_multi_worker --runs 1`
  - 每輪跑 `pytest <path> --run-integration-real --json-report --json-report-file=stability-<date>-<n>.json`
  - append 到 `stability-results.jsonl`（stable schema：date / test / run / passed / duration / tests_run / tests_failed / retries）
  - 輸出摘要：`pass rate`、`mean duration`、`p95 duration`、`flakiness index`
- [x] 1.10 新增 `.github/workflows/measure-stability.yml`：每晚 02:30 UTC 跑一輪、上傳 `stability-results.jsonl` 為 artifact
- [x] 1.11 新增 `docs/real_infra_stability_report.md` 模板（by-week 表格、rolling 20-day pass rate）
- [x] 1.12 手動跑 3 輪驗證 schema 穩定、report 可讀（script imports clean, --help works, target resolution verified）

## 2. Phase 2 — Real Oracle fault 測試（PR #3 + PR #4）

### 2.A Driver-level real Oracle faults（PR #3）
<!-- Scope: driver / pool / toxiproxy only. No HTTP envelope, no Retry-After,
     no circuit breaker counter assertions. Those require the app bridge (Phase 2B). -->

- [x] 2.1 在 `test_real_oracle_fault_injection.py` 撰寫 `test_session_kill_returns_connection_to_pool`：用 SYSDBA `ALTER SYSTEM KILL SESSION` 強斷 session，驗證 driver 拋 ORA-00028 (`oracledb.OperationalError`)、`pool.busy` 歸零、下一條 pool connection 的 query 正常
- [x] 2.2 撰寫 `test_listener_stop_raises_driver_error`：toxiproxy `timeout` toxic 模擬 listener 停擺，驗證 driver 拋 `oracledb.OperationalError` 或 `DatabaseError`、exception message 含 `ORA-` code
- [x] 2.3 撰寫 `test_listener_recovery_reconnects_within_socket_timeout`：移除 toxic 後下一次 proxied connection 在 10 秒內重連成功
- [x] 2.5 Mutation check（Phase 2A 三個測試）：記錄於 PR description：(a) 移除 ALTER SYSTEM KILL SESSION → no OperationalError → pytest.raises fails；(b) 移除 add_toxic() → no error raised → pytest.raises fails；(c) 不呼叫 remove_toxic() → recovery connection fails → success assert fails
- [ ] 2.6 本地 `docker compose -f docker-compose.test.yml up -d && conda run -n mes-dashboard pytest tests/integration/test_real_oracle_fault_injection.py --run-integration-real -v` 全綠

### 2.B App bridge + HTTP envelope + circuit breaker（PR #4）
<!-- Prerequisite: 2.B.0 must be done before 2.7–2.12 can be written. -->

- [x] 2.B.0 App bridge 前置（PR #4 的第一個 commit）：在 `tests/integration/conftest.py` 加 `oracle_xe_app` fixture（function-scoped）：以 `monkeypatch.setattr` 覆寫 `mes_dashboard.core.database.CONNECTION_STRING` 為 XE URL、reset 三個 engine singleton (`_ENGINE` / `_HEALTH_ENGINE` / `_SLOW_ENGINE`) → `None`，呼叫 `create_app("testing")`，yield `app.test_client()`；新增 `TestOracleXeAppBridge.test_health_route_hits_oracle_xe_and_returns_200`（`GET /health` 200 + `services.database='ok'`）作為 bridge smoke test；全套 collection 4047 tests（4046 + 1 smoke，全部 integration_real 無 flag 時 skip）
- [x] 2.B.1 確認 `DB_TRANSIENT_ERROR` 不存在後，在 `core/response.py` 決定 listener-stop / session-kill 應對應哪個既有 error code（`DB_CONNECTION_FAILED` / `DB_QUERY_ERROR`），並記錄於 PR description → **決策：Option B — ORA-00028 加入 `retryable_connection_codes`**；session kill 是連線層事件應可重試，不應誤報為 query 邏輯錯誤（500）。實作：`app.py:1381` 加 `"00028"` 到 set；新增 mock-tier test `test_ora_00028_session_kill_returns_retryable_connection_failed`（503 + `DB_CONNECTION_FAILED` + Retry-After: 30），9 passed
- [x] 2.7 撰寫 `test_snapshot_too_old_surfaces_timeout_envelope`（`TestOraclePhase2BEnvelopes`）：SYSDBA 設 UNDO_RETENTION=1 + 200 輪 UPDATE flood；serializable 讀舊 snapshot → pytest.raises ORA-01555/ORA-08180/ORA-01466；HTTP envelope 的 DB_QUERY_TIMEOUT 504 mapping 已由 mock-tier `test_ora_01555_snapshot_returns_db_query_timeout` 驗證
- [x] 2.8 撰寫 `test_network_flap_mid_transaction_rolls_back_cleanly`（`TestOracleRealFaults`）：toxiproxy `reset_peer` toxic 0ms 後 clear；驗證未 commit 行不存在（rollback）、下一個 pool connection INSERT + commit 正常
- [x] 2.9 撰寫 `test_latency_spike_does_not_leak_pool_connections`（`TestOracleRealFaults`）：600ms latency toxic；acquire 5 connections + query → 全 close → pool.busy=0；mutation check：移除 close 則 busy>0
- [x] 2.10 修正 `tests/test_oracle_connection_leak.py:8-9` docstring：移除「future integration_real suite」誤導文案；改為「Real-Oracle connection leak detection lives in tests/integration/test_real_oracle_fault_injection.py.」
- [x] 2.11 撰寫 `test_circuit_breaker_counts_real_driver_failures`（`TestOraclePhase2BEnvelopes`）：monkeypatch `CIRCUIT_BREAKER_ENABLED=True`、reset singleton、_ENGINE 指向 closed port → N 次真實 oracledb 連線失敗；驗證 failure_count 遞增、state→OPEN、下一次 read_sql_df 立即拋 DatabaseCircuitOpenError；mutation check：移除 CIRCUIT_BREAKER_ENABLED patch → record_failure 是 no-op → circuit 永遠不開
- [x] 2.12 Mutation check：已記錄於各測試 docstring 中的 "Mutation check:" 段落：(a) 2.8 移除 reset_peer toxic → 無 rollback → sentinel 行存在 → 缺席斷言 fail；(b) 2.9 移除 conn.close() → busy>0 → leak 斷言 fail；(c) 2.11 移除 CIRCUIT_BREAKER_ENABLED patch → circuit 永不開 → state≠OPEN 斷言 fail
- [ ] 2.13 本地容器驗證（code complete, env validation pending）：`docker compose -f docker-compose.test.yml up -d && conda run -n mes-dashboard pytest tests/integration/test_real_oracle_fault_injection.py --run-integration-real -v` 全綠；`contract/api_development_contract.md` 無需調整（ORA-00028 → DB_CONNECTION_FAILED 不改變現有文件化 envelope 格式）

## 3. Phase 3 — Soak workload + `/internal/metrics`（PR #5）

- [ ] 3.1 新增 Flask route `src/mes_dashboard/routes/internal_routes.py`：`GET /internal/metrics`，三層 gate：
  - **Layer 1（blueprint registration gate）**：`src/mes_dashboard/app.py` 的 app factory 只在 app config `register_internal_metrics=True` 時 import + `register_blueprint()`；production config factory **連 import 都不做**，讓 route 在 URL map 裡不存在
  - **Layer 2（runtime env gate）**：handler 第一行檢查 `os.getenv("INTERNAL_METRICS_ENABLED") == "1"`，否則 `not_found_error()`
  - **Layer 3（loopback defense-in-depth）**：`request.remote_addr not in {"127.0.0.1", "::1"}` → `not_found_error()`
- [ ] 3.2 新增 `src/mes_dashboard/services/internal_metrics_service.py`：收集 **7 類指標**，回 dict：
  - `pool` — SQLAlchemy pool checkout / checkin / size / overflow
  - `duckdb` — 臨時檔總 bytes、檔案數
  - `redis` — key count（依 prefix 分類）
  - `spool` — `QUERY_SPOOL_DIR` 使用量（bytes / file_count）
  - `worker_rss` — 每個 gunicorn worker PID 的 RSS bytes
  - `circuit_breaker` — 當前 state + 失敗計數
  - `rq` — **每個 RQ queue 的 `pending` / `started` / `failed` / `finished` / `deferred` 深度**
- [ ] 3.3 新增單元測試 `tests/routes/test_internal_routes.py`（6 個）：
  - `config.register_internal_metrics=False` → URL map 不含 `/internal/metrics`（asserts `app.url_map` 無此 rule）
  - `config.register_internal_metrics=True` + `INTERNAL_METRICS_ENABLED` 未設 → 404
  - `config.register_internal_metrics=True` + env 設為 `"0"` → 404
  - `config.register_internal_metrics=True` + env 設為 `"1"` + remote_addr 非 loopback → 404
  - `config.register_internal_metrics=True` + env 設為 `"1"` + loopback → 200 + **7 類** key 齊全
  - production config factory 不 import `internal_routes` module（assert `"mes_dashboard.routes.internal_routes" not in sys.modules` 在 production config 載入後）
- [ ] 3.4 更新 `contract/api_inventory.md`：新增 `/internal/metrics` **Internal-only** 條目；明確標註「不是 admin API 的過渡階段、不進任何 production deploy config、只服務 testing / nightly / soak workflow」
- [ ] 3.5 新增 `tests/integration/test_soak_workload.py`（掛 `@pytest.mark.soak`）：
  - [ ] 3.5.1 fixture `soak_config` 支援 `duration_seconds` / `sample_interval_seconds`（預設 1800 / 30）
  - [ ] 3.5.2 spawn `gunicorn_workers(n=2)` 搭配 `INTERNAL_METRICS_ENABLED=1`
  - [ ] 3.5.3 背景 thread 用 5 個 endpoint 輪發 2–5 req/s（Query Tool、Reject History、Hold Overview、WIP Overview、Resource History）
  - [ ] 3.5.4 另一 thread 每 30s `MetricsProbe.snapshot()` append 到時序 list
  - [ ] 3.5.5 跑完後斷言 D5 的 **6 條性質**（pool slope、duckdb cap、redis convergence、rss growth、circuit breaker transitions、**rq queue depth**尾段 ≤ 首段 × 1.5）
  - [ ] 3.5.6 總是 dump 時序為 `soak-metrics-<timestamp>.json` artifact
  - [ ] 3.5.7 在檔頭 docstring 寫清楚「30 分 default 抓短至中期 leak、120 分 dispatch 抓中長期、超過 120 分不在自動 CI 範圍；通過 ≠ 證明無 leak」定位聲明
- [ ] 3.6 新增 `scripts/soak_local.sh`：本地 5 分鐘縮水版（`duration=300 interval=30`）
- [ ] 3.7 新增 `.github/workflows/soak-tests.yml`：
  - 週日 `cron: "0 4 * * 0"` + `workflow_dispatch`（input `duration_seconds` 上限 7200）
  - `timeout-minutes: 150`（容納 120 分 dispatch 覆寫 + 啟停緩衝）
  - 上傳 `soak-metrics-*.json` artifact、保留 30 天
- [ ] 3.8 Mutation check：
  - 暫時把 `_query_execution` 的 `finally: connection.close()` 註解 → `test_soak_workload` 應 FAIL（pool slope 上升）
  - 暫時把 circuit breaker 的 half-open 過渡邏輯改成每次都 open/close → `circuit_breaker_transitions` 斷言 FAIL
- [ ] 3.9 本地跑 `./scripts/soak_local.sh` 全綠、artifact 產出

## 4. Phase 4 — Pre-merge gate 升級（PR #6 — **條件觸發**）

- [ ] 4.1 等 Phase 1.B 累積 20 天 stability data（20 × 3 = 60 runs）
- [ ] 4.2 整理 `docs/real_infra_stability_report.md`：`pass_rate` / `p95_wall_time` / 每檔 flakiness 根因
- [ ] 4.3 對齊門檻（**數學上誠實的 100%**）：
  - 若 `pass_rate == 100%`（60 runs 內 0 失敗）且每檔 `p95_wall_time < 180s` → 進 4.4
  - 若不達標 → 跳到 4.A 分支處理 flakiness，不動 gate
  - **不用 99%**：60-run window 下 1 次失敗 = 98.3%，寫 99% 看似允許偶發實際等於要求 100%，會造成政策文件的信任缺口
- [ ] 4.4 新增 `.github/workflows/backend-tests.yml` 的 `real-infra-smoke` job（PR required check）：
  - 在 `pull_request` 觸發
  - 只跑 `test_multi_worker_concurrency.py` + `test_redis_chaos.py` + `test_real_multi_worker.py` + `--run-integration-real`
  - `timeout-minutes: 10`
  - 失敗 block merge
- [ ] 4.5 保留既有 `nightly-integration-real` job 繼續跑全量（新舊並存，不是搬家）
- [ ] 4.6 新增 `docs/ci_real_infra_gate_policy.md`：
  - 門檻定義（`pass_rate == 100%` over 20-day × 60-run window；未來若要放寬到 99.0% 必須先擴樣到 ≥ 100 runs，並列明 60-run 下假 99% 的數學陷阱）
  - 量測方法、升級流程
  - 降回觸發條件（過去 7 天 pre-merge flaky rate > 1% → 立即 revert PR）
  - 授權條款註記（`gvenzl/oracle-xe:21-slim` 使用條款連結）
- [ ] 4.7 分支 4.A — 不達標時：
  - 每個 flakiness 根因開 `fix-<slug>` OpenSpec change
  - triage.md 登記 fix 連結
  - 本 PR 只 land Phase 1–3，pre-merge 升級延後

## 5. Phase 5 — 全量驗收 + Triage

- [ ] 5.1 啟動完整服務：`./scripts/start_server.sh start`；healthcheck 正常
- [ ] 5.2 跑後端全量：`conda run -n mes-dashboard pytest tests/ -v`
- [ ] 5.3 跑後端 integration real（含新增）：`conda run -n mes-dashboard pytest --run-integration-real tests/integration/ -v`
- [ ] 5.4 跑 Oracle fault injection：`docker compose -f docker-compose.test.yml up -d && conda run -n mes-dashboard pytest --run-integration-real tests/integration/test_real_oracle_fault_injection.py -v`
- [ ] 5.5 跑 soak 本地 5 分鐘：`./scripts/soak_local.sh`
- [ ] 5.6 跑前端 Vitest：`cd frontend && npm test`
- [ ] 5.7 跑 Playwright（用 `~/.cache/ms-playwright/`，**禁跑 `playwright install`**）：`cd frontend && npx playwright test`
- [ ] 5.8 收集 fail/error/skip 輸出
- [ ] 5.9 建立 `openspec/changes/harden-real-infra-test-coverage/triage.md`，對每筆 failure 執行：
  - 步驟 A：比對 spec Scenario — 不符即 **TEST_BUG**
  - 步驟 B：手動重現 — 違反 spec 即 **CODE_BUG**
  - 步驟 C：mock shape 與 envelope 不一致 — **TEST_BUG**
  - 步驟 D：timing / 環境不穩 — **FLAKY_TEST**
- [ ] 5.10 **TEST_BUG** 在本 PR 修；triage.md 記「修正前 vs 修正後」
- [ ] 5.11 **CODE_BUG**：不在本 PR 修；保持 `xfail(strict=False, reason='see fix-<slug>')`；另開 `fix-<slug>` OpenSpec change；triage.md 登記 change 路徑
- [ ] 5.12 proposal.md `Discovered Regressions` 區段補全 table
- [ ] 5.13 重跑 5.1–5.7，確認剩下的 FAIL 僅為已登記 `xfail` CODE_BUG

## 6. 文件與 PR 切分

- [ ] 6.1 CLAUDE.md Project Commands 新增：
  - `docker compose -f docker-compose.test.yml up -d` / `down`
  - `conda run -n mes-dashboard pytest --run-integration-real tests/integration/test_real_oracle_fault_injection.py -v`
  - `./scripts/soak_local.sh`
  - `python scripts/measure_real_infra_stability.py --runs 3`
- [ ] 6.2 每 PR 描述必附：
  - Mutation check 驗證記錄（哪一行被移除 → 哪些測試 FAIL）
  - 相關 Scenario 對照
  - 本批若有 CODE_BUG 發現 → 列 follow-up change 連結
- [ ] 6.3 最終驗收：
  - [ ] `openspec validate harden-real-infra-test-coverage --strict` 通過
  - [ ] `openspec status` 4/4 artifacts complete
  - [ ] 所有新測試 green（或 `xfail` 指向 follow-up change）
  - [ ] `triage.md` 每筆 failure 有分類與後續動作
  - [ ] `Discovered Regressions` 清單完整
  - [ ] `docs/ci_real_infra_gate_policy.md` 落地（若 Phase 4 達標）
