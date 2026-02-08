## Context

現有程式碼主體在 `DashBoard/` 子目錄，OpenSpec/opsx 在 `DashBoard_vite` 根目錄，造成需求追蹤、實作與驗證分離。重構目標是以 `DashBoard/` 作為參考來源，將可執行專案落到根目錄，並在維持單一對外服務埠前提下導入 Vite 前端建置與模組化。

## Goals / Non-Goals

**Goals:**
- 在 `DashBoard_vite` 根目錄建立可運行工程，與 OpenSpec artifacts 同層。
- 維持 Flask/Gunicorn 單一對外 port，前端資產由 Flask static 提供。
- 導覽改為抽屜分組，保持既有頁面與 drill-down 操作語意。
- 導入分層快取（L1 memory + L2 Redis）取代 NoOp 預設。
- 建立畫面欄位、API key、下載欄位的一致性規範。

**Non-Goals:**
- 不在第一階段重寫所有頁面 UI。
- 不更動核心商業資料來源（Oracle schema 與主要 SQL 邏輯）。
- 不在第一階段導入多服務或多 port 架構。

## Decisions

1. Root-first migration（根目錄主工程）
- Decision: 以 `DashBoard/` 為參考，將執行入口、`src/`、`scripts/`、前端建置等移到 `DashBoard_vite` 根目錄。
- Rationale: 使 OpenSpec 與可執行程式在同一工作根，避免流程分裂。
- Alternative considered: 繼續在 `DashBoard/` 開發，放棄；因與使用者要求衝突。

2. Single-port Vite integration
- Decision: 使用 Vite build 輸出到 Flask static，僅在開發時可選擇 Vite dev server，不作對外正式服務。
- Rationale: 保持現行部署模型與防火牆策略，降低切換風險。
- Alternative considered: 分離前後端雙服務；放棄以符合單一 port 約束。

3. Layered route cache
- Decision: 路由層快取採用 L1 memory TTL + L2 Redis JSON；Redis 不可用時仍有 L1。
- Rationale: 改善響應速度與穩定性，避免 NoOp 導致的快取失效。
- Alternative considered: Redis-only；放棄以避免 Redis 異常時退化過大。

4. Navigation IA by drawers
- Decision: 將 portal 導覽分為「報表類、查詢類、開發工具類」抽屜，頁面內容維持原路由/iframe lazy load。
- Rationale: 降低使用者認知負擔，同時避免一次性替換頁面內邏輯。
- Alternative considered: 直接改成 SPA router；放棄以降低第一階段風險。

5. Field contract normalization
- Decision: 建立欄位契約字典（UI label / API key / export header），並先修正已知不一致。
- Rationale: 避免匯出與畫面解讀差異造成誤用。
- Alternative considered: 每頁分散維護；放棄因長期不可維護。

## Risks / Trade-offs

- [Risk] 根目錄遷移時檔案基線混亂（舊目錄與新目錄並存） → Mitigation: 明確標註 `DashBoard/` 為 reference，新增 root 驗證與遷移清單。
- [Risk] Redis/Oracle 在本機測試環境不可用導致測試波動 → Mitigation: 分離「單元測試通過」與「環境依賴測試」兩條驗證報告。
- [Risk] Portal 抽屜調整影響既有 E2E selector → Mitigation: 保留原 tab class/data-target，先兼容再逐步更新測試。
- [Risk] 欄位命名調整影響下游檔案流程 → Mitigation: 提供別名過渡期與欄位映射文件。

## Migration Plan

1. 建立根目錄主工程骨架（參照 `DashBoard/`），保留 `DashBoard/` 作為對照來源。
2. 導入 Vite build 流程並接入 `deploy/start` 腳本。
3. 套用 portal 抽屜導覽與快取 backend 重構。
4. 執行欄位一致性第一批修正（job query / resource history）。
5. 補齊根目錄測試與操作文件，確認單一 port 運作。

## Open Questions

- 根目錄最終是否保留 `DashBoard/` 作為長期參考，或在完成驗收後移除？
- 第二階段前端運算前移的優先頁面順序（`resource_history` vs `job_query`）是否有業務優先級？
