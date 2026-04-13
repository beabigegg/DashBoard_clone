# TDD — MES Dashboard 測試設計文件

> 版本：1.0 | 日期：2026-04-08 | 狀態：正式版

---

## 1. 測試範圍與目標

### 1.1 測試範圍

| 模組 | 測試範圍 |
|------|----------|
| 路由層（routes/） | API 端點功能、HTTP 方法與狀態碼、請求參數驗證、回應格式 |
| 服務層（services/） | 商業邏輯正確性、快取策略、非同步任務提交與狀態管理 |
| 核心基礎設施（core/） | Circuit Breaker 狀態機、Rate Limit、CSRF、記憶體防護、Redis 客戶端 |
| SQL 層（sql/） | SQL 載入正確性、參數綁定、前後端 SQL 計算結果一致性 |
| 認證系統 | LDAP 認證流程、Session 管理、Admin 角色驗證 |
| 前端核心模組（frontend/src/core/） | compute.js 衍生計算、api.js 請求格式 |

### 1.2 測試目標

- 確保所有 API 端點在正常輸入下回傳正確結果與格式
- 驗證快取命中/未中的行為一致性
- 確保安全機制（CSRF、Rate Limit、Circuit Breaker）正常觸發
- 驗證非同步任務提交、輪詢、結果取回的完整流程
- 確保 SQL 計算結果與前端 DuckDB-WASM 計算結果一致（parity 測試）
- 確保邊界值與錯誤輸入的處理符合預期

### 1.3 不測試範圍

| 項目 | 原因 |
|------|------|
| Oracle 資料庫內部實作 | 唯讀存取，非本系統管轄；使用 Mock 模擬 |
| 外部 LDAP API 邏輯 | 第三方服務，使用 Mock |
| LLM API 回應品質 | AI 輸出非確定性，無法寫死預期值 |
| 前端 UI 渲染（E2E UI） | 本文件聚焦後端；前端有 Node test runner 基礎測試 |
| Redis / Oracle 外部服務可用性 | 整合測試需另行配置，單元測試全部 Mock |

---

## 2. 測試環境

### 2.1 技術堆疊

| 項目 | 工具 | 版本 |
|------|------|------|
| 測試框架 | pytest | `pyproject.toml` 中指定 |
| HTTP 測試 | Flask `test_client()` | 隨 Flask 版本 |
| Mock | `unittest.mock`, `pytest` fixtures | 標準庫 |
| 測試設定 | `pytest.ini` | 根目錄 |
| 前端測試 | Node.js test runner | Node.js 22+ |
| 覆蓋率 | pytest-cov（選用） | — |

### 2.2 測試環境設定（`tests/conftest.py`）

測試執行時自動注入以下環境變數（隔離生產設定）：

```python
FLASK_ENV=testing
REDIS_ENABLED=false       # 預設關閉 Redis，避免需要真實 Redis
RUNTIME_CONTRACT_ENFORCE=false
SLOW_QUERY_THRESHOLD=1.0
WATCHDOG_RUNTIME_DIR=./tmp
```

### 2.3 測試分類與執行旗標

| 測試類型 | 執行方式 | 說明 |
|----------|----------|------|
| 單元測試（預設） | `pytest tests/` | 不需要 Oracle/Redis，全部 Mock |
| 整合測試 | `pytest tests/ --run-integration` | 需要真實 Oracle 連線（從 `.env` 讀取） |
| E2E 測試（本地） | `./scripts/run_e2e.sh` | 需要完整環境，自動檢查本地伺服器狀態，log 至 `logs/e2e_local.log` |
| E2E 測試（雙 target） | `E2E_REMOTE_URL=http://host:port ./scripts/run_e2e.sh` | 先跑本地，再跑遠端 sequential；遠端 log 至 `logs/e2e_remote.log` |
| E2E 測試（直接） | `pytest tests/ --run-e2e` | 可用 `E2E_BASE_URL` / `E2E_BASE_PATH` 指向指定站台 |
| 前端測試 | `npm --prefix frontend test` | Node.js test runner |

### 2.4 主要 Fixtures（`tests/conftest.py`）

| Fixture | 說明 |
|---------|------|
| `app` | 建立 Flask TestingConfig 應用實例 |
| `client` | Flask test client |
| `mock_db` | Mock Oracle 連線池 |
| `mock_redis` | Mock Redis 客戶端 |

---

## 3. 測試類型

### 3.1 單元測試（Unit Test）

- **對象**：`core/`、`services/`、`sql/` 中的獨立函式與商業邏輯
- **策略**：完全 Mock 外部依賴（Oracle、Redis、外部 API），只測目標邏輯
- **命名規則**：`test_[功能]_[情境]_[預期結果]`
- **檔案位置**：`tests/test_*.py`

### 3.2 整合測試（Integration Test）

- **對象**：API 端點的完整請求 → 回應流程，含真實 DB 查詢
- **策略**：使用 `--run-integration` 旗標，載入 `.env`，連線真實 Oracle
- **代表測試**：`tests/test_api_integration.py`, `tests/test_auth_integration.py`
- **注意**：整合測試僅在有 Oracle 連線的環境執行，CI/CD 需配置 DB 連線

### 3.3 SQL 計算一致性測試（Parity Test）

- **對象**：後端 SQL 計算結果 vs 前端 DuckDB-WASM 衍生計算結果
- **策略**：後端執行查詢，前端 core 模組讀取同一份資料，驗證兩者數值一致
- **代表測試**：
  - `tests/test_frontend_compute_parity.py`
  - `tests/test_frontend_duckdb_parity.py`
  - `tests/test_frontend_hold_history_parity.py`
  - `tests/test_frontend_resource_history_parity.py`
  - `tests/test_msd_duckdb_parity.py`
  - `tests/test_hold_history_sql_parity.py`
  - `tests/test_resource_history_sql_parity.py`

### 3.4 前端模組測試

- **對象**：`frontend/src/core/` 下的 JavaScript 模組
- **工具**：Node.js 內建 test runner（`node --test`）
- **執行**：`npm --prefix frontend test`

---

## 4. 測試案例

### 4.1 M10 — 認證與授權

#### 認證流程（`tests/test_auth_routes.py`, `test_auth_service.py`）

| 編號 | 測試案例 | 輸入 | 預期結果 | 優先級 |
|------|----------|------|----------|--------|
| TC-AUTH-001 | LDAP 登入成功 | 有效帳密 | 200 + Session 建立 | P0 |
| TC-AUTH-002 | LDAP 登入失敗 | 錯誤帳密 | 401 + 無 Session | P0 |
| TC-AUTH-003 | 未登入存取受保護 API | 無 Session | 401 Unauthorized | P0 |
| TC-AUTH-004 | 登出後 Session 清除 | 已登入 → 登出 | Session 失效 | P0 |
| TC-AUTH-005 | Admin 權限檢查 | 非 admin Email 存取 admin API | 403 Forbidden | P0 |
| TC-AUTH-006 | Admin 可存取管理 API | Admin Email 帳號 | 200 正常回應 | P0 |
| TC-AUTH-007 | 本地認證（DEV only） | LOCAL_AUTH_ENABLED=true，有效帳密 | 200 + Session | P1 |
| TC-AUTH-008 | 本地認證禁止於 PRODUCTION | LOCAL_AUTH_ENABLED=true，FLASK_ENV=production | 強制停用 | P0 |

#### 權限控制（`tests/test_permissions.py`）

| 編號 | 測試案例 | 預期結果 | 優先級 |
|------|----------|----------|--------|
| TC-PERM-001 | `is_admin_logged_in()` — admin email | True | P0 |
| TC-PERM-002 | `is_admin_logged_in()` — 一般 email | False | P0 |
| TC-PERM-003 | Admin only 頁面未帶 admin session | 重導或 403 | P0 |

### 4.2 M1 — WIP 查詢（`tests/test_wip_routes.py`, `test_wip_service.py`）

| 編號 | 測試案例 | 輸入 | 預期結果 | 優先級 |
|------|----------|------|----------|--------|
| TC-WIP-001 | WIP 概況 API 正常回應 | GET /api/wip/overview | 200 + 矩陣資料 | P0 |
| TC-WIP-002 | WIP 快取命中 | 第二次呼叫 | 結果一致，Oracle 未被呼叫 | P0 |
| TC-WIP-003 | WIP 明細分頁 | per_page=50, page=2 | 回傳第 2 頁資料 | P1 |
| TC-WIP-004 | Autocomplete 前綴搜尋 | prefix="ABC1" | 回傳符合的批號清單 | P1 |

### 4.3 M2 — Hold 分析（`tests/test_hold_routes.py`, `test_hold_history_routes.py`）

| 編號 | 測試案例 | 輸入 | 預期結果 | 優先級 |
|------|----------|------|----------|--------|
| TC-HOLD-001 | Hold 明細 API | GET /api/hold/detail | 200 + Hold 批次清單 | P0 |
| TC-HOLD-002 | Hold 概況 Matrix | GET /api/hold-overview | 200 + 矩陣資料 | P0 |
| TC-HOLD-003 | Hold 歷史查詢 | 日期範圍 7 天 | 200 + 趨勢資料 | P0 |
| TC-HOLD-004 | Hold SQL parity | 後端 SQL 結果 vs 前端 compute | 數值一致 | P1 |

### 4.4 M4 — 品質與良率分析（`tests/test_reject_history_routes.py`, `test_yield_alert_routes.py`）

| 編號 | 測試案例 | 輸入 | 預期結果 | 優先級 |
|------|----------|------|----------|--------|
| TC-REJECT-001 | 不良歷史同步查詢 | 日期範圍 ≤ 7 天 | 200 + 直接回傳結果 | P0 |
| TC-REJECT-002 | 不良歷史非同步觸發 | 日期範圍 > 10 天 | 202 + job_id | P0 |
| TC-REJECT-003 | 非同步任務輪詢 | GET /api/reject-history/job/<id> | 回傳 pending/running/done | P0 |
| TC-REJECT-004 | 非同步任務完成取結果 | 任務完成後輪詢 | 200 + 查詢結果 | P0 |
| TC-REJECT-005 | Batch Pareto API | 有效篩選條件 | 200 + Pareto 統計 | P1 |
| TC-REJECT-006 | 不良歷史匯出 | GET /api/reject-history/export | 200 + Excel 檔案 | P1 |
| TC-YIELD-001 | 良率警示清單 | GET /api/yield-alert/alerts | 200 + 警示清單 | P0 |
| TC-YIELD-002 | 良率鑽取分析 | GET /api/yield-alert/drilldown-context | 200 + 分析結果 | P1 |
| TC-QC-001 | QC-GATE 狀態 | GET /api/qc-gate/status | 200 + 站點狀態矩陣 | P0 |

### 4.5 M5 — 材料追溯（`tests/test_material_trace_routes.py`, `test_trace_routes.py`）

| 編號 | 測試案例 | 輸入 | 預期結果 | 優先級 |
|------|----------|------|----------|--------|
| TC-TRACE-001 | 材料追溯查詢提交 | POST /api/material-trace/query | 202 + job_id | P0 |
| TC-TRACE-002 | 追溯任務完成 | 輪詢 job_id | 200 + 追溯結果 | P0 |
| TC-TRACE-003 | 批次追蹤工具 | POST /query-tool（LOT 模式） | 202 + job_id | P1 |
| TC-TRACE-004 | 材料追溯匯出 | GET /api/material-trace/export | 200 + 匯出檔案 | P1 |

### 4.6 M8 — 異常偵測（`tests/test_anomaly_detection_scheduler.py`）

| 編號 | 測試案例 | 預期結果 | 優先級 |
|------|----------|----------|--------|
| TC-ANOMALY-001 | 異常摘要 API | GET /api/analytics/anomaly-summary → 200 | P1 |
| TC-ANOMALY-002 | 排程觸發偵測 | 手動呼叫 recalculate → 後台任務啟動 | P1 |
| TC-ANOMALY-003 | DuckDB 運算不衝突 | 異常偵測 namespace 與使用者查詢獨立 | P1 |

### 4.7 健康檢查與系統狀態（`tests/test_health_routes.py`）

| 編號 | 測試案例 | 預期結果 | 優先級 |
|------|----------|----------|--------|
| TC-HEALTH-001 | `/health` 正常回應 | 200 + status:ok | P0 |
| TC-HEALTH-002 | `/health/deep` 回應 | 200 + 各元件狀態詳情 | P0 |
| TC-HEALTH-003 | DB 不可用時 `/health` | 200 + DB status: degraded | P1 |
| TC-HEALTH-004 | Redis 不可用時 `/health` | 200 + Redis status: disabled | P1 |

### 4.8 API 契約（`tests/test_api_contract.py`, `test_runtime_contract.py`）

| 編號 | 測試案例 | 預期結果 | 優先級 |
|------|----------|----------|--------|
| TC-CONTRACT-001 | 所有 API 回應符合統一格式 | `{ "status": "ok"/"error", ... }` | P0 |
| TC-CONTRACT-002 | 所有錯誤回應包含 message | `{ "status": "error", "message": "..." }` | P0 |
| TC-CONTRACT-003 | 欄位契約一致性 | 後端回傳欄位名稱與 `shared/field_contracts.json` 一致 | P1 |

### 4.9 前端核心模組（`frontend/tests/*.test.js`）

| 編號 | 測試案例 | 預期結果 | 優先級 |
|------|----------|----------|--------|
| TC-FE-001 | `compute.js` WIP KPI 衍生計算 | 計算結果正確 | P0 |
| TC-FE-002 | `wip-derive.js` 篩選邏輯 | 篩選後結果集正確 | P0 |
| TC-FE-003 | `api.js` 請求格式 | 產生正確 URL 與參數 | P1 |

---

## 5. 異常與邊界測試

### 5.1 錯誤輸入

| 編號 | 情境 | 輸入 | 預期結果 |
|------|------|------|----------|
| TC-ERR-001 | 缺少必填欄位（日期範圍） | `{}` | 400 Bad Request + 明確訊息 |
| TC-ERR-002 | 非法 JSON | `Content-Type: application/json`, body 非 JSON | 400 Bad Request |
| TC-ERR-003 | 超過 Body 大小限制 | JSON body > 256KB | 413 Request Entity Too Large |
| TC-ERR-004 | SQL 注入嘗試（table_name） | `"users; DROP TABLE users"` | 400（白名單驗證拒絕） |
| TC-ERR-005 | 非法 job_id | GET /api/reject-history/job/invalid-id | 404 Not Found |
| TC-ERR-006 | Container ID 超過上限 | 提交 201 個 Container ID | 400 超出上限 |
| TC-ERR-007 | 萬用字元搜尋前綴過短 | prefix="A"（< 4 字元） | 400 前綴長度不足 |

### 5.2 邊界值

| 編號 | 情境 | 輸入 | 預期結果 |
|------|------|------|----------|
| TC-BND-001 | 日期範圍最小值 | start_date = end_date | 正常執行（單日查詢） |
| TC-BND-002 | 不良歷史觸發非同步門檻 | 日期範圍恰好 10 天（REJECT_ASYNC_DAY_THRESHOLD） | 依設定決定同步/非同步 |
| TC-BND-003 | 分頁邊界 | page=1, per_page=最大值 | 正常回傳，不超界 |
| TC-BND-004 | 空查詢結果 | 篩選條件無資料 | 200 + 空陣列（非 404） |
| TC-BND-005 | Spool 大小接近上限 | 查詢結果接近 `REJECT_ENGINE_MAX_RESULT_MB` | 回傳截斷或 413 |

### 5.3 安全性測試（`tests/test_auth_integration.py`, `tests/test_rate_limit_routes.py`）

| 編號 | 情境 | 預期結果 |
|------|------|----------|
| TC-SEC-001 | 未帶 Session 存取受保護 API | 401 Unauthorized |
| TC-SEC-002 | 一般使用者存取 Admin API（/api/system-status） | 403 Forbidden |
| TC-SEC-003 | CSRF 保護：Admin mutation 未帶 Token | 403 CSRF 驗證失敗 |
| TC-SEC-004 | Rate Limit：高成本 API 超出頻率上限 | 429 Too Many Requests + Retry-After |
| TC-SEC-005 | Session 過期後重新存取 | 401，需重新登入 |
| TC-SEC-006 | 非法 table_name（不在白名單） | 400，拒絕查詢 |

### 5.4 韌性與並發測試（`tests/test_circuit_breaker.py`, `tests/test_global_concurrency.py`）

| 編號 | 情境 | 預期結果 |
|------|------|----------|
| TC-RES-001 | Circuit Breaker CLOSED → OPEN | 失敗率達閾值後，後續請求立即回傳 503（不再嘗試 Oracle） |
| TC-RES-002 | Circuit Breaker HALF_OPEN → CLOSED | 冷卻期後探測請求成功，Circuit 恢復 CLOSED |
| TC-RES-003 | Circuit Breaker HALF_OPEN → OPEN | 探測請求仍失敗，Circuit 重回 OPEN |
| TC-RES-004 | 高並發同時請求 | 超出 `HEAVY_QUERY_REJECT_THRESHOLD` 後回傳 503（流量保護） |
| TC-RES-005 | Worker RSS 超過 warn_ratio | 觸發 GC，日誌記錄警告 |
| TC-RES-006 | Worker RSS 超過 hard_ratio | 觸發 Worker 重啟（由 Watchdog 管理） |
| TC-RES-007 | Redis 連線失敗降級 | `REDIS_ENABLED=false` → 快取全部 miss，直接查 Oracle |

### 5.5 非同步任務邊界（`tests/test_async_query_job_service.py`）

| 編號 | 情境 | 預期結果 |
|------|------|----------|
| TC-ASYNC-001 | 任務提交後立即輪詢（pending 狀態） | `{ "status": "pending" }` |
| TC-ASYNC-002 | 任務執行中輪詢（running 狀態） | `{ "status": "running" }` |
| TC-ASYNC-003 | 任務逾時（超過 job_timeout） | `{ "status": "failed", "message": "timeout" }` |
| TC-ASYNC-004 | TTL 過期後輪詢已失效 job_id | 404 Not Found |
| TC-ASYNC-005 | 同一 job_id 重複提交 | 回傳既有任務狀態（不重複建立） |

### 5.6 快取一致性（`tests/test_cache.py`, `test_cache_integration.py`）

| 編號 | 情境 | 預期結果 |
|------|------|----------|
| TC-CACHE-001 | 快取命中 | 回傳快取資料，Oracle 不被呼叫 |
| TC-CACHE-002 | 快取未中 | 查詢 Oracle，結果寫入快取 |
| TC-CACHE-003 | 快取 TTL 過期後 | 重新查詢 Oracle，更新快取 |
| TC-CACHE-004 | Redis 連線中斷後恢復 | 重新連線後快取正常運作 |
| TC-CACHE-005 | Parquet DF 序列化/反序列化 | 資料型別與數值完整保留 |
