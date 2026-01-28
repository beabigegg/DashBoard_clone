## Why

此專案是一個開放的查詢平台，所有人皆可存取已發布的頁面。但隨著功能逐漸增加，需要區分：
- **已發布頁面 (Released)**：所有人皆可存取（如 WIP Overview、WIP Detail、Hold Detail）
- **開發中頁面 (Dev)**：僅管理員可存取，用於測試新功能

缺乏權限控制的問題：
- 無法保護開發中的功能不被外部使用者看到
- 無法動態調整頁面的發布狀態
- 沒有管理介面來控制頁面狀態

## What Changes

### 1. 管理員認證系統

使用公司 LDAP API（`https://adapi.panjit.com.tw`）進行身份驗證。

**管理員登入頁面** (`/admin/login`)
- 支援工號或 email 登入
- 驗證通過後檢查是否為管理員
- 若非管理員，顯示「您不是管理員」訊息
- 管理員登入後將 JWT Token 存入 Flask Session

**登出功能** (`/admin/logout`)
- 清除 Session 中的認證資訊
- 重導向至首頁

### 2. 權限控制機制

**頁面狀態定義**
- `released`: 所有人可存取（公開查詢平台）
- `dev`: 僅管理員可存取（開發中功能）

**存取規則**
- 所有人（無論登入與否）：可存取 `released` 狀態的頁面
- 管理員：可存取所有頁面（包含 `dev`）+ 管理介面

**初始已發布頁面**
- `/` - 首頁
- `/wip-overview` - WIP Overview
- `/wip-detail` - WIP Detail
- `/hold-detail` - Hold Detail
- `/tables` - 表格總覽
- 所有 `/api/*` 端點

### 3. 管理員功能

**管理員帳號**
- `ymirliu@panjit.com.tw` 為管理員
- 可透過設定檔擴充管理員清單

**管理員頁面** (`/admin/pages`)
- 顯示所有頁面路由清單
- 每個頁面可設定為 `released` 或 `dev`
- 即時生效，不需重啟服務
- 頁面狀態儲存於 JSON 檔案或資料庫

**管理介面功能**
- 頁面列表：顯示路由、名稱、目前狀態
- 狀態切換：點擊即可切換 released/dev
- 批次操作：可一次將多個頁面設為 released 或 dev
- 新增頁面：當新增路由時自動偵測或手動新增

### 4. 導航列調整

**一般使用者**（未登入或非管理員）
- 僅顯示已發布頁面的導航項目
- 頁面右上角顯示「管理員登入」連結

**管理員狀態**（已登入且為管理員）
- 顯示管理員名稱
- 顯示「登出」按鈕
- 顯示所有頁面（包含開發中）
- 開發中頁面標示 [DEV] 標籤
- 顯示「頁面管理」連結

## Capabilities

### New Capabilities

- `admin-login`: 管理員登入頁面，使用 LDAP API 驗證，僅允許管理員登入
- `admin-pages`: 管理員頁面管理介面，設定頁面 released/dev 狀態
- `auth-middleware`: 權限檢查中介層，dev 頁面僅管理員可存取
- `page-registry`: 頁面註冊系統，管理所有頁面的發布狀態

### Modified Capabilities

- `base-template`: 導航欄根據管理員狀態顯示不同內容

## Impact

**新增檔案**
- `src/mes_dashboard/routes/auth_routes.py` - 認證路由（登入/登出）
- `src/mes_dashboard/routes/admin_routes.py` - 管理員路由（頁面管理）
- `src/mes_dashboard/services/auth_service.py` - LDAP API 客戶端
- `src/mes_dashboard/services/page_registry.py` - 頁面狀態管理
- `src/mes_dashboard/templates/login.html` - 登入頁面
- `src/mes_dashboard/templates/admin/pages.html` - 頁面管理介面
- `src/mes_dashboard/core/permissions.py` - 權限定義與檢查裝飾器
- `data/page_status.json` - 頁面狀態設定檔

**修改檔案**
- `src/mes_dashboard/templates/base.html` - 導航欄登入狀態顯示
- `src/mes_dashboard/app.py` - 註冊認證路由與 before_request 中介層
- `config.py` - 新增認證設定（LDAP API URL、管理員清單、Session 設定）

**向後相容**
- 已發布頁面不受影響，未登入仍可正常存取
- 現有功能不需任何修改
