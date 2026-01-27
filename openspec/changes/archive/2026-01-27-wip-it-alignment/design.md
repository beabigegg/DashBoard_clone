## Technical Decisions

### Decision: WIP Status 計算位置

**選擇**: 在 SQL 查詢中計算 WIP Status，而非在 Python 程式碼中計算

**原因**:
- 與 IT Power BI 的實作方式一致
- 減少資料傳輸量（資料庫端聚合）
- 效能更佳，可直接利用資料庫的 CASE WHEN 語法

**SQL 實作**:
```sql
CASE WHEN EQUIPMENTCOUNT > 0 THEN 'RUN'
     WHEN CURRENTHOLDCOUNT > 0 THEN 'HOLD'
     ELSE 'QUEUE' END AS WIP_STATUS
```

### Decision: API 回傳格式

**選擇**: 使用 camelCase 作為 API 欄位名稱

**原因**:
- 符合 JavaScript/前端慣例
- 便於前端直接使用

**欄位對應表（部分）**:
| View 欄位 | API 欄位 |
|-----------|----------|
| LOTID | lotId |
| WORKORDER | workOrderId |
| QTY | qtyPcs |
| EQUIPMENTCOUNT | equipmentCount |
| CURRENTHOLDCOUNT | holdCount |
| (計算) | wipStatus |

### Decision: Summary API 結構

**選擇**: 在現有 Summary API 新增 `byWipStatus` 欄位，而非建立新的 API

**原因**:
- 減少前端 API 呼叫次數
- 保持向後相容（原有欄位保留）
- 資料來自同一次查詢，效能較佳

**結構**:
```python
{
    "totalLots": int,
    "totalQtyPcs": int,
    "byWipStatus": {
        "run": {"lots": int, "qtyPcs": int},
        "queue": {"lots": int, "qtyPcs": int},
        "hold": {"lots": int, "qtyPcs": int}
    },
    "dataUpdateDate": str
}
```

### Decision: 移除 Hold KPI 卡片

**選擇**: 移除獨立的 Hold Lots / Hold QTY 卡片

**原因**:
- 避免資訊重複（HOLD 資訊已在 WIP Status 卡片顯示）
- 簡化 UI 層級
- 符合新的三態分類設計

---

## Implementation Approach

### 1. 後端修改（wip_service.py）

#### 1.1 修改 `get_wip_summary()` 函數

新增 WIP Status 分組統計 SQL：

```python
def get_wip_summary(...) -> Optional[Dict[str, Any]]:
    sql = f"""
        SELECT
            COUNT(*) as TOTAL_LOTS,
            SUM(QTY) as TOTAL_QTY_PCS,

            -- RUN: EQUIPMENTCOUNT > 0
            SUM(CASE WHEN EQUIPMENTCOUNT > 0 THEN 1 ELSE 0 END) as RUN_LOTS,
            SUM(CASE WHEN EQUIPMENTCOUNT > 0 THEN QTY ELSE 0 END) as RUN_QTY_PCS,

            -- HOLD: EQUIPMENTCOUNT = 0 AND CURRENTHOLDCOUNT > 0
            SUM(CASE WHEN EQUIPMENTCOUNT = 0 AND CURRENTHOLDCOUNT > 0 THEN 1 ELSE 0 END) as HOLD_LOTS,
            SUM(CASE WHEN EQUIPMENTCOUNT = 0 AND CURRENTHOLDCOUNT > 0 THEN QTY ELSE 0 END) as HOLD_QTY_PCS,

            -- QUEUE: EQUIPMENTCOUNT = 0 AND CURRENTHOLDCOUNT = 0
            SUM(CASE WHEN EQUIPMENTCOUNT = 0 AND CURRENTHOLDCOUNT = 0 THEN 1 ELSE 0 END) as QUEUE_LOTS,
            SUM(CASE WHEN EQUIPMENTCOUNT = 0 AND CURRENTHOLDCOUNT = 0 THEN QTY ELSE 0 END) as QUEUE_QTY_PCS,

            MAX(SYS_DATE) as DATA_UPDATE_DATE
        FROM {WIP_VIEW}
        {where_clause}
    """
```

#### 1.2 回傳格式調整

```python
return {
    'totalLots': int(row['TOTAL_LOTS'] or 0),
    'totalQtyPcs': int(row['TOTAL_QTY_PCS'] or 0),
    'byWipStatus': {
        'run': {
            'lots': int(row['RUN_LOTS'] or 0),
            'qtyPcs': int(row['RUN_QTY_PCS'] or 0)
        },
        'queue': {
            'lots': int(row['QUEUE_LOTS'] or 0),
            'qtyPcs': int(row['QUEUE_QTY_PCS'] or 0)
        },
        'hold': {
            'lots': int(row['HOLD_LOTS'] or 0),
            'qtyPcs': int(row['HOLD_QTY_PCS'] or 0)
        }
    },
    'dataUpdateDate': str(row['DATA_UPDATE_DATE']) if row['DATA_UPDATE_DATE'] else None
}
```

### 2. 前端修改（wip_overview.html）

#### 2.1 HTML 結構修改

```html
<!-- Summary Cards (修改為 2 個) -->
<div class="summary-row">
    <div class="summary-card">
        <div class="summary-label">Total Lots</div>
        <div class="summary-value" id="totalLots">-</div>
    </div>
    <div class="summary-card">
        <div class="summary-label">Total QTY</div>
        <div class="summary-value" id="totalQty">-</div>
    </div>
</div>

<!-- WIP Status Cards (新增) -->
<div class="wip-status-row">
    <div class="wip-status-card run">
        <div class="status-header"><span class="dot"></span>RUN</div>
        <div class="status-values">
            <span class="lots" id="runLots">-</span>
            <span class="qty" id="runQty">-</span>
        </div>
    </div>
    <!-- QUEUE, HOLD 卡片類似 -->
</div>
```

#### 2.2 CSS 樣式新增

```css
.wip-status-row {
    display: grid;
    grid-template-columns: repeat(3, 1fr);
    gap: 14px;
    margin-bottom: 16px;
}

.wip-status-card {
    border-radius: 10px;
    padding: 12px 20px;
    border: 2px solid;
}

.wip-status-card.run {
    background: #F0FDF4;
    border-color: #22C55E;
}

.wip-status-card.queue {
    background: #FFFBEB;
    border-color: #F59E0B;
}

.wip-status-card.hold {
    background: #FEF2F2;
    border-color: #EF4444;
}

.status-values span {
    font-size: 24px;
    font-weight: 700;
}
```

#### 2.3 JavaScript 渲染函數修改

```javascript
function renderSummary(data) {
    updateElementWithTransition('totalLots', data.totalLots);
    updateElementWithTransition('totalQty', data.totalQtyPcs);

    // WIP Status
    const ws = data.byWipStatus;
    updateElementWithTransition('runLots', ws.run.lots + ' lots');
    updateElementWithTransition('runQty', formatNumber(ws.run.qtyPcs) + ' pcs');
    updateElementWithTransition('queueLots', ws.queue.lots + ' lots');
    updateElementWithTransition('queueQty', formatNumber(ws.queue.qtyPcs) + ' pcs');
    updateElementWithTransition('holdLots', ws.hold.lots + ' lots');
    updateElementWithTransition('holdQty', formatNumber(ws.hold.qtyPcs) + ' pcs');

    // Update time
    if (data.dataUpdateDate) {
        document.getElementById('lastUpdate').textContent =
            `Last Update: ${data.dataUpdateDate}`;
    }
}
```

---

## Data Flow

```
┌──────────────────────────────────────────────────────────────────────────┐
│                           資料流程圖                                      │
├──────────────────────────────────────────────────────────────────────────┤
│                                                                          │
│  DWH.DW_PJ_LOT_V                                                        │
│       │                                                                  │
│       │ SQL Query (含 WIP Status CASE WHEN)                             │
│       ▼                                                                  │
│  ┌─────────────────────────────────────────────────────────────────┐    │
│  │  wip_service.py::get_wip_summary()                              │    │
│  │  - 查詢 TOTAL_LOTS, TOTAL_QTY_PCS                               │    │
│  │  - 查詢 RUN/QUEUE/HOLD_LOTS 和 _QTY_PCS                         │    │
│  │  - 組裝 byWipStatus 結構                                        │    │
│  └─────────────────────────────────────────────────────────────────┘    │
│       │                                                                  │
│       │ JSON Response                                                   │
│       ▼                                                                  │
│  ┌─────────────────────────────────────────────────────────────────┐    │
│  │  wip_routes.py::api_overview_summary()                          │    │
│  │  - 回傳 {success: true, data: {...}}                            │    │
│  └─────────────────────────────────────────────────────────────────┘    │
│       │                                                                  │
│       │ HTTP GET /api/wip/overview/summary                              │
│       ▼                                                                  │
│  ┌─────────────────────────────────────────────────────────────────┐    │
│  │  wip_overview.html::renderSummary()                             │    │
│  │  - 更新 Total Lots / Total QTY 卡片                             │    │
│  │  - 更新 RUN / QUEUE / HOLD 狀態卡片                             │    │
│  └─────────────────────────────────────────────────────────────────┘    │
│                                                                          │
└──────────────────────────────────────────────────────────────────────────┘
```

---

## Testing Strategy

### 後端測試

1. **單元測試**: 驗證 `get_wip_summary()` 回傳正確的 `byWipStatus` 結構
2. **SQL 測試**: 驗證 WIP Status CASE WHEN 邏輯正確
3. **API 測試**: 驗證 `/api/wip/overview/summary` 回傳格式

### 前端測試

1. **視覺測試**: 確認 WIP Status 卡片顯示正確顏色
2. **數據測試**: 確認數字與 API 回傳一致
3. **響應式測試**: 確認不同螢幕寬度下的卡片排列
