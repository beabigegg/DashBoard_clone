## Context

Portal sidebar 導航結構目前寫死在 `portal.html` (lines 356-421)，包含三個固定分類與十個固定頁面按鈕。頁面的 `released`/`dev` 狀態已經由 `data/page_status.json` + `page_registry.py` 動態管理，但抽屜分類與頁面歸屬仍需改程式碼。

現有架構：
- `data/page_status.json`: 頁面狀態持久化（JSON file, atomic write, thread-safe cache）
- `page_registry.py`: 服務層（CRUD + cache + lock）
- `admin_routes.py` (lines 629-667): Admin API（GET/PUT pages）
- `admin/pages.html`: Admin UI（頁面狀態切換表格）
- `portal.html`: Jinja2 模板，`{% if can_view_page() %}` 控制可見性

關鍵約束：
- 專案使用 Jinja2 shell + Vite JS 混合架構，所有 11 個頁面一致
- 無資料庫，所有配置用 JSON file 持久化
- 需要向下相容：現有 `page_status.json` 的 page entries 不可遺失

## Goals / Non-Goals

**Goals:**
- Admin 可透過 UI 對抽屜進行 CRUD（新增、改名、刪除、排序）
- Admin 可透過 UI 指定頁面歸屬的抽屜與排序
- Portal sidebar 根據 JSON 配置動態渲染（Jinja2 for loop）
- 向下相容：首次載入時自動從現有 hardcoded 結構產生初始配置
- 為未來全面 Vite SPA 化鋪路：API 設計可直接被前端 fetch 使用

**Non-Goals:**
- 不做全面 Vite SPA 化（本次只做 Jinja2 動態渲染）
- 不做頁面路由的動態新增（頁面路由仍在 `app.py` 中定義）
- 不改變 `released`/`dev` 狀態的邏輯
- 不做拖拉排序（使用上下箭頭或數字排序即可）
- 不做多使用者即時同步（Admin 改完，其他使用者刷新頁面即可看到）

## Decisions

### 1. 資料結構：擴展 `page_status.json`

**選擇**: 在現有 JSON 中新增 `drawers` 頂層欄位，並在 page 中加入 `drawer_id` 和 `order`。

```json
{
  "drawers": [
    { "id": "reports", "name": "報表類", "order": 1 },
    { "id": "queries", "name": "查詢類", "order": 2 },
    { "id": "dev-tools", "name": "開發工具", "order": 3, "admin_only": true }
  ],
  "pages": [
    {
      "route": "/wip-overview",
      "name": "WIP 即時概況",
      "status": "released",
      "drawer_id": "reports",
      "order": 1
    }
  ],
  "api_public": true
}
```

**替代方案**: 獨立 `navigation.json` 檔案。
**放棄原因**: 頁面狀態和歸屬是同一份資料的不同面向，拆成兩個檔案增加同步複雜度。現有的 atomic write + lock 機制可以直接沿用。

### 2. 向下相容：自動遷移策略

**選擇**: `page_registry.py` 的 `_load()` 函式在讀取時檢測是否存在 `drawers` 欄位。若不存在，自動注入預設的三個抽屜定義並根據目前 portal.html 的 hardcoded 映射填充 `drawer_id`。遷移後立即 `_save()` 持久化。

**理由**: 零手動操作部署。首次啟動即完成遷移。

### 3. iframe 策略：維持現行邏輯

**選擇**: 一般頁面每個獨立 iframe，admin 工具頁面共用 `toolFrame`。動態渲染時根據 `drawer.admin_only` 判斷是否使用共用 iframe。

**理由**: 最小變動。iframe 行為和 `portal.js` 的 `activateTab()` 邏輯不需改動。

**具體做法**: 每個 page 的 iframe id 由 route 推導（如 `/wip-overview` → `wipOverviewFrame`），`admin_only` 抽屜下的頁面共用 `toolFrame` 並使用 `data-tool-src` 切換。

### 4. Admin API 設計

**選擇**: 在現有 `admin_routes.py` 中擴展，新增 drawer endpoints。

| Endpoint | Method | 用途 |
|---|---|---|
| `GET /admin/api/drawers` | GET | 取得所有抽屜 |
| `POST /admin/api/drawers` | POST | 新增抽屜 |
| `PUT /admin/api/drawers/<id>` | PUT | 更新抽屜（改名、排序） |
| `DELETE /admin/api/drawers/<id>` | DELETE | 刪除抽屜（需先移走其下頁面） |
| `PUT /admin/api/pages/<route>` | PUT | 擴展現有 endpoint，支援 `drawer_id` 和 `order` |

**替代方案**: RESTful nested resource `/admin/api/drawers/<id>/pages`。
**放棄原因**: 頁面已經有獨立的 PUT endpoint，加上 `drawer_id` 欄位更簡單。

### 5. Admin UI：擴展 `/admin/pages`

**選擇**: 在現有 `admin/pages.html` 上方加入抽屜管理區塊，下方頁面列表加入抽屜歸屬下拉選單和排序控制。

**理由**: 使用者已經知道去哪裡管理頁面，擴展比新頁面更自然。

### 6. Portal 模板動態化

**選擇**: `app.py` 的 portal route 讀取 drawers + pages 配置，組裝成結構化資料傳入 Jinja2 context。`portal.html` 用 `{% for %}` 渲染 sidebar 和 iframes。

**理由**: 維持現有 Jinja2 shell 架構一致性，`can_view_page()` server-side 過濾不需改動。

## Risks / Trade-offs

- **[Risk] JSON 並發寫入** → 現有 `_lock` + atomic write 已處理。單行程 Flask 部署下無問題。如果未來 multi-worker 部署，需考慮 file lock（但這是既有風險，非本次引入）。
- **[Risk] 刪除抽屜時頁面孤立** → API 層強制檢查：抽屜下仍有頁面時禁止刪除，回傳 409 Conflict。
- **[Risk] 首次遷移時 hardcoded 映射不正確** → 遷移邏輯使用明確的 route-to-drawer 映射表，與現有 portal.html 一一對應。
- **[Trade-off] 未歸屬抽屜的頁面不會出現在 sidebar** → 這是刻意設計。子頁面（如 `/wip-detail`, `/hold-detail`）不需出現在 sidebar 中，它們沒有 `drawer_id` 即可。

## Open Questions

- 無。探索階段已充分討論並確認方向。
