## Context

目前 released 報表頁面的篩選模型混用三種模式：
1. 後端動態 options 互篩（`wip-overview` / `wip-detail`）
2. 前端用已載入 options 做部分收斂（`resource-history`）
3. 查詢驅動或鑽取驅動（`reject-history`、`hold-*` 等）

這種混用在「探索型」報表（使用者要快速找到可分析的有效組合）會造成明顯成本：
- 下拉選單可選但查詢無資料
- 上游條件變更後，下游已選值失效但仍保留
- 使用者對不同頁面的篩選預期不一致

本提案聚焦補強兩個探索型頁面：
- `reject-history`
- `resource-history`

並建立跨報表可重用的篩選策略基線。

## Goals / Non-Goals

**Goals:**
- 定義「探索型 vs 監控/鑽取型」頁面的篩選策略分級與適用準則。
- 讓 `reject-history` 支援草稿條件驅動的 options 互相收斂，減少無效篩選組合。
- 讓 `resource-history` 從部分聯動提升為一致聯動（上游變更時，自動 prune 失效選取值）。
- 統一互篩技術細節：debounce、請求去重/過期回應保護、無效值剔除、apply/clear 語意一致。

**Non-Goals:**
- 不在本次將所有 released 頁面全面改為互相篩選。
- 不改變報表核心計算邏輯（KPI、統計口徑、圖表定義）。
- 不引入新基礎設施（例如 Redis 新部署）作為互篩前置條件。

## Decisions

### Decision 1: 採用「頁面類型分級」而非全站一刀切
- 決策：
  - 探索型頁面：要求完整互篩（options 受目前草稿條件影響，且自動 prune 失效值）。
  - 監控/鑽取型頁面：允許維持輕量篩選 + drilldown，不強制完整互篩。
- 理由：
  - 探索型頁面的主要任務是「找可分析組合」，互篩是核心可用性功能。
  - 監控/鑽取型頁面追求即時性與低操作成本，完整互篩的收益較低。
- 替代方案：
  - 全頁面統一完整互篩：一致性高，但開發與維護成本過高，且對監控頁面價值有限。

### Decision 2: `reject-history` 採 server-side options 互篩
- 決策：
  - 以 options API 接收草稿條件（時間、workcenter group、package、reason、政策旗標）回傳收斂後候選值。
  - 前端在草稿變更時 debounce 觸發 options reload；apply 時再執行主查詢。
- 理由：
  - `reject-history` 篩選受政策旗標影響，僅靠前端靜態 options 無法正確反映後端過濾語意。
- 替代方案：
  - 前端本地收斂：無法覆蓋政策條件與後端口徑，容易與實際查詢結果不一致。

### Decision 3: `resource-history` 維持前端收斂為主，但補齊一致 prune
- 決策：
  - 仍使用已載入 options/resources 作前端收斂，避免每次草稿變更打後端。
  - 補上 family/machine 與上游條件（群組、flags）一致收斂與失效值自動清理。
- 理由：
  - `resource-history` 現有資料結構已適合前端計算選項，性能與實作成本較平衡。
- 替代方案：
  - 改成全 server-side options：一致性高，但請求頻率與後端負載上升，且未必有必要。

### Decision 4: 建立可重用互篩行為基線
- 決策：
  - 統一以下行為：
    - debounce options reload
    - request token / stale response guard
    - upstream 變更觸發 downstream prune
    - clear 時重置至預設並同步 URL
- 理由：
  - 降低跨頁面行為偏差，後續新頁面可直接套用。
- 替代方案：
  - 每頁自行實作：短期快，但長期易分歧與回歸。

## Risks / Trade-offs

- [Risk] `reject-history` options API 參數變多，查詢複雜度上升  
  → Mitigation: 使用現有快取索引與必要欄位投影，限制 options 查詢計算範圍。

- [Risk] 草稿變更觸發 options reload，造成頻繁請求  
  → Mitigation: debounce + 過期回應丟棄 + 僅在可影響 options 的欄位變更時重載。

- [Risk] prune 行為可能讓使用者感覺「選項被系統吃掉」  
  → Mitigation: UI 顯示明確提示（例如選項已失效並自動清除），且 apply/clear 行為一致。

- [Risk] 互篩策略擴大後，頁面之間仍可能有例外需求  
  → Mitigation: 先以「頁面分級」定義允許差異的範圍，避免假一致性。

## Migration Plan

1. 先提交 spec-level 規範（策略基線 + 兩頁行為變更）。
2. `reject-history`：擴充 options API 參數與服務層收斂邏輯，前端接入草稿互篩。
3. `resource-history`：補齊前端收斂與 prune 規則，對齊 apply/query 流程。
4. 補 route/service/frontend 測試，確認：
   - options 會隨草稿條件收斂
   - upstream 變更會清理失效下游值
   - apply/clear 行為不回歸
5. 以 feature flag（若需要）做灰度，確認查詢效能後再全面開啟。

Rollback:
- 後端保留原 options 路徑/參數相容；前端可切回「僅 apply 查詢，不做草稿互篩」模式。

## Open Questions

- `reject-history` 的 reason 下拉是否要改為 multi-select（目前設計維持單選）？
- `resource-history` 是否需要將 family options 也改為完全 server-side 來源以統一模式？
- prune 提示文案是否需要全站共用元件（避免各頁文案不一致）？
