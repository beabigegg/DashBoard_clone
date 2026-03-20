## Context

系統現有兩套認證機制：
- **管理員登入**：`/admin/login`（Flask Jinja template），LDAP 驗證 → `session["admin"]`，受 `@admin_required` decorator 保護
- **報表系統**：`/portal-shell`（Vue SPA），完全無認證

現有基礎設施：
- LDAP API：`https://adapi.panjit.com.tw/api/v1/ldap/auth`，回傳 `{username, displayName, mail, department, telephoneNumber, domain}`，JWT 有效期 8 小時
- SQLite + MySQL 雙層同步：LogStore + MetricsHistoryStore → SyncWorker → MySQL
- Flask session：server-side，Redis-backed（或 filesystem fallback）
- 管理員判斷：`ADMIN_EMAILS` 環境變數（目前值 `ymirliu@panjit.com.tw`）

目標：統一為單一登入系統，所有人需登入才能用報表，管理員功能自動判斷。

## Goals / Non-Goals

**Goals:**
- 所有使用者必須登入才能使用報表系統
- 沿用 LDAP API 認證，所有公司員工皆可登入
- 刪除獨立的管理員登入頁面，統一為單一登入入口
- 登入後若 email 在 ADMIN_EMAILS 中，自動擁有管理員權限
- 記錄完整登入資訊：工號、姓名、部門、email、分機、IP、登入時間、使用時間
- 登入記錄使用 SQLite + MySQL 雙層同步
- Session 8 小時過期
- 前端 5 分鐘 heartbeat 追蹤使用時間

**Non-Goals:**
- 角色/權限管理系統（本次只有「一般使用者」與「管理員」兩級）
- 密碼修改/重設（由 AD 管理）
- 多因素認證
- Remember me / 記住登入狀態

## Decisions

### Decision 1: Session Key 統一（`session["user"]` 取代 `session["admin"]`）

**選擇：所有登入使用者統一存入 `session["user"]`**

```python
session["user"] = {
    "username": "92367",
    "displayName": "ymirliu 劉念萱",
    "real_name": "劉念萱",
    "mail": "ymirliu@panjit.com.tw",
    "department": "MBU1_AssEng Div 封裝工程處",
    "telephoneNumber": "1580",
    "domain": "PANJIT",
    "is_admin": True,  # 登入時即判斷
    "login_time": "2026-03-20T09:42:13",
    "ip": "10.20.30.40",
    "session_id": "uuid4",  # 對應 login_sessions 表的記錄
}
```

- `is_admin` 在登入時一次性判斷（email in ADMIN_EMAILS），避免每次 request 都查
- `session["admin"]` 不再使用

**替代方案：保留 `session["admin"]` 另外加 `session["user"]`** — 增加複雜度，兩套 session 需要同步清理。

### Decision 2: API 端點設計

**選擇：新增 `/api/auth/*` 端點群**

| Method | Path | 用途 | 認證 |
|--------|------|------|------|
| POST | `/api/auth/login` | 登入（JSON API） | 無 |
| POST | `/api/auth/logout` | 登出 + 記錄使用時間 | 需登入 |
| GET | `/api/auth/me` | 取得目前登入狀態 | 無（回傳 null 或使用者資訊） |
| PATCH | `/api/auth/heartbeat` | 更新 last_active | 需登入 |

Login request/response：
```
POST /api/auth/login
Body: {"username": "92367", "password": "xxx"}
Response: {
  "success": true,
  "data": { "username", "displayName", "real_name", "mail",
            "department", "is_admin", "telephoneNumber" }
}
```

Me endpoint（前端 router guard 用）：
```
GET /api/auth/me
Response (已登入): { "success": true, "data": { ...user... } }
Response (未登入): { "success": true, "data": null }
```

**理由：** JSON API 讓 Vue 前端可用 fetch 處理，不需要 form POST + redirect。`/api/auth/me` 讓前端 router guard 在頁面載入時檢查登入狀態。

### Decision 3: 前端 Router Guard

**選擇：全局 `beforeEach` guard + `/api/auth/me` 檢查**

```javascript
// router.js
let authChecked = false;
let isAuthenticated = false;

router.beforeEach(async (to) => {
  if (to.path === '/login') return true;

  if (!authChecked) {
    const res = await fetch('/api/auth/me');
    const data = await res.json();
    isAuthenticated = data.data !== null;
    authChecked = true;
  }

  if (!isAuthenticated) {
    return { path: '/login', query: { next: to.fullPath } };
  }
  return true;
});
```

- 只在首次導航時呼叫 `/api/auth/me`（結果 cache 到記憶體）
- Session 過期時後端 API 會回 401 → 前端攔截並導向登入頁
- 登入成功後手動設定 `isAuthenticated = true`，不需再呼叫 me

### Decision 4: Heartbeat 機制

**選擇：前端 setInterval 5 分鐘 + 後端 SQLite UPDATE**

```javascript
// useAuth.js composable
setInterval(() => {
  fetch('/api/auth/heartbeat', { method: 'PATCH' });
}, 5 * 60 * 1000);
```

後端收到 heartbeat：
```python
@user_auth_bp.route("/api/auth/heartbeat", methods=["PATCH"])
def heartbeat():
    session_id = session["user"]["session_id"]
    login_session_store.update_last_active(session_id)
    return success_response(None)
```

- 只做 1 次 SQLite UPDATE（WHERE session_id = ?），< 1ms
- SyncWorker 自然會將 last_active 同步到 MySQL
- 影響評估：200 人同時在線 = 0.67 次/秒，低於 MetricsCollector 的寫入頻率

### Decision 5: 登入記錄 SQLite Store（LoginSessionStore）

**選擇：獨立 SQLite 檔案 `logs/login_sessions.sqlite`**

```sql
CREATE TABLE IF NOT EXISTS login_sessions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id TEXT NOT NULL,
    emp_id TEXT NOT NULL,
    username TEXT NOT NULL,
    display_name TEXT NOT NULL,
    real_name TEXT,
    department TEXT,
    email TEXT,
    phone TEXT,
    domain TEXT,
    ip TEXT,
    login_time TEXT NOT NULL,
    last_active TEXT,
    logout_time TEXT,
    duration_sec INTEGER,
    is_admin INTEGER DEFAULT 0,
    sync_id TEXT,
    synced INTEGER DEFAULT 0
);
CREATE INDEX IF NOT EXISTS idx_login_time ON login_sessions(login_time);
CREATE INDEX IF NOT EXISTS idx_synced ON login_sessions(synced);
CREATE INDEX IF NOT EXISTS idx_session_id ON login_sessions(session_id);
```

MySQL 對應表 `dashboard_login_sessions`：
```sql
CREATE TABLE IF NOT EXISTS dashboard_login_sessions (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    sync_id VARCHAR(255) NOT NULL,
    session_id VARCHAR(100) NOT NULL,
    emp_id VARCHAR(20) NOT NULL,
    username VARCHAR(50) NOT NULL,
    display_name VARCHAR(100) NOT NULL,
    real_name VARCHAR(50),
    department VARCHAR(200),
    email VARCHAR(200),
    phone VARCHAR(20),
    domain VARCHAR(50),
    ip VARCHAR(45),
    login_time DATETIME(3) NOT NULL,
    last_active DATETIME(3),
    logout_time DATETIME(3),
    duration_sec INT,
    is_admin TINYINT DEFAULT 0,
    synced_at DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3),
    UNIQUE INDEX idx_sync_id (sync_id),
    INDEX idx_login_time (login_time),
    INDEX idx_emp_id (emp_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
```

遵循 LogStore 模式：
- 寫入路徑：登入時 INSERT、heartbeat 時 UPDATE last_active、登出時 UPDATE logout_time + duration_sec
- `sync_id` 格式：`{hostname}_login_{rowid}`
- SyncWorker 每輪用 REPLACE INTO（因為 heartbeat 會更新同一筆）而非 INSERT IGNORE

**替代方案：與 admin_logs.sqlite 共用** — 不同 table schema，shared DB 增加耦合。

### Decision 6: SyncWorker 同步策略（REPLACE INTO）

**選擇：login_sessions 用 `REPLACE INTO` 而非 `INSERT IGNORE`**

```python
def _sync_login_sessions(self):
    rows = self._login_store.get_unsynced()
    with get_mysql_connection() as conn:
        for row in rows:
            conn.execute(text("""
                REPLACE INTO dashboard_login_sessions
                (sync_id, session_id, emp_id, ..., last_active, logout_time, duration_sec)
                VALUES (:sync_id, :session_id, :emp_id, ..., :last_active, :logout_time, :duration_sec)
            """), row)
    self._login_store.mark_synced([r["id"] for r in rows])
```

**理由：** 與 logs 不同，login_sessions 是可變記錄（heartbeat 更新 last_active、logout 更新 logout_time）。REPLACE INTO 以 sync_id 為 key 覆蓋舊值，確保 MySQL 總是持有最新狀態。

### Decision 7: 刪除 Admin 登入頁面

**改動範圍：**

| 項目 | 動作 |
|------|------|
| `routes/auth_routes.py` | 刪除（包含 rate limiter 邏輯搬移到新的 user_auth_routes） |
| `templates/login.html` | 刪除 |
| `core/permissions.py` | `is_admin_logged_in()` → 改查 `session["user"]["is_admin"]` |
| `core/permissions.py` | `get_current_admin()` → 改為 `get_current_user()` |
| `core/permissions.py` | `@admin_required` → 改查 `session["user"]` + `is_admin` |
| `app.py` | 移除 `auth_bp` 註冊，新增 `user_auth_bp` 註冊 |
| `app.py` | `/api/portal/navigation` 改從 `session["user"]` 讀取 admin 狀態 |

新增 `@login_required` decorator：
```python
def login_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if "user" not in session:
            return jsonify({"error": "未登入", "login_required": True}), 401
        return f(*args, **kwargs)
    return decorated
```

### Decision 8: displayName 拆分 real_name

LDAP 回傳 `displayName` 格式為 `"ymirliu 劉念萱"`（帳號 + 空格 + 中文名）。

```python
def _extract_real_name(display_name: str) -> str:
    """從 displayName 拆出中文姓名。"""
    parts = display_name.strip().split(" ", 1)
    if len(parts) == 2:
        return parts[1]  # "劉念萱"
    return display_name  # fallback: 回傳原值
```

### Decision 9: Session 過期設定

```python
app.config["PERMANENT_SESSION_LIFETIME"] = timedelta(hours=8)
session.permanent = True  # 在登入時設定
```

- 8 小時與 LDAP JWT 有效期一致
- `session.permanent = True` 啟用 `PERMANENT_SESSION_LIFETIME`（Flask 預設 31 天，需覆寫）

### Decision 10: Rate Limiter 搬移

現有 `auth_routes.py` 中的 rate limiter（Redis-backed + in-memory fallback，5 次/5 分鐘）搬移到新的 `user_auth_routes.py`，邏輯不變。

## File Changes

### New Files
| File | Purpose |
|------|---------|
| `src/mes_dashboard/core/login_session_store.py` | 登入記錄 SQLite store（LoginSessionStore） |
| `src/mes_dashboard/routes/user_auth_routes.py` | 使用者認證 API（login/logout/me/heartbeat） |
| `frontend/src/portal-shell/views/LoginPage.vue` | Vue 登入頁面 |
| `frontend/src/portal-shell/composables/useAuth.js` | 認證 composable（auth 狀態、heartbeat、login/logout 方法） |

### Modified Files
| File | Changes |
|------|---------|
| `src/mes_dashboard/core/permissions.py` | `session["admin"]` → `session["user"]`；新增 `@login_required`；修改 `@admin_required`；修改 `is_admin_logged_in()` / `get_current_admin()` |
| `src/mes_dashboard/core/sync_worker.py` | 新增 `_sync_login_sessions()` 方法 |
| `src/mes_dashboard/app.py` | 移除 `auth_bp`、新增 `user_auth_bp`；`/api/portal/navigation` 改讀 `session["user"]`；session lifetime 設定 |
| `scripts/init_mysql.py` | 新增 `dashboard_login_sessions` 表 |
| `frontend/src/portal-shell/router.js` | 新增 auth guard + login route |
| `frontend/src/portal-shell/App.vue` | admin 判斷改從 useAuth 取；移除 admin login/logout link；改用統一 logout |
| `frontend/src/portal-shell/routeContracts.js` | 新增 `/login` route contract |
| `.env.example` | 新增 `PERMANENT_SESSION_LIFETIME` |

### Deleted Files
| File | Reason |
|------|--------|
| `src/mes_dashboard/routes/auth_routes.py` | 管理員登入路由，功能搬至 `user_auth_routes.py` |
| `src/mes_dashboard/templates/login.html` | 管理員登入 Jinja template，改為 Vue 登入頁面 |
