## Why

目前剩餘風險集中在可維護性與記憶體效率：Resource 快取在同一個 process 內維持多種資料表示，部分查詢 SQL 在不同快取服務重複維護，且型別註記與魔術數字仍不一致。這些問題不會立刻造成中斷，但會提高記憶體占用、增加後續修改成本與回歸風險，因此需要在既有功能不變前提下完成收斂。

## What Changes

- 將 Resource derived index 的資料表示改為「輕量索引 + 惰性輸出」，避免在 process 中重複保留完整 records 複本。
- 將 Resource 與 Realtime Equipment 的 Oracle 查詢字串收斂到共用 SQL 常數模組，降低重複定義與異步漂移風險。
- 補齊型別註記一致性（尤其 cache/index/service 邊界）並把高頻魔術數字提升為具名常數或可配置參數。
- 維持現有 API 契約、全表快取策略、單一 port 架構與前端行為不變。

## Capabilities

### New Capabilities
- `resource-cache-representation-normalization`: 以單一權威資料表示與輕量索引替代 process 內多份完整資料複本，並保留既有查詢回傳結構。
- `oracle-query-fragment-governance`: 將跨服務共用的 Oracle 查詢片段抽離為共享常數/模板，確保查詢語意一致。
- `maintainability-type-and-constant-hygiene`: 建立型別註記與具名常數的落地規範，降低魔術數字與註記風格漂移。

### Modified Capabilities
- `cache-observability-hardening`: 補充記憶體放大係數與索引表示調整後的可觀測一致性要求。

## Impact

- 主要影響檔案：
  - `src/mes_dashboard/services/resource_cache.py`
  - `src/mes_dashboard/services/realtime_equipment_cache.py`
  - `src/mes_dashboard/services/resource_service.py`（若需配合索引輸出）
  - `src/mes_dashboard/sql/*` 或新增共享 SQL 常數模組
  - `src/mes_dashboard/config/constants.py`、`src/mes_dashboard/core/utils.py`
  - 對應測試與 README/README.mdj 文檔
- 不新增外部依賴，不變更對外 API 路徑與欄位契約。
