## Context

`DashBoard_vite` 已完成主體搬遷，但報表頁仍處於混合狀態：
- `resource-status`、`resource-history` 等頁面已有 Vite 版本，卻存在實際行為缺陷。
- `wip_overview`、`wip_detail` 仍以 inline script 為主，尚未納入 Vite entry 與共用模組治理。
- 部分頁面仍有直接字串拼接輸出與原生 `fetch` 路徑，無法完整承接既有 `MesApi` 的降級重試契約。

此變更是「遷移後硬化」階段：不改變既有業務操作語意，但將效果對齊、模組化覆蓋與前端複用一起完成。

## Goals / Non-Goals

**Goals:**
- 讓 WIP 報表頁進入 Vite entry 管理，並保留目前 tab/drill-down 與 `onclick` 操作語意。
- 修復已遷移模組中會影響報表可用性的缺陷（初始化、KPI、矩陣選取、API 呼叫路徑）。
- 強化共用路徑（escape、欄位契約、MesApi/backoff）以支撐後續前端運算擴展。
- 用測試明確覆蓋「asset exists -> module」、「asset missing -> fallback」的模板行為。

**Non-Goals:**
- 不改動後端路由設計與單一 port 服務模型。
- 不重寫 UI 視覺風格或更動既有商業邏輯判斷規則。
- 不在本次引入新的大型前端框架（維持 Vanilla + Vite entry 模式）。

## Decisions

### Decision 1: 採用「模板雙軌載入」完成 WIP 遷移
- 選擇：在 `wip_overview.html`、`wip_detail.html` 加入 `frontend_asset()` module 載入，保留既有 inline script 作 fallback。
- 理由：可在不破壞現場可用性的前提下，讓 Vite bundle 成為預設執行路徑，符合先前頁面遷移模式。
- 替代方案：直接刪除 inline script。
  - 未採用原因：回退能力不足，且無法快速比對 parity。

### Decision 2: 模組保持全域 handler 相容層
- 選擇：Vite entry 內對舊有 `onclick` 所需函式維持 `window` 綁定，避免模板同步大改。
- 理由：降低一次性改動範圍，先確保行為完全對齊，再逐步收斂事件綁定方式。
- 替代方案：全面改為 addEventListener 並移除 inline `onclick`。
  - 未採用原因：本次目標是 parity hardening，不是互動模型重寫。

### Decision 3: 前端 API 路徑統一走 MesApi
- 選擇：JSON API 優先走 `MesApi.get/post`（或 core api bridge），僅 blob/download 等必要場景保留原生 fetch。
- 理由：沿用既有降級錯誤碼與 retry/backoff 策略，避免 pool exhausted 時前端重試失控。
- 替代方案：維持頁面各自 `fetch`。
  - 未採用原因：會破壞 resilience contract，一致性不足。

### Decision 4: 字串輸出與欄位命名同步納入治理
- 選擇：針對動態 HTML 內容補 escape，並對照 field contract 驗證表格欄位與下載標頭語意一致。
- 理由：遷移期間常見 XSS/欄位漂移問題，必須和模組化同時收斂。

## Risks / Trade-offs

- [Risk] 大型 inline script 搬入 module 時可能出現作用域差異 → Mitigation: 先保留 fallback，並針對 `window` handler 做顯式綁定。
- [Risk] 模組與 fallback 並存造成測試分支增加 → Mitigation: 以 template integration 測試固定兩條路徑行為。
- [Risk] escape 補強可能改變少數欄位原始顯示格式 → Mitigation: 僅針對 HTML 注入風險欄位處理，保留 NULL/日期等既有顯示語意。
- [Risk] 前端改走 MesApi 使錯誤提示型態改變 → Mitigation: 保持原錯誤訊息文案，僅替換底層請求路徑。

## Migration Plan

1. 先完成 OpenSpec task 分解與可執行順序。
2. 新增 WIP Vite entries，更新 vite config，模板加上 module/fallback 雙軌。
3. 修復 `resource-history`、`resource-status` 關鍵缺陷並補安全性修正。
4. Build + pytest 驗證，更新 task 勾選。
5. 交付變更摘要與剩餘風險，供後續 archive。

## Open Questions

- 是否需要在下一階段移除 WIP fallback inline script（目前先保留作為回退機制）。
- 是否要擴充前端單元測試（Vitest）覆蓋更多 DOM 互動，而不只依賴後端模板整合測試。
