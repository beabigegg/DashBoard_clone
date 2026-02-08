## Context

本專案上一輪已完成 P0/P1/P2 的主體重構，但 code review 後仍存在幾個殘餘高風險點：
- `LDAP_API_URL` 缺少 scheme/host 防線，屬於可配置 SSRF 風險。
- process-level DataFrame cache 僅用 TTL，缺少容量上限。
- circuit breaker 狀態轉換在持鎖期間寫日誌，存在鎖競爭放大風險。
- 全域 security headers 尚未統一輸出。
- 分頁參數尚有下限驗證缺口。

這些問題橫跨 `app/core/services/routes/tests`，屬於跨模組安全與穩定性修補。

## Goals / Non-Goals

**Goals:**
- 對 LDAP endpoint、HTTP 回應標頭、輸入邊界建立可測試的最低防線。
- 讓 process-level cache 具備有界容量與可預期淘汰行為。
- 降低 circuit breaker 內部鎖競爭風險，避免慢 handler 放大阻塞。
- 維持單一 port、現有 API 契約與前端互動語意不變。

**Non-Goals:**
- 不引入完整 WAF/零信任架構。
- 不重寫既有 cache 架構為外部快取服務。
- 不改動報表功能或頁面流程。

## Decisions

1. **LDAP URL 啟動驗證（fail-fast）**
   - Decision: 在 `auth_service` 啟動階段驗證 `LDAP_API_URL`，限制 `https` 與白名單 host（由 env 設定），不符合即禁用 LDAP 驗證路徑並記錄錯誤。
   - Rationale: 以最低改動封住配置型 SSRF 風險，不影響 local auth 模式。

2. **ProcessLevelCache 有界化**
   - Decision: 在 `ProcessLevelCache` 新增 `max_size` 與 LRU 淘汰（`OrderedDict`），`set` 時淘汰最舊 key。
   - Rationale: 保留 TTL 行為，同時避免高基數 key 長時間堆積。

3. **Circuit breaker 鎖外寫日誌**
   - Decision: `_transition_to` 僅在鎖內更新狀態並組裝日誌訊息，實際 logger 呼叫移到鎖外。
   - Rationale: 降低持鎖區塊執行時間，避免慢 I/O handler 阻塞其他請求路徑。

4. **全域安全標頭統一注入**
   - Decision: 在 `app.after_request` 加入 `CSP`、`X-Frame-Options`、`X-Content-Type-Options`、`Referrer-Policy`，並在 production 加上 `HSTS`。
   - Rationale: 以集中式策略覆蓋所有頁面與 API，降低遺漏機率。

5. **分頁參數上下限一致化**
   - Decision: 對 `page` 與 `page_size` 統一加入 `max(1, min(...))` 邊界處理。
   - Rationale: 防止負值或極端數值造成不必要負載與非預期行為。

## Risks / Trade-offs

- **[Risk] LDAP 白名單設定不完整導致登入中斷** → **Mitigation:** 提供明確錯誤訊息與 local auth fallback 指引。
- **[Risk] Cache 上限過小造成命中率下降** → **Mitigation:** `max_size` 設為可配置，先給保守預設值並觀察 telemetry。
- **[Risk] CSP 過嚴影響既有 inline 腳本** → **Mitigation:** 先採 `default-src 'self'` 與相容策略，必要時以 nonce/白名單微調。
- **[Risk] 行為調整引發測試回歸** → **Mitigation:** 補 unit/integration 測試覆蓋每個修補點。

## Migration Plan

1. 先落地 backend 修補（auth/cache/circuit breaker/app headers/routes）。
2. 補測試（LDAP 驗證、LRU、鎖外日誌、headers、分頁邊界）。
3. 執行既有健康檢查與重點整合測試。
4. 更新 README/README.mdj 的安全與穩定性章節。
5. 若部署後有相容性問題，可暫時透過 env 放寬 LDAP host 白名單與 CSP 細項。

## Open Questions

- LDAP host 白名單在各環境是否需要多個網域（例如內網 + DR site）？
- CSP 是否要立即切換到 nonce-based 嚴格模式，或先維持相容策略？
