## Context

WIP Dashboard 已完成基礎重建（wip-dashboard-rebuild），使用 `DWH.DW_PJ_LOT_V` 作為資料來源。目前提供 Package 與 Status 篩選，但缺乏 WORKORDER 與 LOT ID 的搜尋功能。資料中存在 DUMMY lot 會影響統計準確性。

現有架構：
- 後端：`wip_service.py` 提供查詢函數，`wip_routes.py` 提供 API 端點
- 前端：`wip_overview.html` 與 `wip_detail.html` 使用 vanilla JavaScript

## Goals / Non-Goals

**Goals:**
- 預設排除 DUMMY lot，提升數據準確性
- 提供 WORKORDER 與 LOT ID 模糊搜尋功能
- 使用 autocomplete 下拉選單提升使用體驗
- 保持現有自動刷新機制正常運作

**Non-Goals:**
- 不實作複雜的全文搜尋引擎
- 不儲存使用者篩選偏好（session/cookie）
- 不修改資料庫結構或新增索引

## Decisions

### 1. DUMMY 排除策略

**決定**: 在後端 SQL 查詢中加入 `LOTID NOT LIKE '%DUMMY%'` 條件

**理由**:
- 簡單直接，無需前端配合
- 統一處理，確保所有 API 一致性
- 如需檢視 DUMMY 資料，可透過參數 `include_dummy=true` 覆蓋

**替代方案**: 前端過濾 → 效能差，資料量大時不適用

### 2. 模糊搜尋實作方式

**決定**: 使用 SQL `LIKE '%keyword%'` 搭配 API 參數

**理由**:
- 無需額外依賴（如 Elasticsearch）
- 資料量（約 9000 lots）在可接受範圍內
- 實作簡單，維護成本低

**替代方案**:
- Oracle Text 全文搜尋 → 過度設計
- 前端 fuzzy match → 需載入全部資料，效能差

### 3. 下拉選單資料載入策略

**決定**: 採用「搜尋觸發載入」而非預載全部選項

**API 設計**:
```
GET /api/wip/meta/search?type=workorder&q=GA26&limit=20
GET /api/wip/meta/search?type=lotid&q=GA26011&limit=20
```

**理由**:
- WORKORDER 與 LOTID 數量龐大，預載全部不實際
- 使用者輸入 2-3 字元後觸發搜尋，回傳前 20 筆匹配結果
- 減少初始載入時間與記憶體使用

**替代方案**: 預載全部 → LOTID 有 9000+ 筆，瀏覽器記憶體負擔大

### 4. 前端 Autocomplete 實作

**決定**: 使用 HTML5 `<datalist>` 搭配自訂 JavaScript

**理由**:
- 無需引入第三方函式庫（如 Select2, Choices.js）
- 保持與現有架構一致（vanilla JS）
- 瀏覽器原生支援，效能佳

**替代方案**: 第三方函式庫 → 增加依賴，bundle size 增加

### 5. 篩選器 UI 配置

**WIP Overview (大表)**:
- 新增 WORKORDER 與 LOTID 搜尋框於現有區域上方
- 套用篩選後，矩陣與摘要同步更新

**WIP Detail**:
- 在現有 Package/Status 篩選器旁新增 WORKORDER 與 LOTID 搜尋框
- 維持現有篩選邏輯，新篩選條件為 AND 關係

## Risks / Trade-offs

| 風險 | 緩解措施 |
|------|----------|
| SQL LIKE 效能問題 | 限制搜尋結果數量（limit=20），要求至少輸入 2 字元 |
| datalist 瀏覽器相容性 | 目標瀏覽器（Chrome/Edge）支援良好，IE 不在支援範圍 |
| 搜尋延遲影響體驗 | 加入 debounce（300ms），顯示 loading 指示 |
| DUMMY 排除影響特定使用情境 | 提供 `include_dummy` 參數供進階使用 |

## API 變更摘要

| 端點 | 變更 |
|------|------|
| `/api/wip/overview/*` | 新增 `workorder`, `lotid`, `include_dummy` 參數 |
| `/api/wip/detail/<wc>` | 新增 `workorder`, `lotid`, `include_dummy` 參數 |
| `/api/wip/meta/search` | **新增** - 模糊搜尋 WORKORDER/LOTID |
