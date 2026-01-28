# WIP Status Filter

## 問題描述

WIP 即時概況頁面目前顯示三個狀態卡片（RUN / QUEUE / HOLD）和 Workcenter × Package Matrix 表格，但兩者之間沒有互動關係。

使用者想快速查看「目前有多少 WIP 正在 RUN」或「HOLD 的量分布在哪些工站」時，需要另外到 Detail 頁面篩選，操作不便。

## 目標

在 WIP Overview 頁面新增卡片篩選功能：
- 點選 RUN / QUEUE / HOLD 卡片時，Matrix 表格只顯示該狀態的數量
- 再點一次同一卡片則解除篩選（toggle 行為）
- 提供清晰的視覺回饋，讓使用者知道目前的篩選狀態

## 目標用戶

- 生產主管：快速了解各狀態的分布
- 值班人員：追蹤 HOLD 量的工站分布

## 預期行為

1. **初始狀態**：Matrix 顯示全部數量（現行行為）
2. **點選卡片**：
   - 卡片顯示「選中」樣式（例如外框加粗、背景變深）
   - Matrix 重新載入，只顯示該狀態的數量
   - 其他兩張卡片恢復「未選中」樣式
3. **再次點選同一卡片**：
   - 卡片恢復「未選中」樣式
   - Matrix 恢復顯示全部數量
4. **篩選期間**：
   - Summary 區域的 Total Lots / Total QTY 不變（保持全局統計）
   - Hold Summary 區塊不受影響

## 範圍界定

### 包含
- 前端：卡片點擊事件、選中樣式、Matrix 重載邏輯
- 後端：`/api/wip/overview/matrix` 新增 `status` 參數（可選，值為 RUN/QUEUE/HOLD）
- 後端：`get_wip_matrix()` 函數新增 `status` 篩選條件

### 不包含
- Summary 卡片的數值變動（維持全局統計）
- Hold Summary 區塊的篩選
- URL 參數同步（不影響分享連結）
- 鍵盤快捷鍵

## 技術考量

### WIP 狀態判斷邏輯（與 IT 定義一致）

```sql
CASE
    WHEN EQUIPMENTCOUNT > 0 THEN 'RUN'
    WHEN CURRENTHOLDCOUNT > 0 THEN 'HOLD'
    ELSE 'QUEUE'
END AS WIP_STATUS
```

### API 變更

```
GET /api/wip/overview/matrix?status=RUN
GET /api/wip/overview/matrix?status=QUEUE
GET /api/wip/overview/matrix?status=HOLD
GET /api/wip/overview/matrix  (不帶參數 = 全部)
```

### 前端狀態

```javascript
let activeStatusFilter = null;  // null | 'run' | 'queue' | 'hold'
```

## 風險評估

| 風險 | 影響 | 緩解措施 |
|------|------|----------|
| API 查詢變慢 | 低 | 狀態條件可利用現有索引 |
| 使用者混淆篩選狀態 | 中 | 明確的視覺回饋 + 載入提示 |

## 成功標準

- 點擊卡片後 Matrix 正確顯示篩選結果
- 視覺回饋清晰，使用者能直觀理解當前狀態
- 篩選操作響應時間 < 1 秒
