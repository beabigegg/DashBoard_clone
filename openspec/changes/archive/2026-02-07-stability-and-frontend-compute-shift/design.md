## Context

目前根目錄 `DashBoard_vite` 已完成單一埠 Vite 整合與主要頁面模組化，但運行層仍有三類風險：
1. 韌性參數未完全生效（例如 DB pool 參數在設定層存在、engine 層未完全採用）。
2. 故障語意未完全標準化（pool 耗盡/熔斷開啟/降級回應仍有泛化 500）。
3. 效能優化尚未形成一致策略（快取資料結構與全量 merge 路徑可再降低 CPU 與記憶體負載）。

本設計在不改變業務邏輯與頁面流程前提下，推進 P0/P1/P2：
- P0：穩定性與退避
- P1：查詢效率與資料結構
- P2：運維一致性與自癒

約束條件：
- `resource`（設備主檔）與 `wip`（即時狀態）維持全表快取，因資料規模可接受且可換取查詢一致性與延遲穩定。
- Vite 架構持續以「前端可複用元件 + 前端運算前移」為核心方向。

## Goals / Non-Goals

**Goals:**
- 讓 DB pool / timeout / circuit breaker 形成可配置且可驗證的穩定性基線。
- 在 pool 耗盡與服務降級時，提供可辨識錯誤碼、HTTP 狀態與前端退避策略。
- 保留全表快取前提下，優化快取資料形狀與索引路徑，降低每次請求全量合併成本。
- 對齊 conda + systemd + watchdog 運行模型，讓 worker 自癒與重啟流程可操作、可觀測。
- 持續擴大前端運算前移範圍，並以 parity 驗證保證結果一致。

**Non-Goals:**
- 不改變既有頁面資訊架構、分頁/鑽取邏輯與核心業務規則。
- 不將 `resource/wip` 改為分片快取或拆分多來源讀取。
- 不引入多埠部署或拆分為前後端不同網域。
- 不在本次變更中重寫所有歷史 SQL 或全面替換資料來源。

## Decisions

### Decision 1: 以「配置即行為」收斂 DB 連線與保護策略（P0）
- 決策：`database.py` 的 engine 建立必須直接採用 settings/.env 的 pool 與 timeout 參數，並在 `/health/deep` 輸出實際生效值。
- 原因：目前存在設定值與實際 engine 參數可能分離，導致調參無效。
- 替代方案：
- 保留硬編碼參數，僅調整 `.env.example`（拒絕，無法保證生效）。
- 完全改為每環境不同程式碼分支（拒絕，維運成本高）。

### Decision 2: 標準化「退避可判讀」錯誤語意（P0）
- 決策：新增/明確化 pool exhausted、circuit open、service degraded 的錯誤碼與 HTTP 映射，並在前端 `MesApi` 依狀態碼與錯誤碼進行退避。
- 原因：泛化 500 導致前端無法做差異化重試與提示。
- 替代方案：
- 維持所有 5xx 同一重試邏輯（拒絕，會加劇擁塞）。
- 僅靠文字訊息判斷（拒絕，不穩定且難國際化）。

### Decision 3: 在「全表快取不變」前提下做索引化與增量化（P1）
- 決策：保留 `resource/wip` 全表快取資料來源，但額外建立 process/redis 層索引（如 RESOURCEID → record index）與預聚合中間結果，減少每請求全量 merge。
- 原因：資料量雖不大，但高併發下重複全量轉換與合併會累積 CPU 成本。
- 替代方案：
- 改為分片快取（拒絕，破壞已確認的資料一致性策略）。
- 完全回 Oracle 即時計算（拒絕，增加 DB 壓力與延遲波動）。

### Decision 4: 前端運算前移採「可驗證前移」策略（P1）
- 決策：優先前移展示層聚合/比率/圖表資料整理，並為每個前移計算建立 parity fixture 與容差規則。
- 原因：符合 Vite 架構目的，減輕後端負擔，同時避免靜默偏差。
- 替代方案：
- 一次性大量前移（拒絕，驗證風險高）。
- 完全不前移（拒絕，無法達成改造目標）。

### Decision 5: 運維流程統一以 conda + systemd + watchdog（P2）
- 決策：部署與監控路徑統一到 conda 環境；systemd 服務模板、啟停腳本、watchdog PID/flag 路徑統一；加入自癒與告警門檻。
- 原因：避免 `venv`/`conda` 混用造成重啟失效或定位困難。
- 替代方案：
- 保持雙系統共存（拒絕，長期不一致風險高）。

## Risks / Trade-offs

- [Risk] 調整錯誤碼與狀態碼可能影響既有前端假設 → Mitigation：先以向後相容 envelope 保留既有 `success/error` 結構，再新增標準化 code/meta 欄位。
- [Risk] 啟用 circuit breaker 後短時間內可能增加 503 可見度 → Mitigation：設定合理門檻與 recovery timeout，並提供管理頁可觀測狀態與手動恢復流程。
- [Risk] 新索引/預聚合增加記憶體占用 → Mitigation：設 TTL、大小監控與健康檢查輸出，必要時可透過配置關閉特定索引層。
- [Risk] 前端運算前移可能出現精度差異 → Mitigation：定義 rounding/tolerance 並在 CI gate 執行 parity 測試。
- [Risk] systemd 與腳本改動可能影響部署流程 → Mitigation：提供 rollout/rollback 演練步驟與 smoke check。

## Migration Plan

1. P0 先行（穩定性）
- 讓 DB pool/call timeout/circuit breaker 參數化且生效。
- 新增 pool exhausted 與 degraded 錯誤語意；前端 `MesApi` 加入對應退避策略。
- 補充 health/deep 與 admin status 的可觀測欄位。

2. P1 續行（效率）
- 保留 `resource/wip` 全表快取資料源。
- 加入索引化/預聚合路徑與增量更新鉤子，降低全量 merge 次數。
- 擴充前端 compute-shift，補 parity fixtures。

3. P2 收斂（運維）
- 統一 conda + systemd + watchdog 服務定義與文件。
- 設定 worker 自癒與告警門檻（重啟頻率、pool 飽和、降級持續時間）。
- 完成壓測與重啟演練 gate 後放行。

4. Rollback
- 任一 gate 失敗即回退到前一穩定版本（腳本 + artifacts + 服務模板）。
- 保留向後相容錯誤回應欄位以降低回退期間前端風險。

## Open Questions

- pool exhausted 的最終 HTTP 語意是否固定為 `503`（含 `Retry-After`）或在部分查詢端點使用 `429`？
- 告警通道是否先落地在 log + health gate，或直接接既有監控平台（若有）？
- 前端計算容差的全域預設值是否統一（如 1e-6 / 小數 1 位），或按指標分類？
