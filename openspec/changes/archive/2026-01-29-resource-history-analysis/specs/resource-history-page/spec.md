## ADDED Requirements

### Requirement: 頁面路由與存取

系統 SHALL 提供 `/resource-history` 路由存取機台歷史表現分析頁面。

#### Scenario: 存取歷史分析頁面
- **WHEN** 使用者導航至 `/resource-history`
- **THEN** 系統顯示機台歷史表現分析頁面

#### Scenario: 頁面初始狀態
- **WHEN** 頁面首次載入
- **THEN** 系統顯示篩選條件區但不載入任何資料
- **THEN** 圖表和表格區域顯示「請設定查詢條件」提示

---

### Requirement: 日期範圍篩選

系統 SHALL 提供日期範圍選擇器，允許使用者指定查詢的起迄日期。

#### Scenario: 選擇日期範圍
- **WHEN** 使用者設定開始日期為 2024-01-01，結束日期為 2024-01-31
- **THEN** 系統記錄查詢範圍為該期間

#### Scenario: 日期範圍限制
- **WHEN** 使用者選擇超過 365 天的日期範圍
- **THEN** 系統顯示警告訊息「查詢範圍不可超過一年」
- **THEN** 系統阻止查詢執行

#### Scenario: 預設日期範圍
- **WHEN** 頁面載入時
- **THEN** 日期範圍預設為最近 7 天（不含今日）

---

### Requirement: 時間粒度切換

系統 SHALL 提供日/週/月/年四種時間粒度選項，用於控制資料聚合方式。

#### Scenario: 切換至日粒度
- **WHEN** 使用者選擇「日」粒度
- **THEN** 後續查詢以每日為單位聚合資料

#### Scenario: 切換至週粒度
- **WHEN** 使用者選擇「週」粒度
- **THEN** 後續查詢以 ISO 週為單位聚合資料

#### Scenario: 切換至月粒度
- **WHEN** 使用者選擇「月」粒度
- **THEN** 後續查詢以每月為單位聚合資料

#### Scenario: 切換至年粒度
- **WHEN** 使用者選擇「年」粒度
- **THEN** 後續查詢以每年為單位聚合資料

#### Scenario: 預設粒度
- **WHEN** 頁面載入時
- **THEN** 時間粒度預設為「日」

---

### Requirement: 站點與型號篩選

系統 SHALL 提供站點（Workcenter）和機台型號（Resource Family）下拉選單進行資料篩選。

#### Scenario: 篩選特定站點
- **WHEN** 使用者從站點下拉選單選擇「WC01」
- **THEN** 查詢結果僅包含該站點的資料

#### Scenario: 篩選特定型號
- **WHEN** 使用者從型號下拉選單選擇「FAM01」
- **THEN** 查詢結果僅包含該型號的資料

#### Scenario: 組合篩選
- **WHEN** 使用者同時選擇站點「WC01」和型號「FAM01」
- **THEN** 查詢結果僅包含同時符合兩個條件的資料

#### Scenario: 動態載入篩選選項
- **WHEN** 頁面載入時
- **THEN** 系統從資料庫載入可用的站點和型號列表

---

### Requirement: 設備旗標篩選

系統 SHALL 提供生產機、關鍵機、監控機三個 checkbox 篩選選項。

#### Scenario: 篩選生產機
- **WHEN** 使用者勾選「生產機」checkbox
- **THEN** 查詢結果僅包含 PJ_ISPRODUCTION = 1 的機台

#### Scenario: 篩選關鍵機
- **WHEN** 使用者勾選「關鍵機」checkbox
- **THEN** 查詢結果僅包含 PJ_ISKEY = 1 的機台

#### Scenario: 篩選監控機
- **WHEN** 使用者勾選「監控機」checkbox
- **THEN** 查詢結果僅包含 PJ_ISMONITOR = 1 的機台

---

### Requirement: 查詢觸發

系統 SHALL 提供查詢按鈕，使用者點擊後才執行資料查詢。

#### Scenario: 執行查詢
- **WHEN** 使用者設定完篩選條件後點擊「查詢」按鈕
- **THEN** 系統根據篩選條件執行查詢
- **THEN** 系統顯示載入指示器
- **THEN** 查詢完成後更新 KPI、圖表、表格

#### Scenario: 查詢失敗處理
- **WHEN** 查詢執行失敗（如網路錯誤、超時）
- **THEN** 系統顯示錯誤訊息 toast 通知
- **THEN** 系統隱藏載入指示器

---

### Requirement: KPI 摘要卡片

系統 SHALL 顯示 6 個 KPI 摘要卡片：OU%、PRD 時數、UDT 時數、SDT 時數、EGT 時數、機台數。

#### Scenario: 顯示 OU%
- **WHEN** 查詢完成
- **THEN** 系統顯示查詢範圍內的整體 OU%
- **THEN** OU% 計算公式為 PRD / (PRD + SBY + EGT + SDT + UDT) * 100

#### Scenario: 顯示各狀態時數
- **WHEN** 查詢完成
- **THEN** 系統顯示 PRD、UDT、SDT、EGT 的總時數（小時）

#### Scenario: 顯示機台數
- **WHEN** 查詢完成
- **THEN** 系統顯示符合篩選條件的不重複機台數量

---

### Requirement: OU% 趨勢折線圖

系統 SHALL 顯示 OU% 隨時間變化的折線圖。

#### Scenario: 顯示趨勢圖
- **WHEN** 查詢完成
- **THEN** 系統顯示 X 軸為時間、Y 軸為 OU% 的折線圖
- **THEN** X 軸根據時間粒度顯示對應的日期標籤

#### Scenario: 圖表互動
- **WHEN** 使用者將滑鼠移至圖表上的數據點
- **THEN** 系統顯示該時間點的詳細數值（日期、OU%、PRD 時數等）

---

### Requirement: E10 狀態堆疊長條圖

系統 SHALL 顯示各時間點的 E10 設備狀態時數分布堆疊長條圖。

#### Scenario: 顯示堆疊圖
- **WHEN** 查詢完成
- **THEN** 系統顯示 X 軸為時間、Y 軸為時數的堆疊長條圖
- **THEN** 每個長條包含 PRD、SBY、UDT、SDT、EGT、NST 六種狀態的堆疊

#### Scenario: 圖表圖例
- **WHEN** 圖表顯示時
- **THEN** 系統顯示各狀態的顏色圖例
- **THEN** 使用者可點擊圖例切換該狀態的顯示/隱藏

---

### Requirement: 工站 OU% 對比水平條形圖

系統 SHALL 顯示各站點 OU% 的水平條形圖比較。

#### Scenario: 顯示對比圖
- **WHEN** 查詢完成
- **THEN** 系統顯示各站點的 OU% 水平條形圖
- **THEN** 條形圖按 OU% 由高到低排序

---

### Requirement: 設備狀態熱力圖

系統 SHALL 顯示站點 × 時間的 OU% 熱力圖。

#### Scenario: 顯示熱力圖
- **WHEN** 查詢完成
- **THEN** 系統顯示 X 軸為時間、Y 軸為站點的熱力圖
- **THEN** 顏色深淺表示該站點在該時間的 OU%

#### Scenario: 熱力圖顏色編碼
- **WHEN** 熱力圖顯示時
- **THEN** OU% 高（> 80%）顯示綠色
- **THEN** OU% 中（50-80%）顯示黃色
- **THEN** OU% 低（< 50%）顯示紅色

---

### Requirement: 階層式明細表格

系統 SHALL 顯示可展開的階層式明細表格，支援站點 → 型號 → 個別機台三層結構。

#### Scenario: 顯示站點層級
- **WHEN** 查詢完成
- **THEN** 表格預設顯示站點層級的彙總資料
- **THEN** 每列顯示展開/收合按鈕

#### Scenario: 展開至型號層級
- **WHEN** 使用者點擊站點列的展開按鈕
- **THEN** 系統顯示該站點下各型號的彙總資料
- **THEN** 型號列以縮排方式呈現

#### Scenario: 展開至機台層級
- **WHEN** 使用者點擊型號列的展開按鈕
- **THEN** 系統顯示該型號下各機台的詳細資料
- **THEN** 機台列以更深縮排方式呈現

#### Scenario: 全部展開
- **WHEN** 使用者點擊「全部展開」按鈕
- **THEN** 系統展開所有層級顯示完整明細

---

### Requirement: 表格欄位

系統 SHALL 在明細表格中顯示以下欄位：站點/型號/機台、OU%、PRD（時數/佔比）、SBY（時數/佔比）、UDT（時數/佔比）、SDT（時數/佔比）、EGT（時數/佔比）、NST（時數/佔比）、機台數。

#### Scenario: 顯示時數與佔比
- **WHEN** 表格顯示資料時
- **THEN** 各 E10 狀態欄位同時顯示時數（小時）和佔比（百分比）
- **THEN** 格式為「123.4h (45.6%)」

#### Scenario: 機台數欄位
- **WHEN** 顯示站點或型號層級時
- **THEN** 機台數欄位顯示該群組的不重複機台數量
- **WHEN** 顯示機台層級時
- **THEN** 機台數欄位顯示 1

---

### Requirement: 資料匯出

系統 SHALL 提供 CSV 格式的資料匯出功能。

#### Scenario: 匯出明細資料
- **WHEN** 使用者點擊「匯出」按鈕
- **THEN** 系統生成包含所有明細資料的 CSV 檔案
- **THEN** 瀏覽器自動下載該檔案
- **THEN** 檔案名稱包含查詢日期範圍

#### Scenario: 匯出大量資料
- **WHEN** 查詢結果超過 10000 筆
- **THEN** 系統仍完整匯出所有資料
- **THEN** 系統顯示匯出進度提示
