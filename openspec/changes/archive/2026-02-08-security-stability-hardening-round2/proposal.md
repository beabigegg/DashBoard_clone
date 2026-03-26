## Why

上一輪已完成核心穩定性重構，但仍有數個高優先風險（LDAP URL 驗證、無界快取成長、circuit breaker 持鎖寫日誌、安全標頭缺口、分頁下限驗證）未收斂。這些問題會在長時運行與惡意輸入情境下累積可用性與安全風險，需在同一輪中補齊。

## What Changes

- 新增 LDAP API base URL 啟動驗證（限定 `https` 與白名單主機），避免可控 SSRF 目標。
- 對 process-level cache 加入 `max_size` 與 LRU 淘汰，避免高基數 key 造成無界記憶體成長。
- 調整 circuit breaker 狀態轉換流程，避免在持鎖期間寫日誌。
- 新增全域 security headers（CSP、X-Frame-Options、X-Content-Type-Options、Referrer-Policy、HSTS）。
- 補齊分頁參數下限驗證，避免負值與不合理 page size 進入查詢流程。
- 為上述修補新增對應測試與文件更新，並維持單一 port 與既有前端操作語意不變。

## Capabilities

### New Capabilities
- `security-surface-hardening`: 規範剩餘安全面向（SSRF 防護、security headers、輸入邊界驗證）的最低防線。

### Modified Capabilities
- `cache-observability-hardening`: 擴充快取治理需求，納入 process-level cache 有界容量與淘汰策略。
- `runtime-resilience-recovery`: 補充 circuit breaker 鎖競爭風險修補與安全標頭對運維診斷回應的相容性要求。

## Impact

- Affected code:
  - `src/mes_dashboard/services/auth_service.py`
  - `src/mes_dashboard/core/cache.py`
  - `src/mes_dashboard/services/resource_cache.py`
  - `src/mes_dashboard/core/circuit_breaker.py`
  - `src/mes_dashboard/app.py`
  - `src/mes_dashboard/routes/wip_routes.py`
  - `tests/`
  - `README.md`, `README.mdj`
- APIs:
  - `/health`, `/health/deep`
  - `/api/wip/detail/<workcenter>`
  - `/admin/login`（間接受影響：LDAP base 驗證）
- Operational behavior:
  - 保持單一 port 與既有報表 UI 流程。
  - 強化安全與穩定性防線，不改變既有功能語意。
