## Why

目前已完成第一批根目錄重構，但仍存在「部分頁面與邏輯尚未完整遷移」的階段性狀態。需要建立完整遷移提案，將 `DashBoard_vite` 根目錄收斂為唯一開發與運行主體，並完成前端模組化與欄位契約治理，避免長期雙結構維運風險。

## What Changes

- 完成從參考結構到根目錄主工程的全面切換，消除對 `DashBoard/` 作為執行依賴。
- 以 Vite 完整模組化 Portal 與主要業務頁面前端腳本，逐步移除大型 inline scripts。
- 在不改變既有業務流程前提下，將可前端化的展示/聚合計算由後端移至前端。
- 建立 UI/API/Export 欄位契約機制，對報表與查詢頁進行一致性治理。
- 擴充快取與運維可觀測性，明確 Redis 與記憶體快取的行為、指標與退化策略。
- 建立完整遷移驗收與回退規則，作為 cutover 與後續清理依據。

## Capabilities

### New Capabilities
- `root-cutover-finalization`: 定義並完成根目錄主工程最終切換與遺留結構去依賴。
- `full-vite-page-modularization`: 完成主要頁面腳本的 Vite 模組化與資產輸出治理。
- `frontend-compute-shift`: 將展示層可前端化計算從後端搬移到前端，保持行為一致。
- `field-contract-governance`: 建立並執行欄位契約（UI label / API key / export header）一致性規範。
- `cache-observability-hardening`: 強化分層快取策略與健康指標，明確失效與退化行為。
- `migration-gates-and-rollout`: 定義完整遷移的驗收門檻、灰度與回退流程。

### Modified Capabilities
- None.

## Impact

- Affected code: root `src/`, `frontend/`, `scripts/`, `tests/`, `docs/`。
- Runtime/deploy: Conda + Node(Vite) build pipeline、Flask/Gunicorn 單一對外 port 模式。
- APIs/pages: Portal、resource status、resource history、job query、excel query、tables 等頁面腳本與欄位輸出。
- Ops: Redis 快取、記憶體快取、health/deep health 指標與告警解讀。
