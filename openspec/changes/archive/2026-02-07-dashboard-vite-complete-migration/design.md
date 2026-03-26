## Context

`DashBoard_vite` 已完成第一批根目錄重構，但仍有部分頁面維持大量 inline script、部分計算在後端實作且缺乏前後一致性驗證、欄位命名規則未全面治理。`DashBoard/` 目前仍作為結構與行為參考來源。此變更目標是完成最終遷移：以 `DashBoard_vite` 根目錄作為唯一開發/部署主體，並建立可持續的前端模組化、欄位契約、快取可觀測性與遷移門檻。

## Goals / Non-Goals

**Goals:**
- 完成 root cutover，執行與維護流程完全以 `DashBoard_vite` 為主。
- 將主要頁面前端腳本模組化至 Vite 管理，降低單檔模板複雜度。
- 將可前端化的展示/聚合計算前移，並建立與既有輸出一致性驗證。
- 建立 UI/API/Export 欄位契約與自動檢核機制。
- 強化分層快取的健康指標與退化觀測。
- 制定遷移驗收門檻、灰度與回退方案。

**Non-Goals:**
- 不重寫所有頁面的視覺設計。
- 不更換資料來源（Oracle schema 與核心資料表不變）。
- 不改成前後端雙對外服務架構（維持單一 port）。

## Decisions

1. Canonical root ownership
- Decision: `DashBoard_vite` 為唯一可執行主工程；`DashBoard/` 僅保留為對照基準直到遷移結案。
- Why: 避免規格、程式碼、部署分散在不同根目錄。
- Alternative: 長期雙根並行；放棄，因維運成本與錯誤率高。

2. Page-by-page Vite modularization
- Decision: 以頁面為單位建立 Vite entry，先抽共用 core（API、toast、table/tree、field contract），再遷移頁面。
- Why: 風險可控，便於逐頁回歸驗證。
- Alternative: 一次性 SPA rewrite；放棄，風險高且不符合保持既有邏輯要求。

3. Compute-shift contract with parity checks
- Decision: 後端保留原始資料查詢與必要彙整，前端承接展示層聚合/格式化；每個前移計算需有 parity fixture。
- Why: 提升前端互動效率，同時避免行為偏移。
- Alternative: 全留後端；放棄，無法達成前移目標。

4. Field contract registry
- Decision: 建立欄位契約註冊檔（UI label / API key / export header / semantic type），頁面與匯出共用。
- Why: 消除欄位語義不一致與下載對不上畫面的問題。
- Alternative: 分頁分散維護；放棄，長期不可控。

5. Cache observability first-class
- Decision: 延續 L1 memory + L2 Redis，新增命中率、資料新鮮度、降級狀態指標並在 health/deep-health 可見。
- Why: 快取是效能與穩定核心，需可觀測才能穩定運維。
- Alternative: 僅保留功能快取不加觀測；放棄，故障定位成本高。

## Risks / Trade-offs

- [Risk] 模組化拆分期間，舊 inline 與新 module 並存造成行為差異 → Mitigation: 對每頁保留 feature flag 或 fallback，逐頁切換。
- [Risk] 前移計算造成數值差異（四捨五入、分母定義） → Mitigation: 建立固定測試資料與 snapshot 比對，未通過不得切換。
- [Risk] 欄位契約改名影響下游報表流程 → Mitigation: 提供 alias 過渡期與變更公告。
- [Risk] Redis/Oracle 不可用時測試訊號雜訊高 → Mitigation: 分離 unit/fallback 與 integration pipelines。

## Migration Plan

1. Baseline freeze
- 凍結基線 API payload、頁面主要互動、匯出欄位，產生對照清單。

2. Cutover preparation
- 補齊根目錄執行文件、CI 與腳本，確保不再依賴 `DashBoard/`。

3. Modularization waves
- Wave A: Portal、resource history、job query。
- Wave B: resource status、excel query、tables。
- 每波完成後執行頁面回歸與欄位一致性檢核。

4. Compute-shift waves
- 先移動展示層聚合與圖表資料整理，再評估進一步前移。
- 每項前移需 parity 測試與效能比較。

5. Final cutover and cleanup
- 滿足驗收門檻後將 `DashBoard/` 標記為 archived reference 或移除。
- 完成回退文件與操作手冊更新。

## Open Questions

- `DashBoard/` 在結案後保留多久（短期備援或立即封存）？
- 哪一頁的前移計算業務優先級最高（resource_history vs job_query）？
- 是否要求在 cutover 前補齊端對端自動化下載欄位比對？
