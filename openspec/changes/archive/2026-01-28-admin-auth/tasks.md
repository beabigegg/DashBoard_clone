# Admin Auth 實作任務

## 後端任務

### Task 1: 新增認證服務
- [x] 建立 `src/mes_dashboard/services/auth_service.py`
- [x] 實作 `authenticate(username, password, domain)` 函數
- [x] 實作 `is_admin(user)` 函數
- [x] 新增 LDAP API 錯誤處理（timeout、連線失敗）

### Task 2: 新增頁面狀態管理服務
- [x] 建立 `src/mes_dashboard/services/page_registry.py`
- [x] 實作 `get_page_status(route)` 函數
- [x] 實作 `set_page_status(route, status, name)` 函數
- [x] 實作 `get_all_pages()` 函數
- [x] 建立 `data/page_status.json` 初始設定檔（現有頁面設為 released）

### Task 3: 新增權限檢查模組
- [x] 建立 `src/mes_dashboard/core/permissions.py`
- [x] 實作 `is_admin_logged_in()` 函數
- [x] 實作 `get_current_admin()` 函數
- [x] 實作 `@admin_required` 裝飾器

### Task 4: 新增認證路由
- [x] 建立 `src/mes_dashboard/routes/auth_routes.py`
- [x] 實作 `GET /admin/login` 登入頁面
- [x] 實作 `POST /admin/login` 登入處理
- [x] 實作 `GET /admin/logout` 登出
- [x] 在 `routes/__init__.py` 註冊 `auth_bp`

### Task 5: 新增管理員路由
- [x] 建立 `src/mes_dashboard/routes/admin_routes.py`
- [x] 實作 `GET /admin/pages` 頁面管理介面
- [x] 實作 `GET /admin/api/pages` 取得所有頁面
- [x] 實作 `PUT /admin/api/pages/<route>` 更新頁面狀態
- [x] 在 `routes/__init__.py` 註冊 `admin_bp`

### Task 6: 修改 app.py
- [x] 新增 Flask session 設定（SECRET_KEY）
- [x] 新增 `before_request` 權限檢查中介層
- [x] 新增 `context_processor` 注入 `is_admin`、`admin_user` 和 `can_view_page`
- [x] 註冊 auth_bp 和 admin_bp

### Task 7: 更新設定
- [x] 在 `config/settings.py` 新增 `LDAP_API_URL` 設定
- [x] 在 `config/settings.py` 新增 `ADMIN_EMAILS` 設定
- [x] 在 `config/settings.py` 新增 `SECRET_KEY` 設定
- [x] 在 `requirements.txt` 新增 `requests` 依賴

## 前端任務

### Task 8: 建立登入頁面
- [x] 建立 `templates/login.html`
- [x] 實作帳號/密碼輸入表單
- [x] 實作錯誤訊息顯示
- [x] 套用現有樣式（與 portal.html 一致）

### Task 9: 建立頁面管理介面
- [x] 建立 `templates/admin/pages.html`
- [x] 實作頁面列表表格（路由、名稱、狀態）
- [x] 實作狀態切換功能（點擊切換 released/dev）
- [x] 實作即時儲存（API 呼叫）
- [x] 實作 Toast 通知

### Task 10: 建立 403 頁面
- [x] 建立 `templates/403.html`
- [x] 顯示「頁面開發中」訊息
- [x] 提供返回首頁連結

### Task 11: 修改導航列
- [x] 在 portal.html 右上角加入管理員登入/登出連結
- [x] 管理員登入後顯示名稱和「頁面管理」連結
- [x] Dev 頁面 tabs 對非管理員隱藏（使用 `can_view_page` 條件渲染）

## 測試任務

### Task 12: 單元測試
- [x] auth_service 測試（LDAP 認證、管理員檢查）
- [x] page_registry 測試（頁面狀態讀寫、並發存取）
- [x] permissions 測試（權限檢查、裝飾器）

### Task 13: 整合測試
- [x] 登入/登出路由測試
- [x] 權限中介層測試（released/dev 頁面存取）
- [x] Admin API 測試（頁面管理）
- [x] Context Processor 測試

### Task 14: E2E 測試
- [x] 完整登入登出流程
- [x] 頁面存取控制流程
- [x] 頁面管理流程
- [x] Portal 動態 tabs 顯示
- [x] Session 持久性
- [x] 安全性場景測試

## 部署任務

### Task 15: 環境設定
- [x] 建立初始 page_status.json（現有頁面設為 released）
- [ ] 設定生產環境 SECRET_KEY 環境變數（部署時處理）
- [x] 確認 LDAP API 連線正常（手動測試通過）
