## Context

`DashBoard_vite` 已完成單一 port 的 Flask + Vite 架構整併，並具備降級回應、circuit breaker、watchdog 熱重啟與多層快取。
目前主要缺口不是功能不存在，而是「運維可操作性」與「前端治理粒度」：

1. health/admin 雖有狀態，但缺少門檻與建議動作，值班時仍需人工判讀。
2. watchdog 僅保留最後一次重啟紀錄，無法直接判斷短時間 churn。
3. WIP overview/detail 仍有 autocomplete/filter 搜尋邏輯重複，後續擴展成本高。
4. README 需要明確反映最新架構契約與改善策略，避免文件落後於實作。

## Goals / Non-Goals

**Goals:**
- 提供可操作的韌性診斷輸出（thresholds、churn、recovery recommendation）。
- 保持既有單 port 與手動重啟控制模型，不引入高風險自動重啟風暴。
- 抽離 WIP 頁面共用 autocomplete/filter 查詢邏輯到 Vite core，降低重複。
- 新增對應測試與文件更新，讓 gate 與 README 可驗證。

**Non-Goals:**
- 不做整站 SPA rewrite。
- 不改動既有 drill-down 路徑與使用者操作語意。
- 不預設啟用「條件達成即自動重啟 worker」的強制策略。

## Decisions

1. 韌性診斷採「可觀測 + 建議」而非預設自動重啟
- Decision: 在 `/health`、`/health/deep`、`/admin/api/system-status`、`/admin/api/worker/status` 增加 thresholds/churn/recommendation。
- Rationale: 目前已具備 degraded response + backoff + admin restart；先提升判讀與操作性，避免未設防的自動重啟造成抖動。
- Alternative considered: 直接在 pool exhausted 時自動重啟 worker；未採用，因 root cause 多為慢查詢/瞬時壅塞，重啟治標不治本且有風暴風險。

2. watchdog state 擴充最近重啟歷史
- Decision: 在 state 檔保留 bounded restart history 並計算 churn summary。
- Rationale: 提供運維端可觀測的重啟密度訊號，支援告警與 runbook 決策。
- Alternative considered: 僅依日誌分析；未採用，因 API 需要機器可讀狀態。

3. WIP autocomplete/filter 抽共用核心模組
- Decision: 新增 `frontend/src/core/autocomplete.js`，由 `wip-overview` / `wip-detail` 共用。
- Rationale: 保留既有 API 與頁面互動語意，同時降低重複與 bug 修補成本。
- Alternative considered: 全量頁面元件化框架重寫；未採用，因超出本次風險與範圍。

4. README 架構契約同步
- Decision: 更新 README（並提供 `README.mdj` 鏡像）記錄新的韌性診斷與前端共用模組策略。
- Rationale: 交付後文件應可直接支援運維與交接。

## Risks / Trade-offs

- [Risk] 韌性輸出欄位增加可能影響依賴固定 schema 的外部腳本
  - Mitigation: 採向後相容擴充，不移除既有欄位。

- [Risk] 共用 autocomplete 模組抽離後可能引入搜尋參數差異
  - Mitigation: 保持原有欄位映射與 cross-filter 規則，並補單元測試覆蓋。

- [Risk] restart history 持久化不當可能造成 state 膨脹
  - Mitigation: 使用 bounded history（固定上限）與窗口彙總。

## Migration Plan

1. 實作 resilience diagnostics（thresholds/churn/recommendation）與 watchdog state 擴充。
2. 更新 health/admin API 輸出並補測試。
3. 抽離前端 autocomplete 共用模組，更新 WIP 頁面引用並執行 Vite build。
4. 更新 README/README.mdj 與 runbook 對應段落。
5. 執行 focused pytest + frontend build 驗證，確認單 port 契約不變。

## Open Questions

- 是否在下一階段將 recommendation 與告警 webhook（Slack/Teams）直接整合？
- 是否要把 restart churn 門檻與 UI 告警顏色標準化到 admin/performance 頁？
