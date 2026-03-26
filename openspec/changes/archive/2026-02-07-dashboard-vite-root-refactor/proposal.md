## Why

目前可執行程式碼位於 `DashBoard/` 子目錄，與 `DashBoard_vite` 根目錄的 OpenSpec/opsx 工作流分離，導致規格、實作與驗證不在同一專案根。需要以 `DashBoard` 為參考，將重構主體統一到 `DashBoard_vite` 根目錄，並同時導入 Vite 以改善前端可維護性與體驗。

## What Changes

- 在 `DashBoard_vite` 根目錄建立可執行的重構專案骨架，參照既有 `DashBoard` 功能與路由。
- 維持 Flask/Gunicorn 單一對外 port，導入 Vite 作為前端建置工具（build artifact 由 Flask 提供）。
- 導覽由平鋪 tab 重構為功能抽屜（報表類、查詢類、開發工具類），保持既有業務操作路徑。
- 快取策略改為可運作的分層快取（L1 記憶體 + L2 Redis），不再使用 NoOp 做為預設。
- 建立前端顯示欄位與下載欄位的一致性規範，先修正已知不一致案例。

## Capabilities

### New Capabilities
- `root-project-restructure`: 以 `DashBoard` 為參考，將可運行的重構工程落在 `DashBoard_vite` 根目錄。
- `vite-single-port-integration`: Vite 建置結果整合進 Flask static，維持單一 server/port 對外。
- `portal-drawer-navigation`: Portal 導覽改為抽屜分類且維持原頁面邏輯。
- `layered-route-cache`: 路由層快取改為 L1 memory + L2 Redis 的可用實作。
- `field-name-consistency`: 統一畫面欄位、API key 與匯出欄位命名/語義。

### Modified Capabilities
- None.

## Impact

- Affected codebase root: `DashBoard_vite`（新主工程落點）
- Reference baseline: `DashBoard/`（保留作比對與遷移來源）
- Affected systems: Flask app factory, templates, frontend build pipeline, deployment/start scripts, cache layer, export SQL/headers
