# Change Request

## Original Request

在「生產輔助」抽屜新增一個「UPH表現」頁面（route: /uph-performance, order: 3),用於分析 GDBA(Die Bond) 與 GWBA(Wire Bond) 設備的 UPH（每小時產出）表現。

資料來源與查詢邏輯：
- 從 DWH.EAP_EVENT 撈事件來源：EVENT_TYPE LIKE '%_M[60]' AND LOT_ID IS NOT NULL AND EQUIPMENT_ID LIKE 'GDBA%' OR EQUIPMENT_ID LIKE 'GWBA%'（僅此兩家族，範圍限定），LAST_UPDATE_TIME 區間為必要的索引篩選（比照 EA-03 規則，不可全表掃描，窗口需分片）
- JOIN DWH.EAP_EVENT_DETAIL（SEQ_ID 為 join key），依設備家族取對應的 PARAMETER_NAME：EQUIPMENT_ID 前綴 GDBA → PARAMETER_NAME='BondUPH'；前綴 GWBA → PARAMETER_NAME='fHCM_UPH'。取得的 PARAMETER_VALUE 直接作為 UPH 數值使用，不做任何尺度換算（例如不除以100）。
- 維度擴充 1：LOT_ID = DW_MES_CONTAINER.CONTAINERNAME 橋接（沿用 eap_alarm_worker.py 的 bridging pattern，因 DW_MES_WIP 無 CONTAINERID 索引），取得 PRODUCTLINENAME（前端顯示名稱為「Package」）、PJ_TYPE（前端顯示名稱為「Type」）
- 維度擴充 2：EQUIPMENT_ID = DW_MES_RESOURCE.RESOURCENAME 橋接（OBJECTCATEGORY='ASSEMBLY' 時 RESOURCENAME 即設備編號），取得 WORKCENTERNAME，並對應 src/mes_dashboard/config/workcenter_groups.py 的 焊接_DB/焊接_WB 分組作為 DB/WB 標籤

執行模式：
- 純非同步（比照 eap-alarm 與 production-achievement，無同步 fallback），採用 BaseChunkedDuckDBJob（TIME chunk strategy）
- max_parallel=3、單一 RQ worker process，比照現有安全模式，本次變更不調整並行度旋鈕（並行度提升是獨立的後續架構議題，不在本次範圍）
- 需要新的 spool namespace（加入 spool_routes._ALLOWED_NAMESPACES）、新的 execute_*_job worker（需同時wire deploy/*.service 與 scripts/start_server.sh，並使用 acquire_heavy_query_slot）、新的 *_USE_UNIFIED_JOB 環境變數旗標

頁面設計（前端）：
- 全域篩選器：日期區間（必填）、設備家族 GDBA/GWBA(DB/WB)、WORKCENTERNAME、Package(PRODUCTLINENAME)、Type(PJ_TYPE)、設備編號搜尋
- 趨勢圖：UPH 隨時間變化（M[60] 原始頻率，約每小時一筆），可依設備/家族/Package 分組疊圖
- 設備排行區塊：依 Type 分組呈現，Type 支援多選，使用此圖表「獨立於全域篩選器」的專屬 filter；由低到高排序找出 UPH 表現偏低的機台；本次不設門檻警戒值
- 明細表：逐筆事件明細（LOT_ID、EQUIPMENT_ID、時間戳、UPH 原始值、Package、Type），比照 eap-alarm 的 detail 端點模式

導覽註冊：
- frontend/src/portal-shell/navigationManifest.js：production-assist 抽屜新增 /uph-performance，order 3，displayName「UPH表現」
- docs/migration/full-modernization-architecture-blueprint/route_scope_matrix.json 的 in_scope 加入 /uph-performance
- frontend/vite.config.ts INPUT_MAP 加入 uph-performance
- frontend/src/portal-shell/routeContracts.js ROUTE_CONTRACTS 加入 /uph-performance entry（比照 /eap-alarm 的寫法）

已知風險與待確認事項（實作時需注意）：
- GDBA 的 BondUPH、GWBA 的 fHCM_UPH 這兩個 PARAMETER_NAME 是使用者最近才設定好的（尤其 GWBA 是最近才加入設定），實作 SQL 時建議先以窄時間窗（≤6小時）做探索性查詢驗證這兩個參數確實有資料回傳，再進行完整開發（參考 docs/architecture/eap-event-uph-collection-investigation.md 的既有調查方法與查詢成本注意事項）
- EAP_EVENT 資料量大（GDBA 家族單日可達近千萬筆），detail JOIN 在 24 小時窗口曾經超過 180 秒逾時，務必維持窄窗分片查詢
- 目前完全排除 GWBK/GWMT/GPTA 等無 UPH 訊號的家族，僅涵蓋 GDBA 與 GWBA，未來如有需求可另開後續 change 評估是否從 MES 表（DW_MES_HM_LOTMOVEOUT 等）推算其他家族的產出數據

## Business / User Goal

讓工程師可以自助查詢 GDBA(Die Bond)/GWBA(Wire Bond) 設備的 UPH 表現趨勢，並快速找出表現偏低的機台（依 Package/Type 分組比較），取代目前缺乏 UPH 可視化報表的現況。

## Non-goals

- 不涵蓋 GWBK/GWMT/GPTA 等目前 EAP 資料中無 UPH 訊號的家族
- 不做 UPH 數值尺度換算（例如 ×100 或 ÷100），直接顯示 PARAMETER_VALUE 原始值
- 不設計門檻警戒值/異常告警邏輯
- 不在本次變更中調整非同步查詢的並行度（max_parallel、HEAVY_QUERY_MAX_CONCURRENT、RQ worker process 數量），並行度系統性提升視為獨立的後續架構議題

## Constraints

- 必須走純非同步模式（無同步 fallback），比照 eap-alarm/production-achievement 的 BaseChunkedDuckDBJob 模式
- EAP_EVENT 查詢必須維持窄時間窗分片（單一 chunk 建議 ≤6 小時），不可對 LAST_UPDATE_TIME 做超過安全範圍的全窗口查詢
- 沿用 max_parallel=3、單一 RQ worker process 的現有安全模式
- LOT_ID→DW_MES_CONTAINER、EQUIPMENT_ID→DW_MES_RESOURCE 兩個維度 join 必須採用現有 bridging pattern（避免全表掃描）

## Known Context

- 已有 `docs/architecture/eap-event-uph-collection-investigation.md`（2026-07-08）針對 UPH 資料可行性做過唯讀 Oracle 調查，確認 GDBA 走 `<EQP>-####_M[60]` / `ProcessJob_Periodic` 週期通道；本次使用者提供的參數名稱（BondUPH / fHCM_UPH）為使用者近期在設備端新設定，與調查文件觀察到的參數名稱（如 UPHBonded）不同，需在實作時以窄窗探索性查詢驗證。
- eap_alarm_worker.py 是 EAP_EVENT/EAP_EVENT_DETAIL 查詢與 DW_MES_CONTAINER 橋接的既有範本；production_achievement 是最接近的非同步 spool + 前端頁面範本（同抽屜）。
- DB/WB 分類建議透過 DW_MES_RESOURCE.WORKCENTERNAME 對應 workcenter_groups.py 的焊接_DB/焊接_WB，而非用 EQUIPMENT_ID 前綴做封閉列舉（先前類似做法已因與真實資料不符而被下架，見業務規則 EA-07）。
- 產品維度僅能用 DW_MES_CONTAINER.PRODUCTLINENAME（顯示為 Package）與 PJ_TYPE（顯示為 Type）代替，資料庫中無真正的晶數/線數數值欄位。

## Open Questions

- BondUPH / fHCM_UPH 兩個 PARAMETER_NAME 在窄窗探索性查詢中是否確實有資料回傳（待實作階段驗證）

## Requested Delivery Date / Priority

未指定
