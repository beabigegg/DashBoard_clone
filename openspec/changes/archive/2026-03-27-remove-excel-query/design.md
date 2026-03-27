## Context

Excel Query 是前站使用的批次查詢工具，使用 `get_db_connection()` 直接建立非池化連線（2 處），繞過連線池管理。上線後不再需要此功能。目前涉及 13 個檔案 + 1 目錄需刪除，20 個檔案需編輯移除引用。

## Goals / Non-Goals

**Goals:**
- 完整移除 Excel Query 前後端程式碼及相關測試
- 消除 2 處 direct connection 使用
- 保持所有現有測試通過、build 成功

**Non-Goals:**
- 不重構連線池機制（已有 connection-pool-filter-cache-reform 處理）
- 不調整其他 legacy 頁面

## Decisions

### Decision 1: 一次性完整移除，不分階段

**選擇**: 單次移除所有 Excel Query 相關程式碼

**理由**: Excel Query 無外部依賴者，無需 deprecation 期。分階段移除只會增加中間態的維護成本。

**替代方案**: 先移除前端路由再移除後端 — 不必要，因為無人使用。

### Decision 2: 刪除順序 — 先刪檔案，後編輯引用

**選擇**: 先刪除 13 個獨立檔案/目錄，再編輯 20 個引用檔案

**理由**: 先刪除可讓 IDE/linter 幫助找出遺漏的引用。編輯引用時可依 backend → frontend config → contracts → tests 順序執行，降低遺漏風險。

### Decision 3: Contract 檔案同步更新

**選擇**: 在同一變更中更新 `api_inventory.md`、`css_inventory.md`、`field_contracts.json`

**理由**: 遵循 CLAUDE.md Rule #1.4 和 Rule #2.4，contract 必須與程式碼同步。

## Risks / Trade-offs

- **遺漏引用** → 透過 `pytest` 全套測試 + `npm run build` 驗證。grep 搜尋 `excel.query` / `excel_query` / `excelQuery` 確認無殘留。
- **Build output 殘留** → `static/dist/excel-query.js*` 為 build 產物，刪除後 rebuild 即不再產生。
- **Template 引用** → `excel_query.html` 刪除後若有 render 呼叫會立即 500，但已無路由指向此 template。
