# Technical Design

## Decision: Hold 分類邏輯位置

**選擇**: 後端 Python 層處理分類

**原因**:
- 單一真相來源：分類邏輯只在後端維護，前端直接使用
- 效能：SQL 層直接分類，減少資料傳輸
- 維護性：未來新增/修改 Hold Reason 只需改後端

**位置**: `src/mes_dashboard/services/wip_service.py`

---

## Decision: 非品質異常 Hold Reason 定義

**選擇**: Python Set 常數

**實作**:
```python
# wip_service.py 頂部定義
NON_QUALITY_HOLD_REASONS = {
    'IQC檢驗(久存品驗證)(QC)',
    '大中/安波幅50pcs樣品留樣(PD)',
    '工程驗證(PE)',
    '工程驗證(RD)',
    '指定機台生產',
    '特殊需求(X-Ray全檢)',
    '特殊需求管控',
    '第一次量產QC品質確認(QC)',
    '需綁尾數(PD)',
    '樣品需求留存打樣(樣品)',
    '盤點(收線)需求',
}

def is_quality_hold(reason: str) -> bool:
    """判斷是否為品質異常 Hold"""
    return reason not in NON_QUALITY_HOLD_REASONS
```

**原因**:
- Set 查詢 O(1) 效能
- 易於維護和擴充
- 明確的函數名稱 `is_quality_hold()`

---

## API Changes

### 1. Summary API (`/api/wip/overview/summary`)

**現有回應**:
```json
{
  "byWipStatus": {
    "hold": { "lots": 150, "qtyPcs": 5000 }
  }
}
```

**新增回應欄位**:
```json
{
  "byWipStatus": {
    "hold": { "lots": 150, "qtyPcs": 5000 },
    "qualityHold": { "lots": 80, "qtyPcs": 3000 },
    "nonQualityHold": { "lots": 70, "qtyPcs": 2000 }
  }
}
```

**SQL 修改** (`get_wip_summary`):
```sql
-- 新增品質異常統計
SUM(CASE WHEN COALESCE(EQUIPMENTCOUNT, 0) = 0
          AND COALESCE(CURRENTHOLDCOUNT, 0) > 0
          AND HOLDREASONNAME NOT IN (...non-quality list...)
          THEN 1 ELSE 0 END) as QUALITY_HOLD_LOTS,
-- 新增非品質異常統計
SUM(CASE WHEN COALESCE(EQUIPMENTCOUNT, 0) = 0
          AND COALESCE(CURRENTHOLDCOUNT, 0) > 0
          AND HOLDREASONNAME IN (...non-quality list...)
          THEN 1 ELSE 0 END) as NON_QUALITY_HOLD_LOTS,
```

---

### 2. Matrix API (`/api/wip/overview/matrix`)

**新增參數**: `hold_type` (optional)

| 參數值 | 行為 |
|--------|------|
| (空) | 顯示所有 Hold（現有行為） |
| `quality` | 只顯示品質異常 Hold |
| `non-quality` | 只顯示非品質異常 Hold |

**SQL 修改** (`get_wip_matrix`):
```python
if status == 'HOLD':
    if hold_type == 'quality':
        conditions.append(f"HOLDREASONNAME NOT IN ({non_quality_list})")
    elif hold_type == 'non-quality':
        conditions.append(f"HOLDREASONNAME IN ({non_quality_list})")
```

---

### 3. Hold Summary API (`/api/wip/overview/hold`)

**現有回應**:
```json
{
  "items": [
    { "reason": "品管異常", "lots": 50, "qty": 2000 }
  ]
}
```

**新增回應欄位**:
```json
{
  "items": [
    { "reason": "品管異常", "lots": 50, "qty": 2000, "holdType": "quality" },
    { "reason": "工程驗證(PE)", "lots": 30, "qty": 1000, "holdType": "non-quality" }
  ]
}
```

**Python 修改** (`get_wip_hold_summary`):
```python
for _, row in df.iterrows():
    items.append({
        'reason': row['REASON'],
        'lots': int(row['LOTS'] or 0),
        'qty': int(row['QTY'] or 0),
        'holdType': 'quality' if is_quality_hold(row['REASON']) else 'non-quality'
    })
```

---

### 4. Detail API (`/api/wip/detail/<workcenter>`)

**新增參數**: `hold_type` (optional)

| 參數值 | 行為 |
|--------|------|
| (空) | 顯示所有 Hold（現有行為） |
| `quality` | 只顯示品質異常 Hold lots |
| `non-quality` | 只顯示非品質異常 Hold lots |

**Summary 回應新增**:
```json
{
  "summary": {
    "holdLots": 150,
    "qualityHoldLots": 80,
    "nonQualityHoldLots": 70
  }
}
```

---

## Frontend Changes

### WIP Overview 卡片配置

**現有**: 3 張卡片 (RUN, QUEUE, HOLD)

**改為**: 4 張卡片 (RUN, QUEUE, 品質異常 Hold, 非品質異常 Hold)

**Grid 調整**:
```css
.wip-status-row {
    grid-template-columns: repeat(4, 1fr);  /* 從 3 改為 4 */
}

@media (max-width: 1200px) {
    .wip-status-row {
        grid-template-columns: repeat(2, 1fr);  /* 維持 2 欄 */
    }
}
```

**卡片樣式**:

| 卡片 | 背景色 | 邊框色 | 文字色 |
|------|--------|--------|--------|
| RUN | #F0FDF4 | #22C55E | #166534 |
| QUEUE | #FFFBEB | #F59E0B | #92400E |
| 品質異常 Hold | #FEF2F2 | #EF4444 | #991B1B |
| 非品質異常 Hold | #FFF7ED | #F97316 | #9A3412 |

**卡片 HTML 結構**:
```html
<div class="wip-status-card quality-hold" onclick="toggleStatusFilter('quality-hold')">
    <div class="status-header"><span class="dot"></span>品質異常</div>
    <div class="status-values">
        <span id="qualityHoldLots">-</span>
        <span id="qualityHoldQty">-</span>
    </div>
</div>
<div class="wip-status-card non-quality-hold" onclick="toggleStatusFilter('non-quality-hold')">
    <div class="status-header"><span class="dot"></span>非品質異常</div>
    <div class="status-values">
        <span id="nonQualityHoldLots">-</span>
        <span id="nonQualityHoldQty">-</span>
    </div>
</div>
```

---

### WIP Detail 卡片配置

**現有**: 4 張卡片 (Total, RUN, QUEUE, HOLD)

**改為**: 5 張卡片 (Total, RUN, QUEUE, 品質異常 Hold, 非品質異常 Hold)

**Grid 調整**:
```css
.summary-row {
    grid-template-columns: repeat(5, 1fr);  /* 從 4 改為 5 */
}

@media (max-width: 1400px) {
    .summary-row {
        grid-template-columns: repeat(3, 1fr);  /* 3 欄 wrap */
    }
}

@media (max-width: 768px) {
    .summary-row {
        grid-template-columns: 1fr;  /* 單欄 */
    }
}
```

---

### Hold Summary 表格改版

**現有**:
| Hold Reason | Lots | QTY |
|-------------|------|-----|
| 品管異常 | 50 | 2000 |

**改為**:
| Hold Reason | Lots | QTY |
|-------------|------|-----|
| [品質] 品管異常 | 50 | 2000 |
| [非品質] 工程驗證(PE) | 30 | 1000 |

**樣式**:
```css
.hold-type-badge {
    display: inline-block;
    padding: 2px 6px;
    border-radius: 4px;
    font-size: 11px;
    font-weight: 600;
    margin-right: 6px;
}

.hold-type-badge.quality {
    background: #FEE2E2;
    color: #991B1B;
}

.hold-type-badge.non-quality {
    background: #FFEDD5;
    color: #9A3412;
}
```

**Render 邏輯**:
```javascript
function renderHold(data) {
    data.items.forEach(item => {
        const badgeClass = item.holdType === 'quality' ? 'quality' : 'non-quality';
        const badgeText = item.holdType === 'quality' ? '品質' : '非品質';
        html += `<td><span class="hold-type-badge ${badgeClass}">${badgeText}</span>${item.reason}</td>`;
    });
}
```

---

### 狀態篩選邏輯

**現有狀態** (`activeStatusFilter`):
```javascript
// 可能值: null | 'run' | 'queue' | 'hold'
```

**改為**:
```javascript
// 可能值: null | 'run' | 'queue' | 'quality-hold' | 'non-quality-hold'
```

**toggleStatusFilter 修改**:
```javascript
function toggleStatusFilter(status) {
    if (activeStatusFilter === status) {
        activeStatusFilter = null;
    } else {
        activeStatusFilter = status;
    }
    updateCardStyles();
    updateMatrixTitle();
    loadMatrixOnly();
}
```

**fetchMatrix 修改**:
```javascript
async function fetchMatrix(signal = null) {
    const params = buildQueryParams();

    if (activeStatusFilter) {
        if (activeStatusFilter === 'quality-hold') {
            params.status = 'HOLD';
            params.hold_type = 'quality';
        } else if (activeStatusFilter === 'non-quality-hold') {
            params.status = 'HOLD';
            params.hold_type = 'non-quality';
        } else {
            params.status = activeStatusFilter.toUpperCase();
        }
    }
    // ...
}
```

---

## 向後相容性

| 項目 | 相容性 |
|------|--------|
| API 回應格式 | ✓ 新增欄位，現有欄位不變 |
| API 參數 | ✓ 新增 `hold_type`，現有參數不變 |
| URL 結構 | ✓ 不變 |
| CSS class | ✓ 新增 class，現有不變 |

---

## 測試要點

1. **分類正確性**: 驗證 11 個非品質異常 Reason 正確分類
2. **統計一致性**: `qualityHold + nonQualityHold = hold`
3. **篩選功能**: 點擊卡片正確篩選 Matrix/Table
4. **UI 響應式**: 4/5 張卡片在不同螢幕寬度正確排列
5. **Hold Summary**: 標籤顯示正確
