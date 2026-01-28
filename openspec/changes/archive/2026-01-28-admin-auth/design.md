# Admin Auth 技術設計

## 架構概述

```
┌─────────────────────────────────────────────────────────────┐
│                        Flask App                            │
├─────────────────────────────────────────────────────────────┤
│  before_request                                             │
│  ┌─────────────────────────────────────────────────────┐   │
│  │  check_page_access()                                 │   │
│  │  - 檢查 request.endpoint                             │   │
│  │  - 查詢 PageRegistry 頁面狀態                         │   │
│  │  - 若為 dev 且非管理員 → 403                          │   │
│  └─────────────────────────────────────────────────────┘   │
├─────────────────────────────────────────────────────────────┤
│  Routes                                                     │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐      │
│  │ auth_routes  │  │ admin_routes │  │ wip_routes   │ ...  │
│  │ /admin/login │  │ /admin/pages │  │ /wip-overview│      │
│  │ /admin/logout│  │ /admin/api/* │  │ /wip-detail  │      │
│  └──────────────┘  └──────────────┘  └──────────────┘      │
├─────────────────────────────────────────────────────────────┤
│  Services                                                   │
│  ┌──────────────┐  ┌──────────────┐                        │
│  │ auth_service │  │ page_registry│                        │
│  │ - LDAP 驗證  │  │ - 頁面狀態   │                        │
│  │ - 管理員檢查 │  │ - JSON 儲存  │                        │
│  └──────────────┘  └──────────────┘                        │
└─────────────────────────────────────────────────────────────┘
```

## 資料結構

### Session 資料

```python
# 管理員登入後存入 session
session['admin'] = {
    'username': '92367',
    'displayName': 'ymirliu 劉念萱',
    'mail': 'ymirliu@panjit.com.tw',
    'department': 'MBU1_AssEng Div 封裝工程處',
    'login_time': '2026-01-28T14:00:00'
}
```

### 頁面狀態設定檔 (`data/page_status.json`)

```json
{
  "pages": [
    {
      "route": "/",
      "name": "首頁",
      "status": "released"
    },
    {
      "route": "/wip-overview",
      "name": "WIP 即時概況",
      "status": "released"
    },
    {
      "route": "/wip-detail",
      "name": "WIP 明細",
      "status": "released"
    },
    {
      "route": "/hold-detail",
      "name": "Hold 明細",
      "status": "released"
    },
    {
      "route": "/tables",
      "name": "表格總覽",
      "status": "released"
    },
    {
      "route": "/resource",
      "name": "機台狀態",
      "status": "released"
    },
    {
      "route": "/excel-query",
      "name": "Excel 批次查詢",
      "status": "released"
    }
  ],
  "api_public": true
}
```

## 模組設計

### 1. auth_service.py - LDAP 認證服務

```python
# src/mes_dashboard/services/auth_service.py

LDAP_API_BASE = "https://adapi.panjit.com.tw"
ADMIN_EMAILS = ["ymirliu@panjit.com.tw"]  # 可從 config 讀取

def authenticate(username: str, password: str, domain: str = "PANJIT") -> dict | None:
    """
    呼叫 LDAP API 驗證使用者。

    Returns:
        成功: {'username': ..., 'displayName': ..., 'mail': ..., 'department': ...}
        失敗: None
    """
    response = requests.post(
        f"{LDAP_API_BASE}/api/v1/ldap/auth",
        json={"username": username, "password": password, "domain": domain},
        timeout=10
    )
    data = response.json()
    if data.get("success"):
        return data["user"]
    return None


def is_admin(user: dict) -> bool:
    """檢查使用者是否為管理員。"""
    return user.get("mail", "").lower() in [e.lower() for e in ADMIN_EMAILS]
```

### 2. page_registry.py - 頁面狀態管理

```python
# src/mes_dashboard/services/page_registry.py

import json
from pathlib import Path
from threading import Lock

DATA_FILE = Path("data/page_status.json")
_lock = Lock()
_cache = None

def _load() -> dict:
    """載入頁面狀態設定。"""
    global _cache
    if _cache is None:
        if DATA_FILE.exists():
            _cache = json.loads(DATA_FILE.read_text(encoding="utf-8"))
        else:
            _cache = {"pages": [], "api_public": True}
    return _cache


def _save(data: dict) -> None:
    """儲存頁面狀態設定。"""
    global _cache
    DATA_FILE.parent.mkdir(parents=True, exist_ok=True)
    DATA_FILE.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    _cache = data


def get_page_status(route: str) -> str:
    """取得頁面狀態 ('released' | 'dev')，預設為 'dev'。"""
    with _lock:
        data = _load()
        for page in data.get("pages", []):
            if page["route"] == route:
                return page.get("status", "dev")
        return "dev"  # 未註冊的頁面預設為 dev


def set_page_status(route: str, status: str, name: str = None) -> None:
    """設定頁面狀態。"""
    with _lock:
        data = _load()
        for page in data.get("pages", []):
            if page["route"] == route:
                page["status"] = status
                if name:
                    page["name"] = name
                _save(data)
                return
        # 新增頁面
        data.setdefault("pages", []).append({
            "route": route,
            "name": name or route,
            "status": status
        })
        _save(data)


def get_all_pages() -> list:
    """取得所有頁面設定。"""
    with _lock:
        return _load().get("pages", [])


def is_api_public() -> bool:
    """API 端點是否公開（不受權限控制）。"""
    with _lock:
        return _load().get("api_public", True)
```

### 3. permissions.py - 權限檢查

```python
# src/mes_dashboard/core/permissions.py

from functools import wraps
from flask import session, abort, redirect, url_for, request

def is_admin_logged_in() -> bool:
    """檢查管理員是否已登入。"""
    return "admin" in session


def get_current_admin() -> dict | None:
    """取得目前登入的管理員資訊。"""
    return session.get("admin")


def admin_required(f):
    """裝飾器：需要管理員登入。"""
    @wraps(f)
    def decorated(*args, **kwargs):
        if not is_admin_logged_in():
            return redirect(url_for("auth.login", next=request.url))
        return f(*args, **kwargs)
    return decorated
```

### 4. auth_routes.py - 認證路由

```python
# src/mes_dashboard/routes/auth_routes.py

from flask import Blueprint, render_template, request, redirect, url_for, session, flash
from mes_dashboard.services.auth_service import authenticate, is_admin

auth_bp = Blueprint("auth", __name__, url_prefix="/admin")


@auth_bp.route("/login", methods=["GET", "POST"])
def login():
    """管理員登入頁面。"""
    error = None

    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")

        if not username or not password:
            error = "請輸入帳號和密碼"
        else:
            user = authenticate(username, password)
            if user is None:
                error = "帳號或密碼錯誤"
            elif not is_admin(user):
                error = "您不是管理員，無法登入後台"
            else:
                # 登入成功
                session["admin"] = {
                    "username": user["username"],
                    "displayName": user["displayName"],
                    "mail": user["mail"],
                    "department": user["department"],
                    "login_time": datetime.now().isoformat()
                }
                next_url = request.args.get("next", url_for("portal_index"))
                return redirect(next_url)

    return render_template("login.html", error=error)


@auth_bp.route("/logout")
def logout():
    """登出。"""
    session.pop("admin", None)
    return redirect(url_for("portal_index"))
```

### 5. admin_routes.py - 管理員路由

```python
# src/mes_dashboard/routes/admin_routes.py

from flask import Blueprint, render_template, jsonify, request
from mes_dashboard.core.permissions import admin_required
from mes_dashboard.services.page_registry import get_all_pages, set_page_status

admin_bp = Blueprint("admin", __name__, url_prefix="/admin")


@admin_bp.route("/pages")
@admin_required
def pages():
    """頁面管理介面。"""
    return render_template("admin/pages.html")


@admin_bp.route("/api/pages", methods=["GET"])
@admin_required
def api_get_pages():
    """API: 取得所有頁面。"""
    return jsonify({"success": True, "pages": get_all_pages()})


@admin_bp.route("/api/pages/<path:route>", methods=["PUT"])
@admin_required
def api_update_page(route):
    """API: 更新頁面狀態。"""
    data = request.get_json()
    status = data.get("status")
    name = data.get("name")

    if status not in ("released", "dev"):
        return jsonify({"success": False, "error": "Invalid status"}), 400

    route = "/" + route if not route.startswith("/") else route
    set_page_status(route, status, name)
    return jsonify({"success": True})
```

### 6. app.py 修改 - 加入權限檢查

```python
# 在 create_app() 中加入

from mes_dashboard.routes.auth_routes import auth_bp
from mes_dashboard.routes.admin_routes import admin_bp
from mes_dashboard.services.page_registry import get_page_status, is_api_public
from mes_dashboard.core.permissions import is_admin_logged_in

def create_app(config_name: str | None = None) -> Flask:
    app = Flask(__name__, template_folder="templates")

    # ... 現有設定 ...

    # Session 設定
    app.secret_key = os.environ.get("SECRET_KEY", "dev-secret-key-change-in-prod")

    # 註冊認證路由
    app.register_blueprint(auth_bp)
    app.register_blueprint(admin_bp)

    # 權限檢查中介層
    @app.before_request
    def check_page_access():
        # 跳過靜態檔案
        if request.endpoint == "static":
            return

        # API 端點檢查
        if request.path.startswith("/api/"):
            if is_api_public():
                return  # API 公開
            # 若 API 不公開，檢查管理員
            if not is_admin_logged_in():
                return jsonify({"error": "Unauthorized"}), 401
            return

        # 跳過認證相關頁面
        if request.path.startswith("/admin/login") or request.path.startswith("/admin/logout"):
            return

        # 管理員頁面需要登入
        if request.path.startswith("/admin/"):
            if not is_admin_logged_in():
                return redirect(url_for("auth.login", next=request.url))
            return

        # 檢查頁面狀態
        page_status = get_page_status(request.path)
        if page_status == "dev" and not is_admin_logged_in():
            return render_template("403.html"), 403

    # 注入模板變數
    @app.context_processor
    def inject_admin():
        return {
            "is_admin": is_admin_logged_in(),
            "admin_user": session.get("admin")
        }

    # ... 現有路由 ...
```

## UI 設計

### 登入頁面 (`login.html`)

簡潔的登入表單：
- 標題：管理員登入
- 帳號輸入框（支援工號或 email）
- 密碼輸入框
- 登入按鈕
- 錯誤訊息顯示區

### 頁面管理介面 (`admin/pages.html`)

表格形式：
| 路由 | 名稱 | 狀態 | 操作 |
|------|------|------|------|
| / | 首頁 | Released | [切換] |
| /wip-overview | WIP 即時概況 | Released | [切換] |
| /new-feature | 新功能 | Dev | [切換] |

功能：
- 點擊狀態切換 released/dev
- 批次操作按鈕
- 即時儲存（不需重整）

### 導航列調整

在 `_base.html` 或各頁面模板中加入：

```html
<!-- 右上角登入狀態 -->
<div class="admin-status">
    {% if is_admin %}
        <span>{{ admin_user.displayName }}</span>
        <a href="{{ url_for('admin.pages') }}">頁面管理</a>
        <a href="{{ url_for('auth.logout') }}">登出</a>
    {% else %}
        <a href="{{ url_for('auth.login') }}">管理員登入</a>
    {% endif %}
</div>
```

### 403 頁面 (`403.html`)

當存取 dev 頁面時顯示：
- 標題：頁面開發中
- 說明：此頁面尚未發布，僅管理員可存取
- 返回首頁連結

## 設定

### config/settings.py 新增

```python
class Config:
    # ... 現有設定 ...

    # Auth 設定
    LDAP_API_URL = "https://adapi.panjit.com.tw"
    ADMIN_EMAILS = ["ymirliu@panjit.com.tw"]
    SECRET_KEY = os.environ.get("SECRET_KEY", "dev-secret-key")

    # Session 設定
    SESSION_TYPE = "filesystem"  # 或 redis
    PERMANENT_SESSION_LIFETIME = 28800  # 8 小時
```

## 安全考量

1. **Secret Key**: 生產環境必須設定環境變數 `SECRET_KEY`
2. **HTTPS**: LDAP API 已使用 HTTPS
3. **Session**: JWT Token 儲存於 server-side session，不暴露給前端
4. **管理員清單**: 透過設定檔控制，可隨時更新

## 測試計畫

1. **auth_service 測試**
   - 正確帳密驗證成功
   - 錯誤帳密驗證失敗
   - 管理員判斷正確

2. **page_registry 測試**
   - 讀取/寫入頁面狀態
   - 未註冊頁面預設為 dev
   - 並發存取安全

3. **權限中介層測試**
   - Released 頁面所有人可存取
   - Dev 頁面非管理員返回 403
   - 管理員可存取所有頁面

4. **路由測試**
   - 登入/登出流程
   - 頁面管理 API
