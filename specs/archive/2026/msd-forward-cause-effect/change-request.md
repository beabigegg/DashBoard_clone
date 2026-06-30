# Change Request

## Original Request

MSD 順向(forward)中段不良分析 Phase 3:建立「前段報廢項目 → 後製程影響 → 後段報廢如何變化」的因果分析能力。

工程師想看到:① 前段(偵測站)報廢了什麼項目(不良原因),② 對應到後製程(下游站)會有什麼影響,③ 後製程相對應的報廢會怎麼變化。核心是 cause→effect 連結:前段偵測不良 → 下游站點影響 → 下游報廢行為。

背景(已完成 Phase 1+2,commit `e2931e1b`):forward 已支援 package/type 母體 mask、明細表已可運作;但 forward 仍走 in-memory pandas 路徑,`get_summary(direction="forward")` 故意 `return None` 退回 in-memory。

### 核心正確性洞(必修)
`_attribute_forward_defects`(mid_section_defect_service.py:2606)只用 `cid in defect_cids` 歸因下游事件;forward lineage(`children_map`)有被拿去**抓**下游資料,卻沒拿去**歸因** → lot 在下游分裂/合併/改名(child container)後的報廢全被丟掉。且 forward **完全沒寫 lineage spool**(只有 backward 有)。

### 本 change 範圍 = 完整 Phase 3(forward 對齊 backward 的分析深度)

> 決策:原先構想的「對照組 / flagged-vs-clean lift(3b)」**不做** —— backward 也只做直接歸因、無任何基準對照能力(經程式碼確認),3b 屬整個 dashboard 都沒有的新分析,over-engineering 且需擴大 Oracle 抓取範圍。問題③「後段報廢如何變化」改以下游 cross-tab + 趨勢圖呈現,不引入正式對照組。

- 寫 forward lineage stage spool(`SEED_ID, DESCENDANT_ID`),下游事件 re-key 回源頭偵測 lot
- 修正下游歸因:涵蓋分裂/合併後的 descendant 報廢(目前 per-CONTAINERID-only 會丟失)
- 新增聚合 `[偵測 LOSSREASONNAME] × [下游 WORKCENTER_GROUP]` cross-tab(reject 量/率);新增 `by_detection_loss_reason` 圖(forward 目前缺前段不良原因圖);下游報廢趨勢呈現問題③
- 讓 `get_summary(direction="forward")` 走 DuckDB,退役部分 in-memory 路徑(會關閉目前 2 個 `xfail(strict)` forward-summary spool 測試 tripwire)
- 前端:Sankey hero(前段原因→下游站,點擊 cross-filter)+ heatmap toggle;KPI 加「放大倍率」(下游不良率÷前段不良率);明細加「前段不良原因」欄

## Business / User Goal

讓中段工程師能從「前段偵測不良」直接看到「對後製程的下游報廢影響與放大」,把目前 4 張互不關聯的 Pareto 圖升級為 cause→effect 的故事(原因→站點→變化),支援自助根因/影響分析。

## Non-goals

- **不做對照組 / clean-vs-flagged lift 分析** —— backward 無對應能力,屬 over-engineering;不擴大下游事件抓取範圍(仍只抓 defect lots 的 tracked 下游,不抓 clean 母體)。
- 不改 backward(反向)既有行為(Phase 1/2 已完成,backward 為單一事實基準)。
- 不在本變更引入新的外部資料源;僅在現有 MES Oracle 表 + DuckDB spool 架構內。
- query-tool 等共用引擎的根源完整展開語意不在本變更範圍(MSD 不需追到 WAFER 完整展開)。

## Constraints

- 檔案/spool 路徑必須同時相容 host 與 Docker(無硬編絕對路徑、不靠 cwd/__file__ 猜根)。
- i18n:任何新增使用者可見文字需同步所有語言檔。
- CSS 須 scope 在 `.theme-mid-section-defect`;Tailwind token,無硬編 hex/px;ECharts 走 vue-echarts(`@click` 綁在 `<VChart>`)。
- 新 spool + 抓取範圍變更屬高風險(concurrency / 大查詢),需 stress/soak 評估。
- routes 不放業務邏輯;API 回應走 `core/response.py` helpers。

## Known Context

- 背景設計分析(資料模型 + DuckDB SQL 草案、UX/Sankey/heatmap mockup)已產出,作為 design 輸入。
- 受影響主要檔案:`src/mes_dashboard/services/mid_section_defect_service.py`(forward 聚合/歸因/明細)、`msd_duckdb_runtime.py`(get_summary/get_detail forward)、`trace_job_service.py`(spool 寫入/orchestration)、`routes/mid_section_defect_routes.py`、`routes/trace_routes.py`;前端 `frontend/src/mid-section-defect/`(App.vue、components/KpiCards/DetailTable/ParetoChart/TrendChart + 新 Sankey/Heatmap)。
- 相關紀錄:Phase 1/2 commit `e2931e1b`;cache-spool / service-patterns 既有 promoted learnings(見 CLAUDE.md)。

## Open Questions

- forward lineage spool 的 `SEED_ID` 是用「偵測 defect lot」還是「seed root」為錨點?
- 「放大倍率」分母為 0(前段不良率=0)時的顯示與語意。
- Sankey/heatmap 的 Top-N 截斷門檻(節點過多會難讀)。

## Requested Delivery Date / Priority

接續 Phase 1/2,本 change(3a)優先;3b(`msd-forward-control-cohort-lift`)視 3a 成果與抓取成本再排程。
