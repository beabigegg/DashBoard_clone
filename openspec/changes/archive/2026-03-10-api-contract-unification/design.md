## Context

`api_development_contract.md` 已定義目標 API 契約，但現況存在顯著落差：
- 後端 route 層仍大量以手動 `jsonify` 回傳（`src/mes_dashboard/routes` 約 405 次，`src/mes_dashboard/app.py` 約 7 次）。
- `core/response.py` 已具備標準 helper 與錯誤碼常數，但 route 實際 `success_response()` 使用率為 0。
- 前端同時存在兩種錯誤格式相依：
  - 新格式：`error.code / error.message`
  - 舊格式：`error` 字串（含 `cache_expired`、`cache_miss` 等流程控制訊號）
- `/health*`、CSV/NDJSON 串流與下載端點、`/admin/api/*` 等有既有消費者與監控契約，不適合以一次性 envelope 化強推。

此變更屬於跨模組治理型遷移：同時影響 Flask routes、前端 API bridge、測試基線與運維監控讀取。

## Goals / Non-Goals

**Goals:**
- 定義可執行且可驗收的 API 契約遷移架構，將最終狀態對齊 `api_development_contract.md`。
- 建立 endpoint 分類與例外邊界（標準 JSON API、health API、串流/下載 API、legacy 過渡 API）。
- 先完成高優先路由（`wip_routes.py`）契約化，並提供可擴展到其餘路由的標準作法。
- 在遷移期維持前端可運行，逐步收斂 `error` 字串依賴到 `error.code/message`。
- 將遷移進度與違規回歸納入檢查機制（清單、測試、CI gate）。

**Non-Goals:**
- 不在此變更中一次改寫所有路由檔。
- 不在此變更中變更健康檢查 payload 的語義結構（例如將 `/health` 外包成 `data`）。
- 不在此變更中移除 `/admin/api/*` 命名空間；僅先建立治理規則與過渡策略。
- 不在此變更中改動業務 SQL 或資料模型。

## Decisions

### 1. 採用「分層分類 + 分波遷移」，不做一次性全量替換
- 分類：
  1) 標準 JSON API（目標全數 envelope 化）
  2) Health API（保留既有 top-level payload）
  3) 串流/下載 API（成功回應維持檔案/串流，錯誤回應標準化）
  4) Legacy bridge API（`app.py` 內歷史端點與 `/admin/api/*`）
- 原因：降低回歸風險、可逐步驗證、便於前端同步切換。
- 替代方案：一次全量替換；否決原因是前端與測試依賴面過大，風險不可控。

### 2. 先固化「錯誤契約」，再逐步固化「成功契約」
- 第一優先：所有遷移中的 JSON API 錯誤回應收斂到 `error.code/error.message`。
- 第二優先：成功回應統一為 `success/data/meta`，逐步移除裸 payload。
- 原因：前端重試、降級、流程控制主要依賴錯誤路徑，先穩定錯誤面可最大化收益。
- 替代方案：先改成功回應；否決原因是錯誤路徑仍分裂會持續造成 UI/測試不確定性。

### 3. Health endpoints 定義為契約例外且需「穩定輸出」
- `/health`、`/health/deep`、`/health/frontend-shell` 維持現有 top-level 結構，避免破壞 shell 健康元件與運維腳本。
- 例外規則寫入 spec，避免未來「統一契約」行動誤改。
- 替代方案：完全 envelope 化；否決原因是既有消費者廣泛，且收益低於風險。

### 4. 建立遷移相容層以承接舊式 `error` 字串判斷
- 前端 API bridge 以 `error.code/error.message` 為主，並在過渡期相容讀取舊 `error` 字串。
- 將 `cache_expired/cache_miss` 從字串比較逐步改為明確 code（例如 `CACHE_EXPIRED`, `CACHE_MISS`）。
- 替代方案：立即移除所有字串判斷；否決原因是需同時改大量前端頁面與測試，交付風險過高。

### 5. 以路由清單與 CI gate 管控遷移品質
- 建立 endpoint 契約分類清單與重構進度清單。
- 加入 guardrail：禁止新增手動 `jsonify`（例外端點除外），並防止 legacy `jsonify` 數量回升。
- 替代方案：只靠 code review；否決原因是跨團隊與長週期遷移容易產生漏網與回歸。

## Risks / Trade-offs

- [Risk] 遷移中同時存在雙格式，增加短期複雜度  
  → Mitigation: 制定 endpoint 分類清單、每波明確驗收條件與下線條件。

- [Risk] 前端仍有 `error` 字串流程控制（`cache_expired/cache_miss`）  
  → Mitigation: 先維持相容；逐頁改為 `error.code` 後再移除字串分支。

- [Risk] health payload 誤改會影響監控/值班判讀  
  → Mitigation: 將 health 視為契約例外並補測試鎖定輸出 shape。

- [Trade-off] `/admin/api/*` 暫不立即改名為 `/api/*`  
  → Mitigation: 先文件化為過渡命名空間，後續另立變更進行 URI 正規化。

- [Trade-off] 短期內無法立即達成「零 `jsonify`」  
  → Mitigation: 設分波目標與趨勢 gate，先追求持續下降與不可回升。

## Migration Plan

1. Phase A: 契約基線與例外清單
- 建立 endpoint 分類（standard/health/streaming/legacy）與責任邊界。
- 補齊 `core/response.py` helper 與錯誤碼（含 cache 類 code）。

2. Phase B: 高優先路由先行（`wip_routes.py`）
- 全面改為 helper 回應。
- 同步更新對應 route tests 與前端 error 讀取。

3. Phase C: 高流量/高耦合路由波次遷移
- 建議順序：`resource_routes.py` → `dashboard_routes.py` → `hold_*`/`reject_history`/`yield_alert`。
- 每波皆需完成：路由 + 前端消費端 + 測試三件套。

4. Phase D: Legacy bridge 與命名治理
- `app.py` 內 API 端點納入 helper 與契約檢查。
- `/admin/api/*` 是否轉向 `/api/*` 於後續 change 執行。

Rollback Strategy:
- 每波以檔案群組為最小回滾單位。
- 若前端出現錯誤語義不相容，先回滾該波 route 與對應前端 parsing 變更。

## Open Questions

- `/admin/api/*` 的最終命名策略要採「保留 + alias」還是「完整搬遷 + 301/compat window」？
- `cache_expired/cache_miss` 是否要提升為全域標準錯誤碼並套用於各 dataset-cache 模組？
- 是否要新增自動化契約測試工具，直接掃描所有 JSON route 的 envelope 與錯誤碼一致性？
