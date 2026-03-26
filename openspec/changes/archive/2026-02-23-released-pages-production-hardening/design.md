## Context

Released 頁面已直接使用於生產，且現行部署為單層對外服務（無反向代理）。現況存在多個交叉風險：
- JSON 解析錯誤可能透過全域 exception handler 回落為 500。
- 部分高成本查詢端點缺乏批量輸入與查詢筆數上限。
- rate-limit client key 可能受 `X-Forwarded-For` spoofing 影響。
- 設定載入在缺漏時存在偏寬鬆預設（含 API 可見性、環境模式）。
- 記錄連線 URL 時可能暴露敏感資訊。
- 前端仍有 inline handler 字串插值路徑。

本變更屬跨模組 hardening（routes/core/config/frontend/tests），且要求在不破壞 Released 正常流程下補齊安全與穩定性基線。

## Goals / Non-Goals

**Goals:**
- 將 Released 高風險端點的輸入錯誤語義固定為可預期 4xx。
- 對 batch / detail 查詢導入可設定的硬上限與拒絕策略。
- 在無 proxy 預設下建立正確的 rate-limit 信任邊界。
- 將生產安全設定調整為 fail-safe 預設並加入啟動檢查。
- 移除已知前端 inline 插值風險點並補強測試，確保無回歸。

**Non-Goals:**
- 不重寫 Released 頁面的商業邏輯或資料模型。
- 不改動 Oracle schema 或新增外部服務。
- 不一次性移除全站所有 legacy inline script（以風險最高路徑優先）。

## Decisions

### Decision 1: 建立一致的 JSON 輸入驗證邊界，將解析失敗明確轉為 4xx
- 選擇：在 Released 相關 JSON routes 採一致的 request parsing helper（含 content-type 與 malformed JSON 驗證），回傳 400/415；僅真正未預期例外才走 500。
- 理由：修正「客戶端錯誤被誤判為服務端錯誤」並提升可觀測性。
- 替代方案：維持各 route 自行 `get_json()` + 全域 handler。
  - 未採用原因：行為不一致且易再次回歸 500。

### Decision 2: 以設定驅動的輸入預算（input budget）治理高成本端點
- 選擇：新增集中化上限設定（例如 `QUERY_TOOL_MAX_CONTAINER_IDS`、`RESOURCE_DETAIL_MAX_LIMIT`、`MAX_JSON_BODY_BYTES`），route 先驗證再呼叫 service。
- 理由：避免 hardcode 分散、便於環境調優與壓測。
- 替代方案：在 service 層被動截斷或依 DB timeout 自然保護。
  - 未採用原因：無法在入口即時拒絕，仍浪費應用資源。

### Decision 3: 以「預設不信任 proxy headers」實作 rate-limit identity
- 選擇：新增 `TRUST_PROXY_HEADERS=false` 預設；只有顯式開啟且來源符合 trusted proxy 條件時才使用 `X-Forwarded-For`。
- 理由：符合當前無反向代理部署現況，避免 IP spoofing 使限流失效。
- 替代方案：永遠信任 XFF。
  - 未採用原因：對外直連部署下可被任意偽造。

### Decision 4: 生產安全設定 fail-safe 與敏感資訊遮罩
- 選擇：`api_public` 缺值或配置錯誤時預設 false；`SECRET_KEY` 等關鍵安全變數缺失時拒絕啟動或進入明確受限模式；所有 URL 型密鑰資訊在 log 遮罩。
- 理由：把「配置失誤」從安全事件轉為可診斷的啟動錯誤。
- 替代方案：保留寬鬆 fallback（例如預設公開 API）。
  - 未採用原因：與生產最小暴露原則衝突。

### Decision 5: 前端高風險 inline handler 先行替換為安全事件綁定
- 選擇：針對 Released 且已觀察到風險的 job-query 動作欄位，改為 data attribute + addEventListener；避免 raw 字串 `onclick` 插值。
- 理由：以最小變更降低 XSS/斷裂風險且不影響 UX。
- 替代方案：一次性重構所有頁面事件綁定。
  - 未採用原因：變更面過大，不利快速風險收斂。

### Decision 6: 以「負向測試 + 既有契約測試」雙軌防回歸
- 選擇：新增 hardening 專屬負向測試（invalid JSON、超量輸入、限流來源、secret redaction）並保留既有 released route 正向契約測試，兩者皆納入 CI gate。
- 理由：確保防護生效且既有功能不被破壞。
- 替代方案：僅補單元測試或手動驗證。
  - 未採用原因：無法長期防止行為漂移。

## Risks / Trade-offs

- [Risk] 新增 4xx 驗證可能影響少量既有錯誤處理流程 → Mitigation: 僅對 JSON-only endpoint 啟用，並以契約測試固定成功路徑。
- [Risk] 輸入上限過低可能影響查詢體驗 → Mitigation: 上限參數化並透過壓測/實際流量校準。
- [Risk] fail-safe 設定可能在配置不完整時阻擋啟動 → Mitigation: 發布前檢查清單與啟動時清楚錯誤訊息。
- [Risk] 前端事件綁定改動造成局部互動差異 → Mitigation: 補 UI 行為測試與手動 smoke 驗證。

## Migration Plan

1. 新增設定鍵與預設值（輸入上限、proxy trust、安全啟動檢查），保留清楚註解與環境文件。
2. 先改 route 層 JSON 驗證與批量上限檢查，再補 service 防線（雙層保護）。
3. 更新 rate-limit client identity resolver，預設走 `remote_addr`。
4. 加入 Redis URL log redaction 與 page registry fail-safe 預設。
5. 調整 job-query 前端事件綁定，移除高風險 inline 插值。
6. 補齊測試：負向 API、限流信任邊界、設定 fail-safe、log redaction、既有 released route 契約。
7. CI 全綠後部署；若出現非預期拒絕，僅允許透過設定值調整上限，不回退安全語義。

Rollback Strategy:
- 若發生突發相容性問題，優先調整上限配置與 trusted proxy 配置；
- 嚴禁回退到「信任任意 XFF」或「invalid JSON 回 500」行為；
- 必要時暫時放寬單一端點上限，但保留防護機制本身。

## Open Questions

- `container_ids` 與 `resource detail limit` 的正式預設值是否以現網 P95 請求分佈定版（例如 200 / 500）？
- trusted proxy 是否需要 CIDR allowlist（而非單純 bool）以支援未來拓樸演進？
