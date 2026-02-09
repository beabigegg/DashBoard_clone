## 1. 資料層：擴展 page_status.json 與 page_registry.py

- [x] 1.1 在 `page_registry.py` 的 `_load()` 中加入自動遷移邏輯：當 `drawers` 欄位不存在時，注入預設三個抽屜並根據 hardcoded 映射表填充每個 page 的 `drawer_id` 和 `order`，然後 `_save()`
- [x] 1.2 新增 drawer CRUD 函式：`get_all_drawers()`, `create_drawer(name, order, admin_only)`, `update_drawer(id, ...)`, `delete_drawer(id)`
- [x] 1.3 擴展 `set_page_status()` 支援 `drawer_id` 和 `order` 參數
- [x] 1.4 新增 `get_navigation_config()` 函式：回傳按 drawer order 排序的巢狀結構（drawers → pages），供 portal route 使用

## 2. API 層：擴展 admin_routes.py

- [x] 2.1 新增 `GET /admin/api/drawers` endpoint，回傳所有抽屜（sorted by order）
- [x] 2.2 新增 `POST /admin/api/drawers` endpoint，建立新抽屜（驗證名稱不重複）
- [x] 2.3 新增 `PUT /admin/api/drawers/<id>` endpoint，更新抽屜名稱/排序/admin_only
- [x] 2.4 新增 `DELETE /admin/api/drawers/<id>` endpoint，刪除空抽屜（有頁面時回傳 409）
- [x] 2.5 擴展現有 `PUT /admin/api/pages/<route>` endpoint，接受 `drawer_id` 和 `order` 欄位（驗證 drawer_id 存在）

## 3. 模板層：portal.html 動態渲染

- [x] 3.1 修改 `app.py` 的 portal route，呼叫 `get_navigation_config()` 取得結構化導航資料，傳入 Jinja2 context
- [x] 3.2 將 `portal.html` sidebar 區塊（lines 356-392）改為 `{% for drawer in drawers %}` 動態渲染，保留 `can_view_page()` 過濾與 `admin_only` 判斷
- [x] 3.3 將 `portal.html` iframe 區塊（lines 394-421）改為動態渲染，根據配置產生 iframe elements
- [x] 3.4 確認 `portal.js` 的 `activateTab()` 與 lazy-load 邏輯在動態 DOM 下正常運作（iframe id 命名規則需一致）

## 4. Admin UI：擴展 /admin/pages

- [x] 4.1 在 `admin/pages.html` 上方加入「抽屜管理」區塊：抽屜列表 + 新增/改名/刪除/排序控制
- [x] 4.2 在頁面列表每一列加入 drawer 歸屬下拉選單（含「未分類」選項）和排序輸入
- [x] 4.3 實作前端 JS：drawer CRUD 操作（呼叫 API → 更新 UI）
- [x] 4.4 實作前端 JS：頁面 drawer 指派操作（下拉變更 → PUT API）

## 5. 驗證

- [x] 5.1 驗證首次啟動遷移：刪除 `page_status.json` 中的 `drawers` 欄位，重啟後確認自動產生正確的預設配置
- [x] 5.2 驗證 portal sidebar 動態渲染：新增/刪除抽屜後刷新 portal，確認 sidebar 正確反映
- [x] 5.3 驗證頁面歸屬變更：改變頁面的 drawer_id 後刷新 portal，確認頁面出現在正確的抽屜中
- [x] 5.4 驗證權限邏輯不變：非 admin 使用者看不到 dev 頁面、看不到 admin_only 抽屜
- [x] 5.5 驗證安全性：非 admin 使用者無法存取 drawer API endpoints
