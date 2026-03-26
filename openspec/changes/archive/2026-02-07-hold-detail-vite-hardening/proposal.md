## Why

`hold_detail` 目前仍是大型 inline script，尚未納入 Vite 模組治理，且動態 HTML 字串拼接存在潛在注入風險。為了完成報表頁一致的現代化架構與安全基線，需要將該頁補齊至與其餘主要頁面相同的模組化與防護水位。

## What Changes

- 新增 `hold-detail` Vite entry 並由模板透過 `frontend_asset(...)` 優先載入 module。
- 保留現有 inline script 作為 asset 缺失時 fallback，維持既有操作語意不變。
- 將 `hold_detail` 的動態表格/篩選渲染改為 escape-safe 輸出，避免不受信字串直接注入 DOM。
- 補充模板整合測試，驗證 `hold_detail` 的 module/fallback 路徑。

## Capabilities

### New Capabilities
- None.

### Modified Capabilities
- `full-vite-page-modularization`: 擴展 major page 模組化覆蓋到 hold-detail 報表頁。
- `field-contract-governance`: 將動態渲染安全契約擴展到 hold-detail 報表內容。
- `report-effects-parity`: 明確要求 hold-detail 的篩選、分頁、分佈互動在遷移後維持等效。

## Impact

- Affected code: `frontend/src/`, `frontend/vite.config.js`, `src/mes_dashboard/templates/hold_detail.html`, `tests/test_template_integration.py`。
- APIs/routes: `/hold-detail`, `/api/wip/hold-detail/*`（僅前端調用與渲染方式調整，不更動後端契約）。
- Runtime behavior: 單一 port 與既有 MesApi/retry 行為不變。
