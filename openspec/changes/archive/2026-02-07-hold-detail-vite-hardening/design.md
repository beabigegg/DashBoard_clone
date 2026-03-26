## Context

目前主要報表頁多已採 `frontend_asset(...) + Vite module + inline fallback` 模式，但 `hold_detail` 仍停留在純 inline script。這造成：
- 例外頁面無法受益於共用模組治理與 build pipeline。
- 動態表格字串拼接保留 XSS 風險。
- 長期維護出現「主流程已模組化、單頁特例未遷移」的不一致。

## Goals / Non-Goals

**Goals:**
- 讓 `hold_detail` 與其他報表頁採同一套 Vite 載入模式。
- 保留既有功能語意（篩選、分頁、刷新、導航）與 MesApi 呼叫契約。
- 將高風險動態輸出改為 escape-safe 渲染。
- 加上模板整合測試覆蓋 module/fallback 分支。

**Non-Goals:**
- 不改後端資料模型與查詢邏輯。
- 不重設 UI 視覺樣式與互動流程。
- 不移除 fallback（本次仍保留回退能力）。

## Decisions

### Decision 1: 以「抽取 inline script 到 Vite entry」完成遷移
- 選擇：新增 `frontend/src/hold-detail/main.js`，以既有邏輯為基礎遷移，模板改為 module 優先、fallback 次之。
- 理由：最小風險完成頁面納管，避免一次性重寫行為。

### Decision 2: 保持全域 handler 相容
- 選擇：module 內維持 `window` 介面供既有 `onclick` 使用。
- 理由：降低模板 DOM 大改成本，優先保證 parity。

### Decision 3: 在 module 與 fallback 皆補 escape 防護
- 選擇：對 workcenter/package/lot 資料動態輸出加入 escape/quoted-string 保護。
- 理由：避免 fallback 成為安全漏洞旁路。

## Risks / Trade-offs

- [Risk] 複製遷移過程遺漏函式導致 runtime error → Mitigation: build + template test 覆蓋 module 路徑。
- [Risk] fallback 與 module 雙軌造成維護成本 → Mitigation: 保持語意對齊並在後續階段評估移除 fallback。
- [Risk] escape 導致個別顯示格式變化 → Mitigation: 僅防注入，不改原欄位值與排序/篩選語意。

## Migration Plan

1. 增加 `hold-detail` Vite entry 與 module 檔案。
2. 調整 `hold_detail.html` scripts block 為 module/fallback 雙軌。
3. 補強 module + fallback 的動態輸出 escape。
4. build 與 pytest 驗證，更新 tasks。

## Open Questions

- 是否在下一階段移除 `hold_detail` fallback inline script，以降低雙路徑維運成本。
