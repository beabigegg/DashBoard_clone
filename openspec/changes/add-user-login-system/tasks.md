## 1. 登入記錄 Store（後端核心）

- [x] 1.1 建立 `src/mes_dashboard/core/login_session_store.py`：
  - `LoginSessionStore` class — 沿用 LogStore 模式，獨立 SQLite 檔案 `logs/login_sessions.sqlite`
  - `initialize()` — 建表 `login_sessions`（session_id, emp_id, username, display_name, real_name, department, email, phone, domain, ip, login_time, last_active, logout_time, duration_sec, is_admin, sync_id, synced）
  - `create_session(user_info, ip)` — 登入時復用或新建 session（8h 內同使用者復用既有 session）
  - `update_last_active(session_id)` — heartbeat 時 UPDATE last_active = now
  - `close_session(session_id)` — 登出時 UPDATE logout_time + 計算 duration_sec
  - `get_unsynced(batch_size=500)` — 取 synced=0 的記錄
  - `mark_synced(rowids)` — 批次標記 synced=1
  - `cleanup_synced(older_than_hours=24)` — 清除已同步的舊記錄（登入記錄保留較久）
  - `_generate_sync_id(rowid)` — 格式 `{hostname}_login_{rowid}`
  - Thread-safe：thread-local SQLite connection
  - 環境變數：`LOGIN_SESSION_SQLITE_PATH`（預設 `logs/login_sessions.sqlite`）
- [x] 1.2 建立 `get_login_session_store()` singleton factory

## 2. MySQL Schema 擴充

- [x] 2.1 修改 `scripts/init_mysql.py`：
  - 新增 `dashboard_login_sessions` 表（sync_id UNIQUE, session_id, emp_id, username, display_name, real_name, department, email, phone, domain, ip, login_time DATETIME(3), last_active, logout_time, duration_sec, is_admin, synced_at）
  - INDEX: sync_id (UNIQUE), login_time, emp_id
  - 冪等執行（CREATE TABLE IF NOT EXISTS）
- [x] 2.2 手動驗證表建立成功（透過 SyncWorker 自動初始化）

## 3. SyncWorker 擴充

- [x] 3.1 修改 `src/mes_dashboard/core/sync_worker.py`：
  - `__init__` 新增 `self._login_store = login_store or get_login_session_store()`
  - 新增 `_sync_login_sessions()` 方法 — `REPLACE INTO dashboard_login_sessions`（用 REPLACE 而非 INSERT IGNORE，因為 heartbeat 會更新同一筆）
  - `_run()` loop 新增 `_sync_login_sessions()` 呼叫
  - `_cleanup_synced()` 新增 `self._login_store.cleanup_synced()` 呼叫

## 4. 權限系統改造

- [x] 4.1 修改 `src/mes_dashboard/core/permissions.py`：
  - `is_admin_logged_in()` → 改查 `session.get("user", {}).get("is_admin", False)`
  - `get_current_admin()` → 改為 `get_current_user()`，回傳 `session.get("user")`
  - `@admin_required` → 先檢查 `"user" in session`，再檢查 `session["user"]["is_admin"]`；用 `unauthorized_error()` / `forbidden_error()` 取代 `jsonify`
  - 新增 `is_user_logged_in()` → `"user" in session`
  - 新增 `@login_required` decorator — 未登入回 `unauthorized_error("未登入")`

## 5. 使用者認證 API

- [x] 5.1 建立 `src/mes_dashboard/routes/user_auth_routes.py`：
  - Blueprint `user_auth_bp`
  - Rate limiter 從 `auth_routes.py` 搬移（Redis-backed + in-memory fallback，5 次/5 分鐘）
  - Rate limiter 只在認證失敗後才記錄（成功登入不消耗次數）
  - `POST /api/auth/login`、`POST /api/auth/logout`、`GET /api/auth/me`、`PATCH /api/auth/heartbeat`
- [x] 5.2 `_extract_real_name(display_name)` helper — 從 "ymirliu 劉念萱" 拆出 "劉念萱"

## 6. 刪除舊管理員登入

- [x] 6.1 刪除 `src/mes_dashboard/routes/auth_routes.py`
- [x] 6.2 刪除 `src/mes_dashboard/templates/login.html`
- [x] 6.3 修改 `src/mes_dashboard/app.py`：
  - 移除 `auth_bp` import 和 `register_blueprint(auth_bp)`
  - 新增 `user_auth_bp` import 和 `register_blueprint(user_auth_bp)`
  - `PERMANENT_SESSION_LIFETIME = timedelta(hours=8)`
  - 初始化 LoginSessionStore（與 LogStore、MetricsHistoryStore 同位置）
  - `/api/portal/navigation` 改從 `session["user"]` 讀取 admin 狀態和使用者資訊
  - `/admin/logout` route 移除（改用 `/api/auth/logout`）

## 7. 前端登入頁面

- [x] 7.1 建立 `frontend/src/portal-shell/composables/useAuth.js`：
  - `user` ref、`isAuthenticated` / `isAdmin` computed
  - `checkAuth()`、`login()`、`logout()`
  - `startHeartbeat()` / `stopHeartbeat()` — 5 分鐘間隔，收到 401 自動停止
- [x] 7.2 建立 `frontend/src/portal-shell/views/LoginPage.vue`：
  - 全頁登入（無 header/sidebar）
  - Tailwind CSS（無硬編碼色值）
  - `next` 參數驗證（防止 open redirect）
  - 登入成功後呼叫 `setAuthState(true)` 避免多餘 API 呼叫
- [x] 7.3 修改 `frontend/src/portal-shell/router.js`：
  - 新增 `/login` 靜態路由 → LoginPage
  - `beforeEach` guard + auth 狀態 cache
  - 匯出 `setAuthState()` 供登入/401 使用
- [x] 7.4 修改 `frontend/src/portal-shell/routeContracts.js`：新增 `/login` 到 DEFERRED_ROUTES
- [x] 7.5 修改 `frontend/src/portal-shell/App.vue`：
  - 登入頁面時只渲染 `<RouterView>`（無 shell chrome）
  - 登入後離開 `/login` 時自動重載 navigation
  - 401 攔截器加入 re-entrancy guard + `setAuthState(false)`
- [x] 7.6 前端 401 攔截：API 回應 401 時自動導向 /login

## 8. CSRF 處理

- [x] 8.1 結論：`should_enforce_csrf()` 只對 `/admin/*` 路徑強制執行，`/api/auth/*` 不受影響，無需額外處理。

## 9. 環境設定

- [x] 9.1 更新 `.env.example`：新增 `PERMANENT_SESSION_LIFETIME=28800`、`LOGIN_SESSION_SQLITE_PATH=logs/login_sessions.sqlite`

## 10. 整合測試

- [x] 10.1 啟動 app，驗證 LoginSessionStore 初始化成功
- [x] 10.2 測試完整登入流程：POST /api/auth/login → session 建立 → GET /api/auth/me 回傳使用者
- [x] 10.3 測試管理員判斷：用 92367 登入 → is_admin=true → 管理功能可用
- [x] 10.4 測試登出流程：POST /api/auth/logout → session 清除 → login_session 記錄 logout_time
- [x] 10.5 測試 heartbeat：PATCH /api/auth/heartbeat → last_active 更新
- [x] 10.6 測試 SyncWorker：已啟動（interval=600s），sync_login_sessions 方法就緒
- [x] 10.7 測試前端：/portal-shell → 導向 /login → 登入 → 進入報表 → sidebar 正常
- [x] 10.8 測試管理員功能：登入 92367 → Admin 頁面可存取（管理後台連結 + 頁面管理）
- [x] 10.9 測試未登入 API 回 401、heartbeat 回 401 後自動停止
- [x] 10.10 執行全部測試 `pytest tests/ -v` 確認無 regression（1752 passed, 268 skipped）

## 11. Contract 同步

- [x] 11.1 更新 `contract/api_inventory.md`：新增 /api/auth/* 端點、/admin/api/user-usage-kpi
- [x] 11.2 更新 `contract/css_inventory.md`：新增 `admin-user-usage-kpi/style.css`

## 12. 審核修正

- [x] 12.1 C1: `permissions.py` — `jsonify` → `unauthorized_error()` / `forbidden_error()`
- [x] 12.2 C2: Rate limiter 只在認證失敗後記錄
- [x] 12.3 C3: LoginPage.vue `next` 參數驗證防止 open redirect
- [x] 12.4 C4: 401 攔截器 re-entrancy guard + `setAuthState(false)`
- [x] 12.5 W1: Heartbeat 收到 401 自動 stopHeartbeat
- [x] 12.6 W2: LoginPage.vue CSS 改用 Tailwind utilities
- [x] 12.7 W4: heartbeat sync 只在 synced=1 時重設為 0
- [x] 12.8 W7+W8: 401 時 setAuthState(false)；登入後 setAuthState(true)
- [x] 12.9 App.vue 登入頁隱藏 shell chrome + 登入後重載 navigation
- [x] 12.10 admin/pages apiFetch 解包 json.data

## 13. 使用者 KPI 儀表板

- [x] 13.1 建立 `src/mes_dashboard/services/user_usage_kpi_service.py`：MySQL 優先 / SQLite fallback
- [x] 13.2 admin_routes.py 新增 `/admin/user-usage-kpi` + `/admin/api/user-usage-kpi`
- [x] 13.3 建立 `frontend/src/admin-user-usage-kpi/`（Vue SPA：App.vue + 7 components + style.css）
- [x] 13.4 註冊 routeContracts.js、nativeModuleRegistry.js、vite.config.js
- [x] 13.5 更新 page_registry.py + page_status.json
- [x] 13.6 更新架構文件（route_contracts.json, route_scope_matrix.json, asset_readiness_manifest.json, known_bug_baseline.json, baseline_drawer_visibility.json）

## 14. Session 邏輯修正

- [x] 14.1 create_session 改為復用邏輯：8h 內同使用者復用既有 session
- [x] 14.2 超過 8h 或明確 logout 才結束 session 並建新的
- [x] 14.3 測試隔離：test_auth_integration.py / test_runtime_hardening.py mock login_session_store
