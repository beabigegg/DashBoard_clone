## Why

上一輪已完成高風險核心修復，但仍有一批殘餘問題會在高併發、長時間運行與惡意/異常輸入下放大風險（快取發布一致性、鎖競爭、健康檢查負載、輸入邊界與速率治理）。本輪目標是把這些尾端風險收斂到可接受範圍，避免後續運維與效能不穩。

## What Changes

- 強化 WIP 快取發布流程，確保更新失敗時不污染既有讀取路徑。
- 調整 process cache 慢路徑鎖範圍，避免持鎖解析大 JSON。
- 補齊 realtime equipment process cache 的 bounded LRU，與 WIP/Resource 策略一致。
- 為資源路由 NaN 清理加入深度保護（避免深層遞迴風險）。
- 抽取共用布林參數解析，消除重複邏輯。
- 將 filter cache 的 view 名稱改為可配置，移除硬編碼耦合。
- 加入敏感連線字串 log redaction。
- 對 `/health`、`/health/deep` 增加 5 秒內部短快取（測試模式禁用）。
- 對高成本查詢 API 增加輕量速率限制與可調參數。
- 更新 README/README.mdj 與驗證測試。

## Capabilities

### New Capabilities
- `api-safety-hygiene`: API 輸入邊界、共享參數解析、可配置查詢來源、與高成本端點速率治理。

### Modified Capabilities
- `cache-observability-hardening`: 補強快取發布一致性、process cache 鎖範圍與 bounded 策略一致化。
- `runtime-resilience-recovery`: 健康檢查短快取與敏感資訊日誌遮罩的運維安全要求。

## Impact

- Affected code:
  - `src/mes_dashboard/core/cache_updater.py`
  - `src/mes_dashboard/core/cache.py`
  - `src/mes_dashboard/services/realtime_equipment_cache.py`
  - `src/mes_dashboard/routes/resource_routes.py`
  - `src/mes_dashboard/routes/wip_routes.py`
  - `src/mes_dashboard/routes/hold_routes.py`
  - `src/mes_dashboard/services/filter_cache.py`
  - `src/mes_dashboard/core/database.py`
  - `src/mes_dashboard/routes/health_routes.py`
- APIs:
  - `/health`, `/health/deep`
  - `/api/wip/detail/<workcenter>`, `/api/wip/overview/*`
  - `/api/resource/*`（高成本路由）
- Docs/tests:
  - `README.md`, `README.mdj`, `tests/*`
