# Hold Detail 設計文件

## 頁面架構

### URL 路徑
```
/hold-detail?reason=<hold_reason>&hold_type=<quality|non-quality>
```

### 頁面布局

```
┌─────────────────────────────────────────────────────────────────────────────┐
│  ← 返回 WIP Overview     Hold Detail: <Hold Reason Name>                   │
├─────────────────────────────────────────────────────────────────────────────┤
│  ┌─────────┐ ┌─────────┐ ┌─────────────┐ ┌─────────────┐ ┌─────────────┐   │
│  │Total    │ │Total    │ │平均當站滯留  │ │最久當站滯留  │ │ 影響站群     │   │
│  │Lots     │ │QTY      │ │             │ │             │ │             │   │
│  │   128   │ │  25600  │ │    2.3天    │ │    15天     │ │     8       │   │
│  └─────────┘ └─────────┘ └─────────────┘ └─────────────┘ └─────────────┘   │
├─────────────────────────────────────────────────────────────────────────────┤
│  當站滯留天數分佈 (Age at Current Station)                                   │
│  ┌──────────────┐ ┌──────────────┐ ┌──────────────┐ ┌──────────────┐       │
│  │ 0-1天        │ │ 1-3天        │ │ 3-7天        │ │ 7+天         │       │
│  │ Lots: 45     │ │ Lots: 38     │ │ Lots: 30     │ │ Lots: 15     │       │
│  │ QTY: 9000    │ │ QTY: 7600    │ │ QTY: 6000    │ │ QTY: 3000    │       │
│  │ 35.2%        │ │ 29.7%        │ │ 23.4%        │ │ 11.7%        │       │
│  └──────────────┘ └──────────────┘ └──────────────┘ └──────────────┘       │
├─────────────────────────────────────────────────────────────────────────────┤
│  ┌───────────────────────────────┐ ┌───────────────────────────────┐       │
│  │ By Workcenter                 │ │ By Package                     │       │
│  ├───────────────────────────────┤ ├───────────────────────────────┤       │
│  │ Workcenter   Lots  QTY     %  │ │ Package      Lots  QTY     %  │       │
│  │ DA            45  9000  35.2% │ │ DIP-B         50 10000  39.1% │       │
│  │ WB            38  7600  29.7% │ │ QFN           35  7000  27.3% │       │
│  │ MOLD          30  6000  23.4% │ │ BGA           28  5600  21.9% │       │
│  │ ...           ..   ...   ...  │ │ ...           ..   ...   ...  │       │
│  └───────────────────────────────┘ └───────────────────────────────┘       │
├─────────────────────────────────────────────────────────────────────────────┤
│  Lot Details                                    篩選: Workcenter=DA [清除] │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │ LOTID   WORKORDER   QTY  Package  Workcenter  Spec  Age  Hold By Dept│   │
│  │ L001    WO123       200  DIP-B    DA          S01   2.3  EMP01   QC  │   │
│  │ L002    WO124       200  QFN      DA          S02   1.5  EMP02   PE  │   │
│  │ ...                                                                  │   │
│  └─────────────────────────────────────────────────────────────────────┘   │
│  顯示 1-50 / 128                                      < 1 2 3 ... >        │
└─────────────────────────────────────────────────────────────────────────────┘
```

## 後端 API 設計

### 1. Hold Detail Summary API

**端點**: `GET /api/wip/hold-detail/summary`

**參數**:
- `reason` (required): Hold Reason 名稱
- `hold_type` (optional): `quality` 或 `non-quality`

**回應**:
```json
{
  "totalLots": 128,
  "totalQty": 25600,
  "avgAge": 2.3,
  "maxAge": 15,
  "workcenterCount": 8
}
```

### 2. Hold Detail Distribution API

**端點**: `GET /api/wip/hold-detail/distribution`

**參數**:
- `reason` (required): Hold Reason 名稱
- `hold_type` (optional): `quality` 或 `non-quality`

**回應**:
```json
{
  "byWorkcenter": [
    {"name": "DA", "lots": 45, "qty": 9000, "percentage": 35.2},
    {"name": "WB", "lots": 38, "qty": 7600, "percentage": 29.7}
  ],
  "byPackage": [
    {"name": "DIP-B", "lots": 50, "qty": 10000, "percentage": 39.1},
    {"name": "QFN", "lots": 35, "qty": 7000, "percentage": 27.3}
  ],
  "byAge": [
    {"range": "0-1", "label": "0-1天", "lots": 45, "qty": 9000, "percentage": 35.2},
    {"range": "1-3", "label": "1-3天", "lots": 38, "qty": 7600, "percentage": 29.7},
    {"range": "3-7", "label": "3-7天", "lots": 30, "qty": 6000, "percentage": 23.4},
    {"range": "7+", "label": "7+天", "lots": 15, "qty": 3000, "percentage": 11.7}
  ]
}
```

### 3. Hold Detail Lots API

**端點**: `GET /api/wip/hold-detail/lots`

**參數**:
- `reason` (required): Hold Reason 名稱
- `hold_type` (optional): `quality` 或 `non-quality`
- `workcenter` (optional): 篩選特定站群
- `package` (optional): 篩選特定封裝
- `age_range` (optional): `0-1`, `1-3`, `3-7`, `7+`
- `page` (optional, default: 1): 頁碼
- `per_page` (optional, default: 50): 每頁筆數

**回應**:
```json
{
  "lots": [
    {
      "lotId": "L001",
      "workorder": "WO123",
      "qty": 200,
      "package": "DIP-B",
      "workcenter": "DA",
      "spec": "S01",
      "age": 2.3,
      "holdBy": "EMP01",
      "dept": "QC"
    }
  ],
  "pagination": {
    "page": 1,
    "perPage": 50,
    "total": 128,
    "totalPages": 3
  },
  "filters": {
    "workcenter": "DA",
    "package": null,
    "ageRange": null
  }
}
```

## 前端實作

### 資料載入流程

1. 頁面載入時，同時呼叫 Summary API 和 Distribution API
2. 根據 Distribution API 結果渲染分佈卡片和表格
3. 預設載入第一頁 Lot Details
4. 點擊分佈項目時，更新篩選參數並重新載入 Lot Details

### 篩選邏輯

```javascript
// 篩選狀態
let currentFilters = {
    workcenter: null,
    package: null,
    ageRange: null
};

// 點擊篩選
function applyFilter(type, value) {
    // 如果點擊同一個篩選值，則取消篩選
    if (currentFilters[type] === value) {
        currentFilters[type] = null;
    } else {
        currentFilters[type] = value;
    }
    loadLotDetails(1); // 重新載入第一頁
    updateFilterIndicator();
}

// 清除所有篩選
function clearFilters() {
    currentFilters = { workcenter: null, package: null, ageRange: null };
    loadLotDetails(1);
    updateFilterIndicator();
}
```

### CSS 樣式規範

1. **數值顯示**：不帶單位文字（如 pcs），純數字
2. **表格欄位**：
   - 文字欄位：左對齊
   - 數值欄位：右對齊
   - 欄位間隔：16px gap
3. **卡片樣式**：
   - 可點擊卡片顯示 cursor: pointer
   - 選中狀態使用高亮邊框
4. **分佈表格欄位寬度**：
   - 名稱欄位：flex-grow
   - Lots 欄位：80px
   - QTY 欄位：100px
   - 百分比欄位：80px

### Age Distribution 分段定義

| 範圍 | Label | SQL 條件 |
|------|-------|----------|
| 0-1天 | 0-1天 | AgeByDays >= 0 AND AgeByDays < 1 |
| 1-3天 | 1-3天 | AgeByDays >= 1 AND AgeByDays < 3 |
| 3-7天 | 3-7天 | AgeByDays >= 3 AND AgeByDays < 7 |
| 7+天 | 7+天 | AgeByDays >= 7 |

## 資料庫查詢

### 基礎條件

```python
base_conditions = """
    WORKORDER IS NOT NULL
    AND STATUS = 'Active'
    AND CURRENTHOLDCOUNT > 0
    AND HOLDREASONNAME = :reason
"""
```

### Summary 查詢

```sql
SELECT
    COUNT(*) AS total_lots,
    SUM(QTY) AS total_qty,
    ROUND(AVG(AGEBYDAYS), 1) AS avg_age,
    MAX(AGEBYDAYS) AS max_age,
    COUNT(DISTINCT WORKCENTER_GROUP) AS workcenter_count
FROM DWH.DW_PJ_LOT_V
WHERE {base_conditions}
```

### Distribution 查詢

```sql
-- By Workcenter
SELECT
    WORKCENTER_GROUP AS name,
    COUNT(*) AS lots,
    SUM(QTY) AS qty
FROM DWH.DW_PJ_LOT_V
WHERE {base_conditions}
GROUP BY WORKCENTER_GROUP
ORDER BY lots DESC

-- By Package
SELECT
    PRODUCTLINENAME AS name,
    COUNT(*) AS lots,
    SUM(QTY) AS qty
FROM DWH.DW_PJ_LOT_V
WHERE {base_conditions}
GROUP BY PRODUCTLINENAME
ORDER BY lots DESC

-- By Age
SELECT
    CASE
        WHEN AGEBYDAYS < 1 THEN '0-1'
        WHEN AGEBYDAYS < 3 THEN '1-3'
        WHEN AGEBYDAYS < 7 THEN '3-7'
        ELSE '7+'
    END AS age_range,
    COUNT(*) AS lots,
    SUM(QTY) AS qty
FROM DWH.DW_PJ_LOT_V
WHERE {base_conditions}
GROUP BY CASE
    WHEN AGEBYDAYS < 1 THEN '0-1'
    WHEN AGEBYDAYS < 3 THEN '1-3'
    WHEN AGEBYDAYS < 7 THEN '3-7'
    ELSE '7+'
END
```

## 檔案結構

```
src/mes_dashboard/
├── routes/
│   ├── wip_routes.py          # 修改：新增 hold-detail 路由
│   └── hold_routes.py         # 新增：Hold Detail API 路由
├── services/
│   └── wip_service.py         # 修改：新增 hold detail 查詢函數
└── templates/
    ├── wip_overview.html      # 修改：Hold Summary 加入連結
    └── hold_detail.html       # 新增：Hold Detail 頁面
```
