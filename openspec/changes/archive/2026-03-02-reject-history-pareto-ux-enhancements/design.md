## Context

Reject History 已改為兩階段查詢：`/api/reject-history/query` 先查 Oracle 並快取 DataFrame，`/api/reject-history/view` 與 `/api/reject-history/export-cached` 在快取資料上做補充篩選。現況存在三個 UX/一致性缺口：

1. `TYPE/WORKFLOW/機台` 維度在 80% 範圍下仍可能過多，不易閱讀。  
2. Pareto 點選目前僅支援單選原因（reason），不支援多選且不支援其他維度。  
3. 匯出需要和畫面篩選完全一致，但目前缺少 Pareto 多選情境的等價參數傳遞與後端套用。

本變更跨前端 Vue（FilterPanel/ParetoSection/App）與後端 Flask+Pandas（routes/cache service），屬跨模組一致性調整。

## Goals / Non-Goals

**Goals:**
- 在 `TYPE/WORKFLOW/機台` 維度提供 Pareto 顯示範圍切換（`全部顯示` / `只顯示 TOP 20`）。
- 將「Pareto 僅顯示累計前 80%」控制移到補充篩選區域，維持預設啟用。
- Pareto 圖表與表格都支援多選，並即時聯動刷新明系列表。
- 匯出 CSV 套用完整篩選上下文（主查詢、補充篩選、互動篩選、Pareto 多選）。
- 保持 UTF-8 BOM 與標準 CSV escaping。

**Non-Goals:**
- 不改動 Oracle SQL schema 與資料來源邏輯。
- 不新增新資料表或 Redis key 結構。
- 不重做 Reject History 整體版面，只做既有模組行為擴充。

## Decisions

### 1) Pareto 多選狀態由 App.vue 集中管理
- Decision: 新增 `selectedParetoValues`（array）與 `paretoDisplayScope`（`all`/`top20`）於 `App.vue`。
- Why: 既有趨勢日期、補充篩選、明細分頁都由 App 協調；將 Pareto 多選納入同一狀態中心可確保 URL、view、export 一致。
- Alternative considered:
  - 在 `ParetoSection.vue` 內部持有選取狀態：會造成匯出與後端參數組裝需要額外同步機制，易出現狀態漂移。

### 2) `TOP 20` 僅在前端呈現層裁切
- Decision: 後端仍回傳完整（或 top80）Pareto items，`TOP 20` 由前端 computed 再切片。
- Why: `TOP 20` 是視覺呈現策略，不是資料語意；放前端可避免增加 API 分支與快取鍵複雜度。
- Alternative considered:
  - API 增加 `display_scope=top20`：可行但會讓同一資料語意被多組 API 參數切分，且對快取命中率不利。

### 3) Pareto 多選篩選在後端 cache service 統一套用
- Decision: `apply_view()` 與 `export_csv_from_cache()` 新增 `pareto_dimension` + `pareto_values` 參數，透過共享 helper 套用到對應欄位。
- Why: 明細畫面與匯出都要使用「同一過濾函式」才能保證 parity。
- Alternative considered:
  - 前端先過濾當頁明細再匯出：無法涵蓋全資料集，且分頁資料可能不完整。

### 4) 80% toggle 位置調整但語意不變
- Decision: checkbox UI 從主工具列移至補充篩選區塊；預設值與 URL 參數（`pareto_scope_all`）維持既有相容。
- Why: 80% 為二階段視圖篩選，移入補充篩選可降低使用者誤解。

## Risks / Trade-offs

- [Risk] 多選維度欄位映射錯誤（特別是 `equipment` 對應欄位）導致篩選失準。  
  → Mitigation: 單元測試覆蓋各維度映射與無效維度 400。  

- [Risk] 前端多種互動（趨勢日期、reason、pareto 多選）同時作用時狀態難追蹤。  
  → Mitigation: `activeFilterChips` 顯示所有活躍條件，並統一經 `refreshView()` + `updateUrlState()`。  

- [Risk] CSV 匯出和列表排序/篩選不一致造成信任問題。  
  → Mitigation: 匯出重用與 view 相同 filter helper，並新增 route/service parity 測試。

## Migration Plan

1. 先落地後端 `apply_view/export_csv_from_cache` 共同 Pareto 多選過濾與參數驗證。  
2. 再調整前端控制項與事件（多選、TOP20、補充篩選區）。  
3. 補上 route/service 單元測試。  
4. 驗證目標：`reject-history` 相關測試通過，手動檢查 CSV 編碼與欄位。

Rollback strategy:
- 若上線後出現篩選偏差，可暫時忽略 `pareto_dimension/pareto_values` 參數（後端回退到舊邏輯），不影響既有查詢主路徑。

## Open Questions

- `TOP 20` 是否僅限定 `TYPE/WORKFLOW/機台`（本次採用是），或未來要擴展到全部維度？  
- 多選 Pareto 與補充篩選中的 `reason` 同時存在時，是否需要 UI 顯示「交集」提示（本次先不新增提示文案）。
