## Why

Portal sidebar 的抽屜分類（報表類/查詢類/開發工具）與頁面歸屬目前寫死在 `portal.html` Jinja2 模板中，任何導航結構的變更都需要改程式碼並重新部署。Admin 應能透過現有的「頁面管理」UI 動態管理抽屜與頁面分配，無需開發介入。

## What Changes

- 擴展 `data/page_status.json` 資料結構，加入 `drawers` 陣列定義抽屜（名稱、排序、可見性），並在每個 page 中加入 `drawer_id` 和 `order` 欄位
- 擴展 `page_registry.py` 服務層，新增 drawer CRUD 函式與 page-to-drawer 指派函式
- 新增 admin API endpoints：drawer 的增刪改查、頁面的抽屜指派與排序
- **BREAKING**: `portal.html` sidebar 從寫死 HTML 改為 `{% for drawer in drawers %}` 動態渲染
- 擴展現有 `/admin/pages` UI，加入抽屜管理區塊與頁面拖拉/下拉分配功能
- 頁面的 `released`/`dev` 狀態邏輯與 `can_view_page()` 權限檢查保持不變

## Capabilities

### New Capabilities
- `drawer-management`: Admin 可透過 API 與 UI 對抽屜進行 CRUD 操作（新增、刪除、改名、排序）
- `page-drawer-assignment`: Admin 可透過 API 與 UI 將頁面指派到不同抽屜，並控制頁面在抽屜內的排序

### Modified Capabilities
- `portal-drawer-navigation`: 導航結構從寫死改為從 JSON 配置動態渲染，抽屜分類與頁面歸屬由資料驅動

## Impact

- **資料層**: `data/page_status.json` 結構擴展（向下相容，新增欄位有預設值）
- **服務層**: `page_registry.py` 新增 drawer 相關函式
- **路由層**: `admin_routes.py` 新增 drawer API endpoints
- **模板層**: `portal.html` sidebar 區塊重寫為動態渲染
- **前端層**: `admin/pages.html` UI 擴展
- **無影響**: 各頁面本身的路由、模板、Vite 模組均不需變更
