## Why

目前報表系統（/portal-shell）無需登入即可使用，任何人只要知道 URL 就能存取所有報表。管理員功能有獨立的 `/admin/login` 登入頁，但一般使用者完全不需要認證。

需要解決的問題：
- 報表資料包含生產敏感資訊，不應無認證開放
- 無法追蹤誰在使用系統、使用頻率、在線時長
- 管理員登入與系統登入分離，管理員需要登入兩次（一次進系統、一次進後台）
- 缺乏使用者行為數據（登入記錄、部門分佈、尖峰時段等）

## What Changes

新增統一的使用者登入系統，取代現有的分離式管理員登入。

- **新增 Vue 登入頁面**：`/portal-shell/login`，未認證使用者由 Vue Router guard 攔截導入
- **新增後端認證 API**：`POST /api/auth/login`、`GET /api/auth/me`、`POST /api/auth/logout`、`PATCH /api/auth/heartbeat`
- **認證方式不變**：沿用現有 LDAP API（`adapi.panjit.com.tw`），所有公司員工皆可登入
- **統一管理員判斷**：登入後若 email 匹配 `ADMIN_EMAILS`，自動解鎖管理功能，不再需要獨立的管理員登入
- **刪除 `/admin/login`**：管理員登入頁面及相關 template 移除
- **Session 過期 8 小時**：與 LDAP JWT token 有效期一致（一個班次）
- **Heartbeat 機制**：前端每 5 分鐘 ping 後端，更新 `last_active` 時間
- **登入記錄**：SQLite + MySQL 雙層同步（沿用現有 SyncWorker 模式），記錄工號、姓名、部門、email、IP、分機、登入/登出時間、使用時長

## Capabilities

### New Capabilities
- `user-auth-api`: 使用者認證 API — login、logout、me、heartbeat 四個端點
- `user-auth-session`: Flask session 管理 — `session["user"]` 儲存登入狀態，8 小時過期
- `login-session-store`: 登入記錄 SQLite store — LoginSessionStore，記錄登入/登出/heartbeat 事件
- `login-page`: Vue 登入頁面 — LoginPage.vue + router guard

### Modified Capabilities
- `admin-permissions`: `@admin_required` 改為檢查 `session["user"]` + ADMIN_EMAILS，取代 `session["admin"]`
- `portal-navigation`: `/api/portal/navigation` 改為從 `session["user"]` 判斷 admin 狀態
- `sync-worker`: SyncWorker 新增 `_sync_login_sessions()` 方法
- `mysql-schema-init`: `scripts/init_mysql.py` 新增 `dashboard_login_sessions` 表

## Impact

- **後端新增 2 個模組**：`core/login_session_store.py`（登入記錄 SQLite store）、`routes/user_auth_routes.py`（認證 API）
- **後端修改 4 個模組**：`core/permissions.py`、`core/sync_worker.py`、`app.py`、`scripts/init_mysql.py`
- **後端刪除**：`routes/auth_routes.py`（admin 登入路由）、`templates/login.html`（admin 登入模板）
- **前端新增 2 個檔案**：`portal-shell/views/LoginPage.vue`、`portal-shell/composables/useAuth.js`
- **前端修改 3 個檔案**：`portal-shell/router.js`（加 guard）、`portal-shell/App.vue`（改 admin 判斷）、`portal-shell/routeContracts.js`（加 login route）
- **環境變數調整**：`PERMANENT_SESSION_LIFETIME` 設為 8 小時
- **部署影響**：無新依賴；現有 LDAP、MySQL、Redis 設定不變
