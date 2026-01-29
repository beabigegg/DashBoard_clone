## ADDED Requirements

### Requirement: 歷史資料摘要查詢

系統 SHALL 提供 API 端點 `GET /api/resource/history/summary` 查詢機台歷史效能摘要資料。

#### Scenario: 查詢日粒度摘要
- **WHEN** 呼叫 API 並傳入 start_date=2024-01-01, end_date=2024-01-07, granularity=day
- **THEN** 系統回傳該期間以日為單位聚合的 KPI、趨勢、熱力圖、站點比較資料

#### Scenario: 查詢週粒度摘要
- **WHEN** 呼叫 API 並傳入 granularity=week
- **THEN** 系統使用 TRUNC(TXNDATE, 'IW') 以 ISO 週為單位聚合資料

#### Scenario: 查詢月粒度摘要
- **WHEN** 呼叫 API 並傳入 granularity=month
- **THEN** 系統使用 TRUNC(TXNDATE, 'MM') 以月為單位聚合資料

#### Scenario: 查詢年粒度摘要
- **WHEN** 呼叫 API 並傳入 granularity=year
- **THEN** 系統使用 TRUNC(TXNDATE, 'YYYY') 以年為單位聚合資料

#### Scenario: 帶篩選條件查詢
- **WHEN** 呼叫 API 並傳入 workcenter=WC01, family=FAM01
- **THEN** 系統回傳僅符合該站點和型號的資料

#### Scenario: 回傳資料結構
- **WHEN** 查詢成功
- **THEN** 回傳 JSON 包含 kpi、trend、heatmap、workcenter_comparison 四個區塊

---

### Requirement: OU% 計算公式

系統 SHALL 使用標準 OU% 計算公式：PRD / (PRD + SBY + EGT + SDT + UDT) * 100。

#### Scenario: 計算 OU%
- **WHEN** PRD=800, SBY=100, EGT=50, SDT=30, UDT=20
- **THEN** OU% = 800 / (800+100+50+30+20) * 100 = 80%

#### Scenario: 排除 NST
- **WHEN** 計算 OU% 時
- **THEN** 分母不包含 NST（Not Scheduled Time）

#### Scenario: 處理零分母
- **WHEN** PRD + SBY + EGT + SDT + UDT = 0
- **THEN** OU% 回傳 0 而非錯誤

---

### Requirement: E10 狀態時數與佔比計算

系統 SHALL 計算各 E10 狀態（PRD、SBY、UDT、SDT、EGT、NST）的時數和佔比。

#### Scenario: 計算狀態時數
- **WHEN** 查詢特定期間的資料
- **THEN** 系統從 DW_MES_RESOURCESTATUS_SHIFT.HOURS 欄位聚合各狀態時數

#### Scenario: 計算狀態佔比
- **WHEN** 計算各狀態佔比
- **THEN** 佔比 = 該狀態時數 / 全部狀態時數總和 * 100

#### Scenario: 按狀態分組聚合
- **WHEN** 聚合資料時
- **THEN** 系統根據 OLDSTATUSNAME 欄位識別 PRD、SBY、UDT、SDT、EGT、NST

---

### Requirement: 階層式明細資料查詢

系統 SHALL 提供 API 端點 `GET /api/resource/history/detail` 查詢階層式明細資料。

#### Scenario: 查詢明細資料
- **WHEN** 呼叫 API 並傳入日期範圍和粒度
- **THEN** 系統回傳包含 WORKCENTERNAME、RESOURCEFAMILYNAME、RESOURCENAME 三個維度的扁平化資料

#### Scenario: 分頁查詢
- **WHEN** 呼叫 API 並傳入 page=2, page_size=100
- **THEN** 系統回傳第 101-200 筆資料
- **THEN** 回傳包含 total 總筆數供前端分頁

#### Scenario: 回傳欄位
- **WHEN** 查詢成功
- **THEN** 每筆資料包含：workcenter、family、resource、ou_pct、prd_hours、prd_pct、sby_hours、sby_pct、udt_hours、udt_pct、sdt_hours、sdt_pct、egt_hours、egt_pct、nst_hours、nst_pct、machine_count

---

### Requirement: 篩選選項查詢

系統 SHALL 提供 API 端點查詢可用的篩選選項。

#### Scenario: 查詢站點列表
- **WHEN** 頁面載入時呼叫篩選選項 API
- **THEN** 系統回傳所有可用的 WORKCENTERNAME 列表

#### Scenario: 查詢型號列表
- **WHEN** 頁面載入時呼叫篩選選項 API
- **THEN** 系統回傳所有可用的 RESOURCEFAMILYNAME 列表

---

### Requirement: 資料匯出服務

系統 SHALL 提供 API 端點 `GET /api/resource/history/export` 匯出 CSV 格式資料。

#### Scenario: 匯出 CSV
- **WHEN** 呼叫 API 並傳入 format=csv 和篩選條件
- **THEN** 系統回傳 Content-Type: text/csv 的檔案下載
- **THEN** 檔案包含所有符合條件的明細資料

#### Scenario: CSV 欄位
- **WHEN** 匯出 CSV 時
- **THEN** 包含欄位：站點、型號、機台、OU%、PRD(h)、PRD(%)、SBY(h)、SBY(%)、UDT(h)、UDT(%)、SDT(h)、SDT(%)、EGT(h)、EGT(%)、NST(h)、NST(%)

#### Scenario: 處理大量資料匯出
- **WHEN** 匯出資料量超過 10000 筆
- **THEN** 系統使用串流方式輸出避免記憶體溢出

---

### Requirement: 資料來源與關聯

系統 SHALL 從 DW_MES_RESOURCESTATUS_SHIFT 表查詢歷史狀態資料，並關聯 DW_MES_RESOURCE 表取得機台維度資訊。

#### Scenario: 資料表關聯
- **WHEN** 查詢資料時
- **THEN** 系統使用 HISTORYID = RESOURCEID 關聯兩表

#### Scenario: 篩選條件
- **WHEN** 查詢資料時
- **THEN** 系統套用 OBJECTCATEGORY/OBJECTTYPE 篩選（ASSEMBLY 或 WAFERSORT）
- **THEN** 系統排除 EXCLUDED_LOCATIONS 和 EXCLUDED_ASSET_STATUSES 中定義的資料

#### Scenario: 時間範圍篩選
- **WHEN** 查詢資料時
- **THEN** 系統使用 TXNDATE 欄位進行日期範圍篩選

---

### Requirement: 查詢效能優化

系統 SHALL 實作查詢效能優化措施。

#### Scenario: 日期範圍限制
- **WHEN** 查詢日期範圍超過 365 天
- **THEN** 系統回傳錯誤訊息「查詢範圍不可超過一年」

#### Scenario: 索引使用
- **WHEN** 執行查詢時
- **THEN** 系統確保 SQL 查詢能使用 TXNDATE 索引

#### Scenario: 查詢超時
- **WHEN** 查詢執行超過 60 秒
- **THEN** 系統中斷查詢並回傳超時錯誤
