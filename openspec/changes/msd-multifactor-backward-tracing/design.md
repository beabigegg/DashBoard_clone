## Context

「製程不良追溯分析」是 TMTT 測試站不良的回溯歸因工具。目前架構為三階段 staged pipeline（seed-resolve → lineage → events），反向追溯只取 `upstream_history` domain 做機台歸因。

已有的基礎設施：
- **EventFetcher** 已支援 `materials` domain（查 `LOTMATERIALSHISTORY`），可直接複用
- **LineageEngine** 已能追溯 split chain 到 root ancestor，`child_to_parent` map 可直接求 root
- 前端使用 **ECharts** (vue-echarts) 渲染柏拉圖，組件化完善
- 歸因邏輯 `_attribute_defects()` 是通用 pattern：`factor_value → detection_lots mapping → rate calculation`

## Goals / Non-Goals

**Goals:**
- 在反向追溯中新增原物料、源頭晶片兩個歸因維度，與現有機台歸因並列
- 提升柏拉圖的分析能力（排序切換、80% 標記線、tooltip 強化）
- 讓使用者理解歸因計算方式（分析摘要面板）
- 明細表嫌疑因子命中呈現，與柏拉圖 Top N 連動
- 嫌疑機台的維修上下文面板
- 報廢歷史查詢頁面承接產品分布分析（PACKAGE / TYPE / WORKFLOW）

**Non-Goals:**
- 正向追溯改版（後續獨立處理）
- 維修事件作為獨立歸因維度（時間交叉模型複雜，本次僅作為嫌疑機台的上下文資訊）
- Cross-filter 聯動（點圖表 bar 聯動篩選所有圖表 — 本次不做，僅做嫌疑命中）
- 站點層級歸因柏拉圖（產品每站都經過，無鑑別力）

## Decisions

### D1: 原物料歸因邏輯 — 複用 `_attribute_defects` pattern

**選擇**：新增 `_attribute_materials()` 函數，邏輯與 `_attribute_defects()` 完全對稱，只是 key 從 `(workcenter_group, equipment_name, equipment_id)` 換成 `(material_part_name, material_lot_name)`。

**替代方案**：泛化為通用 `_attribute_by_factor(records, key_fn)` 函數。
**理由**：各維度的 record 結構不同（upstream_history 有 station/equipment，materials 有 part/lot），強行泛化需要額外 adapter 層。先用對稱複製，後續若新增更多維度再考慮抽象。

### D2: 原物料資料取得 — EventFetcher materials domain

**選擇**：在 staged trace events 階段新增請求 `materials` domain。前端的 `useTraceProgress.js` 在 backward 模式時改為 `domains: ['upstream_history', 'materials']`。

**替代方案**：另開一個獨立 API 查原物料。
**理由**：EventFetcher 已有完善的 materials domain（batch、cache、rate limit），staged trace pipeline 已能處理多 domain 並行查詢，無需重複建設。

### D3: 源頭晶片歸因 — 從 lineage ancestors 提取 root

**選擇**：在 lineage stage 的 response 中新增 `roots` 欄位（`{seed_cid: root_container_name}`），不需要額外 SQL 查詢。LineageEngine 已有 `child_to_parent` map，遍歷到無 parent 的節點即為 root。後端 `_attribute_wafer_roots()` 以 `root_container_name` 為 key 做歸因。

**替代方案**：用 SQL CONNECT BY 直接查 root。
**理由**：lineage stage 已經完整追溯了 split chain，root 資訊是副產品，不需要額外 DB roundtrip。

### D4: 柏拉圖排列 — 替換 PACKAGE/TYPE/WORKFLOW

**選擇**：6 張柏拉圖改為：

| 位置 | 原本 | 改為 |
|------|------|------|
| 左上 | 依上游機台歸因 | 依上游機台歸因（保留） |
| 右上 | 依不良原因 | 依原物料歸因（新） |
| 左中 | 依偵測機台 | 依源頭晶片歸因（新） |
| 右中 | 依 WORKFLOW | 依不良原因（保留） |
| 左下 | 依 PACKAGE | 依偵測機台（保留） |
| 右下 | 依 TYPE | 移除 |

改為 5 張（2-2-1 排列），最後一行只有偵測機台。或視空間調整為 3-2 或 2-2-2。

**理由**：PACKAGE / TYPE / WORKFLOW 是「不良分布在哪些產品上」的分析，屬於報廢歷史查詢的範疇。製程不良追溯的核心問題是「不良來自哪個上游因子」。

### D5: 明細表結構化上游資料

**選擇**：後端 `_build_detail_table` 的 `UPSTREAM_MACHINES` 欄位改為回傳 list of `{station, machine}` 對象。同時新增 `UPSTREAM_MATERIALS` (list of `{part, lot}`) 和 `UPSTREAM_WAFER_ROOT` (string) 欄位。CSV export 時 flatten 回逗號字串。

前端明細表不顯示全部上游機台，改為只顯示「嫌疑因子命中」：根據當前柏拉圖（含 inline filter）的 Top N 嫌疑名單，與該 LOT 的上游因子做交叉比對。

### D6: 嫌疑機台上下文面板 — Popover 或 Side Drawer

**選擇**：使用 Popover（點擊柏拉圖 bar 時彈出），內容包含：
- 歸因數據：不良率、LOT 數、投入/報廢
- 設備資訊：站點、機型 (RESOURCEFAMILYNAME)
- 近期維修：呼叫 `GET /api/query-tool/lot-associations?type=jobs&container_id=<equipment_id>` 取近期 JOB 紀錄（需要以 equipment_id 查詢的 endpoint，可能需要新增或複用 equipment-period jobs）

**替代方案**：Side drawer 或 modal。
**理由**：Popover 輕量、不離開當前分析上下文。維修資料只需 3-5 筆近期紀錄，不需要完整的 JOB 列表。

### D7: 報廢歷史查詢頁面新增 Pareto 維度

**選擇**：在現有 ParetoSection.vue 新增維度下拉選擇器。後端 `reject_history_service.py` 的 reason Pareto 邏輯改為可指定 `dimension` 參數（`reason` / `package` / `type` / `workflow` / `workcenter` / `equipment`）。

## Risks / Trade-offs

### R1: 原物料資料量
原物料紀錄可能比 upstream_history 多很多（一個 LOT 可能消耗多種材料）。2000 個 LOT + 血緣的原物料查詢可能返回大量資料。
→ **Mitigation**: EventFetcher 已有 batch + cache 機制。若資料量過大，可限制原物料歸因只取前幾種 material_part_name（如前 20 種），其餘歸為「其他」。

### R2: LineageEngine root 不一定是晶圓
Split chain 的 root 可能不總是代表「晶圓批次」，取決於產品結構。某些產品線的 root 可能是其他中間製程的 LOT。
→ **Mitigation**: 以 `root_container_name` 顯示，不硬標籤為「晶圓」。UI label 用「源頭批次」而非「晶圓」。

### R3: Staged trace events 增加 domain 的延遲
新增 materials domain 會增加 events stage 的執行時間。
→ **Mitigation**: EventFetcher 已支援 concurrent domain 查詢（ThreadPoolExecutor），materials 和 upstream_history 可並行。Cache TTL 300s 也能有效減輕重複查詢。

### R4: 嫌疑機台維修資料可能需要新的 API
目前 query-tool 的 jobs API 是以 container_id 或 equipment + time_range 查詢，沒有「某台設備的近期 N 筆維修」的 endpoint。
→ **Mitigation**: 新增一個輕量的 equipment-recent-jobs endpoint，或在前端直接用 equipment-period jobs API 查近 30 天即可。

### R5: 報廢歷史查詢的 Pareto 維度切換需要後端支援
目前 Pareto 只支援按 reason 聚合，新增其他維度需要後端 SQL 重寫。
→ **Mitigation**: 報廢歷史查詢使用 two-phase caching pattern（完整 DataFrame 已快取），在 view refresh 階段做不同維度的 groupby 即可，不需重新查 DB。
