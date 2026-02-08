## Why

目前仍有部分報表頁維持大型 inline script，且已遷移的 Vite 模組存在實際行為缺口（例如 KPI 0% 呈現、矩陣篩選選取、模組作用域匯出失敗）。這造成「舊版 Jinja 報表效果」與「新架構模組化」之間存在落差，無法完全發揮 Vite 在複用、可維護性與前端運算轉移的優勢。

## What Changes

- 將 WIP Overview / WIP Detail 的報表互動完整納入 Vite entry，保留既有頁面操作語意與 drill-down 路徑。
- 修復已遷移頁面的核心行為缺陷（Resource History 模組初始化、Resource Status KPI 與矩陣交互）。
- 統一報表前端 API 呼叫路徑，優先透過 `MesApi` 以承接既有 retry/backoff 與降級錯誤契約。
- 補強報表頁字串輸出安全與欄位契約一致性，確保畫面欄位、查詢結果與下載欄位名稱一致。
- 新增/調整模板整合驗證，確保 Vite 模組載入與 fallback 行為在報表頁完整覆蓋。

## Capabilities

### New Capabilities
- `report-effects-parity`: 定義舊版 Jinja 報表在新 Vite 架構下的效果對齊要求（圖表、篩選、表格、KPI、互動與下載語意）。

### Modified Capabilities
- `full-vite-page-modularization`: 擴展到 WIP 報表頁完整模組化與 fallback 覆蓋。
- `frontend-compute-shift`: 擴大前端運算承載並修復前端計算與呈現邏輯缺陷。
- `field-contract-governance`: 強化欄位名稱與匯出標頭一致性及頁面渲染安全。
- `runtime-resilience-recovery`: 明確要求前端呼叫在降級/壓力情境下遵循退避契約。

## Impact

- Affected code: `frontend/src/`, `frontend/vite.config.js`, `src/mes_dashboard/templates/`, `tests/test_template_integration.py`。
- Affected runtime behavior: 報表頁 JS 載入模式、矩陣/篩選互動、KPI 顯示與下載欄位對齊。
- Affected operations: 單一對外 port 架構不變，仍由 Flask/Gunicorn 提供頁面與 Vite build 輸出資產。
