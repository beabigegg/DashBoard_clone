## ADDED Requirements

### Requirement: Unified Card Structure
兩個頁面（設備即時機況、設備歷史績效）的 KPI 卡片 SHALL 包含相同的 9 張卡片，順序固定如下：
1. OU%（稼動率）
2. Availability%（可用率）
3. PRD（生產）
4. SBY（待機）
5. UDT（非計畫停機）
6. SDT（計畫停機）
7. EGT（工程）
8. NST（未排程）
9. 機台數（設備總數）

#### Scenario: Card order verification on real-time status page
- **WHEN** 使用者開啟設備即時機況頁面
- **THEN** 頁面 SHALL 依序顯示 9 張卡片：OU%、Availability%、PRD、SBY、UDT、SDT、EGT、NST、機台數

#### Scenario: Card order verification on historical performance page
- **WHEN** 使用者開啟設備歷史績效頁面
- **THEN** 頁面 SHALL 依序顯示 9 張卡片：OU%、Availability%、PRD、SBY、UDT、SDT、EGT、NST、機台數

### Requirement: Unified Card Labels
每張卡片 SHALL 顯示統一的主標籤與副標籤。

| 主標籤 | 副標籤 |
|--------|--------|
| OU% | 稼動率 |
| Availability% | 可用率 |
| PRD | 生產 |
| SBY | 待機 |
| UDT | 非計畫停機 |
| SDT | 計畫停機 |
| EGT | 工程 |
| NST | 未排程 |
| 機台數 | 設備總數 |

#### Scenario: Label consistency across pages
- **WHEN** 使用者查看任一頁面的 PRD 卡片
- **THEN** 主標籤 SHALL 為「PRD」，副標籤 SHALL 為「生產」

### Requirement: Real-time Status Card Display Format
設備即時機況頁面的狀態卡片（PRD、SBY、UDT、SDT、EGT、NST）SHALL 顯示台數與佔比。

#### Scenario: Real-time PRD card display
- **WHEN** 系統有 120 台設備，其中 42 台處於 PRD 狀態
- **THEN** PRD 卡片 SHALL 顯示「42」作為主要數值，並顯示佔比百分比

#### Scenario: Real-time card with zero count
- **WHEN** 某狀態無任何機台
- **THEN** 該狀態卡片 SHALL 顯示「0」作為主要數值，佔比顯示「0.0%」

### Requirement: Historical Performance Card Display Format
設備歷史績效頁面的狀態卡片（PRD、SBY、UDT、SDT、EGT、NST）SHALL 顯示小時數（HR）與佔比。

#### Scenario: Historical PRD card display
- **WHEN** 查詢期間 PRD 總時數為 1234 小時，總時數為 2800 小時
- **THEN** PRD 卡片 SHALL 顯示「1,234 HR」或「1.2K HR」作為主要數值，並顯示佔比百分比

#### Scenario: Historical card large number formatting
- **WHEN** 某狀態時數 >= 1000 小時
- **THEN** 該狀態卡片 SHALL 以 K 為單位顯示（如 1.2K HR）

### Requirement: Status Percentage Calculation
狀態佔比 SHALL 使用以下公式計算：
```
佔比% = 該狀態值 / (PRD + SBY + UDT + SDT + EGT + NST) × 100
```
分母包含所有 6 種狀態的總和。

#### Scenario: Percentage calculation with all statuses
- **WHEN** PRD=100, SBY=50, UDT=20, SDT=10, EGT=15, NST=5（總計 200）
- **THEN** PRD 佔比 SHALL 為 50.0%，SBY 佔比 SHALL 為 25.0%

#### Scenario: Percentage when total is zero
- **WHEN** 所有狀態值皆為 0
- **THEN** 所有狀態佔比 SHALL 顯示「--」或「0.0%」

### Requirement: Real-time OU Percentage Calculation
設備即時機況頁面的 OU% SHALL 使用以下公式計算：
```
OU% = PRD台數 / (PRD + SBY + UDT + SDT + EGT) 台數 × 100
```
分母不包含 NST。

#### Scenario: Real-time OU calculation
- **WHEN** PRD=42, SBY=30, UDT=10, SDT=5, EGT=8, NST=25 台
- **THEN** OU% SHALL 為 42/(42+30+10+5+8)×100 = 44.2%

### Requirement: Real-time Availability Percentage Calculation
設備即時機況頁面的 Availability% SHALL 使用以下公式計算：
```
Availability% = (PRD + SBY + EGT) 台數 / 總設備數 × 100
```

#### Scenario: Real-time Availability calculation
- **WHEN** PRD=42, SBY=30, EGT=8，總設備數=120 台
- **THEN** Availability% SHALL 為 (42+30+8)/120×100 = 66.7%

### Requirement: Machine Count Card
機台數卡片 SHALL 顯示設備總數。

#### Scenario: Real-time machine count
- **WHEN** 使用者查看設備即時機況頁面
- **THEN** 機台數卡片 SHALL 顯示符合篩選條件的總設備數

#### Scenario: Historical machine count
- **WHEN** 使用者查看設備歷史績效頁面
- **THEN** 機台數卡片 SHALL 顯示查詢期間內不重複的機台數量
