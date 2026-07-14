# Change Request

## Original Request

生產達成率 (Production Achievement Rate) 報表全面改版。

背景：現有報表僅以 (shift_code, workcenter_group) 分組顯示每日/區間產出 vs 目標，透過自訂起訖日期查詢。本次改版新增 PACKAGE_LF（封裝/Leadframe）作為報表的第一級分組維度，並重新設計整個頁面互動模式與資料管線。

完整需求（已與使用者逐項確認，設計已於 plan mode 完成並核准，計畫檔案位於 /home/egg/.claude/plans/calm-plotting-diffie.md，須完整讀取該檔案作為本次 change 的權威實作依據）：

1. Oracle SQL 撈取新增 DW_MES_LOTWIPHISTORY.PACKAGE_LF 欄位（已透過即時查詢確認該欄位存在，VARCHAR2(60)，今年至今 37 種不同值）。

2. 新增 MySQL 可管理的 PACKAGE_LF 合併分組表（稀疏例外表、fallback-to-self 語意）：SOD-123FL OP1+SOD-123FL→SOD-123FL；SOT23-5L+SOT23-6L→SOT23-5L/6L；SOT-543+SOT-553+SOT-563→SOT-543/553/563；TO-277+TO-277B→TO-277(B)；其餘含 HD 後綴、TO-277C、點測等一律獨立成組，不在表中的原始值 fallback 為自己。

3. workcenter_group 沿用現有 DW_MES_SPEC_WORKCENTER_V 來源，新增 MySQL 可管理的 workcenter 合併對照表（explicit-inclusion 語意，不在表中=排除）：焊接_WB+焊接_DW 合併為「焊接_WB」，焊接_DB 獨立，另外成型/去膠/移印/水吹砂/電鍍/切彎腳/TMTT/品檢/FQC 這 9 項 1:1 對應，清單外其餘原始 group（切割/PKG_SAW/點測/可靠性/補鍍/預備站/成品倉/IST/CP線邊倉/成品入庫/已CP入庫/已CP倉/DS線邊倉/MA/TCT）一律排除。

4. 新增 MySQL 每日計畫表，鍵值為 (workcenter_group[合併後], package_lf_group[合併後])，不分班別，與現有以 shift_code 分的 targets 表並存、互不影響。

5. 每日產出 = D班+N班加總；每日達成率 = 每日產出/每日計畫。

6. 權限：完全沿用現有 can_edit_targets() 白名單機制（不新建權限系統），僅擴大其授權範圍涵蓋新的 3 張表。

7. 前端由現有「自訂日期區間+多選篩選」改為 4 種固定檢視模式：當日／前日／當月／自訂區間（保留但改用累計樣式呈現）。四種模式共用一個「站點群組」單選篩選器（來源=合併後的 12 個 workcenter_group，預設「焊接_DB」）。

8. 當日/前日：資料表以 PACKAGE_LF 分組為列，欄位為 D班產出/N班產出/每日產出/每日計畫/每日達成率；圖表為每個 PACKAGE_LF 分組一根柱子，以每日計畫為 100% 基準，D%+N% 堆疊（可能<100%、=100%、>100%），取代現有 AchievementChart.vue。

9. 當月/自訂區間：資料表欄位為累計計畫(每日計畫×已過天數)/累計產出/累計差異/累計達成率；圖表為逐日趨勢，同樣 D%+N% 堆疊，跨所有 PACKAGE_LF 分組加總後計算（先加總分子分母再相除，不可先算個別百分比再平均）。當月查詢日為 1 號時顯示上個月完整月資料。

10. 當日/前日改為由背景熱快取供應（沿用現有 core/spool_warmup_scheduler.py 每小時排程機制，新增 2 個 warmup job，直接重用 ProductionAchievementJob 並 override progress_report() 避免 Redis 孤兒 key），而非即時查 Oracle；快取未命中時無縫退回現有 202 async-spool 輪詢流程。

11. 新增獨立設定頁面（新 route /production-achievement-settings，無側邊欄項目，僅能透過報表頁「設定」按鈕進入），供有權限帳號管理上述 3 張新表；無權限者唯讀。

12. 一併修復隨計畫發現的既有資料缺口：查詢區間最後一天的 N 班次日 00:00-07:29 尾段目前會被漏採（chunk_end_excl 邊界問題），需擴充為完整 datetime 並新增一個窄幅收尾 chunk。

13. 相關 contracts（business-rules.md、api-contract.md、data-shape-contract.md）與 ADR-0016 延伸說明皆需同步更新。

這是單一大型 CDD change（使用者已明確選擇不拆分為多個循序 change）。

## Business / User Goal

## Non-goals

## Constraints

## Known Context

## Open Questions

## Requested Delivery Date / Priority
