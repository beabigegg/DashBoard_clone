# WIP 在制品報表 - 使用說明

## 功能說明

這是一個專門查詢當前在制品 (Work In Process) 數量統計的報表工具。

### 欄位對照

根據您的需求，系統會顯示以下欄位：
- **CONTAINERNAME** = LOT ID (批次號)
- **GA_CONTAINERNAME** = GA LOT ID (GA 批次號)
- **QTY** = 數量
- **QTY2** = 片數
- **MFGORDERNAME** = GA (工單號)

### 報表內容

#### 1. 總覽統計卡片
- 總 LOT 數：當前在制品的批次總數
- 總數量 (QTY)：總數量統計
- 總片數 (QTY2)：總片數統計
- 工序數 (SPEC)：涉及的工序數量
- 工作中心數：涉及的工作中心數量
- 產品線數：涉及的產品線數量

#### 2. 按工序與工作中心統計
顯示各 SPECNAME (工序) 及 WORKCENTERNAME (工作中心) 對應的當前 WIP 數量：
- SPECNAME (工序)
- WORKCENTERNAME (工作中心)
- LOT 數
- 總數量 (QTY)
- 總片數 (QTY2)

#### 3. 按產品線統計
顯示不同產品組合 (PRODUCTLINENAME_LEF) 各佔的量：

**產品線匯總**：
- PRODUCTLINENAME_LEF (產品線)
- LOT 數合計
- 總數量 (QTY) 合計
- 總片數 (QTY2) 合計

**產品線明細**：
- PRODUCTLINENAME_LEF (產品線)
- SPECNAME (工序)
- WORKCENTERNAME (工作中心)
- LOT 數
- 總數量 (QTY)
- 總片數 (QTY2)

---

## 啟動方式

### 方法 1: 使用啟動腳本（推薦）

```bash
# 雙擊運行
scripts\啟動Dashboard.bat
```

### 方法 2: 手動啟動

```bash
# 使用虛擬環境的 Python
venv\Scripts\python.exe apps\portal.py
```

然後訪問: **http://localhost:5000**
（入口頁面可用 Tab 切換，或直接開啟 **http://localhost:5000/wip**）

---

## 使用說明

### 1. 選擇時間範圍

在頁面頂部的下拉選單中選擇：
- 最近 1 天
- 最近 3 天
- 最近 7 天（默認）
- 最近 14 天
- 最近 30 天

### 2. 點擊查詢

選擇時間範圍後，點擊「🔍 查詢」按鈕重新載入數據

### 3. 切換報表視圖

使用頁面中的標籤切換不同的統計視圖：
- **按工序與工作中心統計**：查看各 SPEC 和 WORKCENTER 的 WIP 分布
- **按產品線統計**：查看各產品線的 WIP 分布（包含匯總和明細）

---

## 查詢邏輯

### 數據範圍

- 使用 `TXNDATE >= TRUNC(SYSDATE) - N` 查詢最近 N 天的數據
- 自動排除已完成或已取消的批次 (`STATUS NOT IN (8, 128)`)
- 只查詢有效的數據（非 NULL）

### SQL 查詢示例

#### 按 SPEC 和 WORKCENTER 統計

```sql
SELECT
    SPECNAME,
    WORKCENTERNAME,
    COUNT(DISTINCT CONTAINERNAME) as LOT_COUNT,
    SUM(QTY) as TOTAL_QTY,
    SUM(QTY2) as TOTAL_QTY2
FROM DW_MES_WIP
WHERE TXNDATE >= TRUNC(SYSDATE) - 7
  AND STATUS NOT IN (8, 128)
  AND SPECNAME IS NOT NULL
  AND WORKCENTERNAME IS NOT NULL
GROUP BY SPECNAME, WORKCENTERNAME
ORDER BY SPECNAME, WORKCENTERNAME
```

#### 按產品線統計

```sql
SELECT
    PRODUCTLINENAME_LEF,
    SPECNAME,
    WORKCENTERNAME,
    COUNT(DISTINCT CONTAINERNAME) as LOT_COUNT,
    SUM(QTY) as TOTAL_QTY,
    SUM(QTY2) as TOTAL_QTY2
FROM DW_MES_WIP
WHERE TXNDATE >= TRUNC(SYSDATE) - 7
  AND STATUS NOT IN (8, 128)
  AND PRODUCTLINENAME_LEF IS NOT NULL
GROUP BY PRODUCTLINENAME_LEF, SPECNAME, WORKCENTERNAME
ORDER BY PRODUCTLINENAME_LEF, SPECNAME, WORKCENTERNAME
```

---

## API 接口

如需程式化調用，可使用以下 API：

### 1. WIP 總覽統計
```
GET /api/wip/summary?days=7
```

**響應**:
```json
{
  "success": true,
  "data": {
    "total_lot_count": 1234,
    "total_qty": 567890,
    "total_qty2": 123456,
    "spec_count": 45,
    "workcenter_count": 23,
    "product_line_count": 12
  }
}
```

### 2. 按 SPEC 和 WORKCENTER 統計
```
GET /api/wip/by_spec_workcenter?days=7
```

**響應**:
```json
{
  "success": true,
  "data": [
    {
      "SPECNAME": "SMT",
      "WORKCENTERNAME": "SMT-LINE1",
      "LOT_COUNT": 50,
      "TOTAL_QTY": 12500,
      "TOTAL_QTY2": 2500
    }
  ],
  "count": 100
}
```

### 3. 按產品線統計
```
GET /api/wip/by_product_line?days=7
```

**響應**:
```json
{
  "success": true,
  "data": [...],
  "summary": [
    {
      "PRODUCTLINENAME_LEF": "產品線A",
      "LOT_COUNT": 150,
      "TOTAL_QTY": 37500,
      "TOTAL_QTY2": 7500
    }
  ],
  "count": 200
}
```

---

## 注意事項

### 1. 性能考量

- 查詢使用 `TXNDATE` 欄位進行時間範圍過濾
- 建議查詢範圍不超過 30 天
- 大數據量查詢可能需要等待幾秒鐘

### 2. 數據即時性

- 數據來自 DW_MES_WIP 表
- 根據 `TXNDATE` 欄位判斷數據更新時間
- 如需最新數據，建議選擇「最近 1 天」或「最近 3 天」

### 3. 狀態過濾

系統自動排除以下狀態的批次：
- `STATUS = 8`: 已完成
- `STATUS = 128`: 已取消

---

## 常見問題

### Q1: 為什麼查詢結果為空？

**可能原因**：
1. 選擇的時間範圍內沒有數據
2. 所有批次都已完成或取消
3. 數據庫連接問題

**解決方法**：
1. 嘗試擴大時間範圍（例如選擇「最近 30 天」）
2. 檢查數據庫連接狀態

### Q2: 數字顯示為 "-" 是什麼意思？

表示該欄位的值為 NULL 或查詢失敗。

### Q3: 如何匯出數據？

目前版本不支援匯出功能，但您可以：
1. 直接使用 API 接口獲取 JSON 格式數據
2. 從瀏覽器複製表格內容到 Excel

### Q4: 可以同時運行多個報表嗎？

可以，但需要使用不同的端口：
- 數據查詢工具: http://localhost:5000
- WIP 報表: http://localhost:5000

---

## 後續擴展

可以考慮增加的功能：
- [ ] Excel 匯出功能
- [ ] 圖表可視化（餅圖、柱狀圖）
- [ ] 更多篩選條件（產品、工單號等）
- [ ] Hold 批次統計
- [ ] 在站時間分析

---

**版本**: 1.0
**建立日期**: 2026-01-14


