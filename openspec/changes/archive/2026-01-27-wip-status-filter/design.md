# WIP Status Filter - 技術設計

## 架構概覽

```
┌─────────────────────────────────────────────────────────────┐
│  wip_overview.html (前端)                                    │
│  ┌─────────┐ ┌─────────┐ ┌─────────┐                        │
│  │   RUN   │ │  QUEUE  │ │  HOLD   │  ← 可點擊卡片          │
│  └────┬────┘ └────┬────┘ └────┬────┘                        │
│       │           │           │                             │
│       └───────────┼───────────┘                             │
│                   ▼                                         │
│         activeStatusFilter (state)                          │
│                   │                                         │
│                   ▼                                         │
│  GET /api/wip/overview/matrix?status={RUN|QUEUE|HOLD}       │
└─────────────────────────────────────────────────────────────┘
                    │
                    ▼
┌─────────────────────────────────────────────────────────────┐
│  wip_routes.py                                              │
│  api_overview_matrix() ← 新增 status 參數解析               │
└─────────────────────────────────────────────────────────────┘
                    │
                    ▼
┌─────────────────────────────────────────────────────────────┐
│  wip_service.py                                             │
│  get_wip_matrix(status=...) ← 新增 status 篩選邏輯          │
└─────────────────────────────────────────────────────────────┘
```

---

## 後端變更

### 1. wip_service.py - get_wip_matrix()

**新增參數**：`status: Optional[str] = None`

**SQL 條件**：
```python
# 在 _build_base_conditions 之後加入
if status:
    status_upper = status.upper()
    if status_upper == 'RUN':
        conditions.append("EQUIPMENTCOUNT > 0")
    elif status_upper == 'HOLD':
        conditions.append("EQUIPMENTCOUNT = 0 AND CURRENTHOLDCOUNT > 0")
    elif status_upper == 'QUEUE':
        conditions.append("EQUIPMENTCOUNT = 0 AND CURRENTHOLDCOUNT = 0")
```

**函數簽名變更**：
```python
def get_wip_matrix(
    include_dummy: bool = False,
    workorder: Optional[str] = None,
    lotid: Optional[str] = None,
    status: Optional[str] = None  # 新增
) -> Optional[Dict[str, Any]]:
```

### 2. wip_routes.py - api_overview_matrix()

**新增參數解析**：
```python
status = request.args.get('status', '').strip().upper() or None

# 驗證 status 值
if status and status not in ('RUN', 'QUEUE', 'HOLD'):
    return jsonify({
        'success': False,
        'error': 'Invalid status. Use RUN, QUEUE, or HOLD'
    }), 400

result = get_wip_matrix(
    include_dummy=include_dummy,
    workorder=workorder,
    lotid=lotid,
    status=status  # 新增
)
```

---

## 前端變更

### 1. 新增狀態變數

```javascript
// 在 state 物件旁邊新增
let activeStatusFilter = null;  // null | 'run' | 'queue' | 'hold'
```

### 2. 新增 CSS 樣式

```css
/* 可點擊的卡片 */
.wip-status-card {
    cursor: pointer;
    transition: all 0.2s ease;
}

.wip-status-card:hover {
    transform: translateY(-2px);
    box-shadow: 0 4px 15px rgba(0, 0, 0, 0.15);
}

/* 選中狀態 */
.wip-status-card.active {
    border-width: 3px;
    box-shadow: 0 4px 20px rgba(0, 0, 0, 0.2);
}

.wip-status-card.run.active {
    box-shadow: 0 4px 20px rgba(34, 197, 94, 0.4);
}

.wip-status-card.queue.active {
    box-shadow: 0 4px 20px rgba(245, 158, 11, 0.4);
}

.wip-status-card.hold.active {
    box-shadow: 0 4px 20px rgba(239, 68, 68, 0.4);
}

/* 篩選提示標籤 */
.filter-badge {
    display: none;
    font-size: 10px;
    padding: 2px 6px;
    border-radius: 4px;
    margin-left: 8px;
    background: rgba(0, 0, 0, 0.1);
}

.wip-status-card.active .filter-badge {
    display: inline-block;
}
```

### 3. HTML 變更

為卡片添加 `onclick` 和篩選標籤：

```html
<div class="wip-status-card run" onclick="toggleStatusFilter('run')">
    <div class="status-header">
        <span class="dot"></span>RUN
        <span class="filter-badge">FILTERED</span>
    </div>
    <div class="status-values">
        <span id="runLots">-</span>
        <span id="runQty">-</span>
    </div>
</div>
```

### 4. JavaScript 邏輯

```javascript
function toggleStatusFilter(status) {
    if (activeStatusFilter === status) {
        // 解除篩選
        activeStatusFilter = null;
    } else {
        // 套用新篩選
        activeStatusFilter = status;
    }

    // 更新卡片樣式
    updateCardStyles();

    // 重新載入 Matrix（帶篩選參數）
    loadMatrix();
}

function updateCardStyles() {
    document.querySelectorAll('.wip-status-card').forEach(card => {
        card.classList.remove('active');
    });

    if (activeStatusFilter) {
        const activeCard = document.querySelector(`.wip-status-card.${activeStatusFilter}`);
        if (activeCard) {
            activeCard.classList.add('active');
        }
    }
}

function loadMatrix() {
    const params = new URLSearchParams();

    // 現有篩選條件
    const workorder = document.getElementById('workorder').value.trim();
    const lotid = document.getElementById('lotid').value.trim();
    if (workorder) params.append('workorder', workorder);
    if (lotid) params.append('lotid', lotid);

    // 狀態篩選
    if (activeStatusFilter) {
        params.append('status', activeStatusFilter.toUpperCase());
    }

    const url = '/api/wip/overview/matrix' + (params.toString() ? '?' + params : '');

    // 顯示載入狀態
    document.getElementById('matrixContainer').innerHTML =
        '<div class="placeholder">Loading...</div>';

    fetch(url)
        .then(response => response.json())
        .then(result => {
            if (result.success) {
                renderMatrix(result.data);
            } else {
                document.getElementById('matrixContainer').innerHTML =
                    '<div class="placeholder">Error loading data</div>';
            }
        })
        .catch(error => {
            console.error('Matrix load error:', error);
            document.getElementById('matrixContainer').innerHTML =
                '<div class="placeholder">Error loading data</div>';
        });
}
```

### 5. 整合 loadAllData()

修改 `loadAllData()` 確保 Matrix 載入時考慮 `activeStatusFilter`：

```javascript
async function loadAllData(showLoading = false) {
    // ... 現有邏輯 ...

    // Matrix 改為獨立載入（支援狀態篩選）
    loadMatrix();

    // Summary 和 Hold 維持不變
    // ...
}
```

### 6. Auto-refresh 整合

確保自動刷新時保留篩選狀態：

```javascript
function startAutoRefresh() {
    refreshInterval = setInterval(() => {
        loadAllData(false);  // loadMatrix() 內部會讀取 activeStatusFilter
    }, 600000);
}
```

---

## Matrix 表格標題顯示篩選狀態

當有篩選時，更新 Matrix 標題：

```javascript
function updateMatrixTitle() {
    const titleEl = document.querySelector('.card-title');
    const baseTitle = 'Workcenter x Package Matrix (QTY)';

    if (activeStatusFilter) {
        const statusLabel = activeStatusFilter.toUpperCase();
        titleEl.textContent = `${baseTitle} - ${statusLabel} Only`;
    } else {
        titleEl.textContent = baseTitle;
    }
}
```

---

## 資料流程

### 篩選開啟流程

```
1. 使用者點擊 RUN 卡片
   │
2. toggleStatusFilter('run')
   │
3. activeStatusFilter = 'run'
   │
4. updateCardStyles() → RUN 卡片加上 .active
   │
5. loadMatrix() → GET /api/wip/overview/matrix?status=RUN
   │
6. 後端過濾 EQUIPMENTCOUNT > 0 的資料
   │
7. 前端 renderMatrix() 顯示篩選結果
```

### 篩選關閉流程

```
1. 使用者再次點擊 RUN 卡片
   │
2. toggleStatusFilter('run')
   │
3. activeStatusFilter = null（因為已是 'run'）
   │
4. updateCardStyles() → 移除所有 .active
   │
5. loadMatrix() → GET /api/wip/overview/matrix（無 status 參數）
   │
6. 後端返回全部資料
   │
7. 前端 renderMatrix() 顯示完整 Matrix
```

---

## 邊界情況

| 情況 | 處理方式 |
|------|----------|
| 篩選結果為空 | 顯示 "No data available" |
| 與 workorder/lotid 組合篩選 | 條件疊加（AND） |
| 無效的 status 參數 | API 返回 400 錯誤 |
| 自動刷新時 | 保留 activeStatusFilter 狀態 |
| 手動刷新時 | 保留 activeStatusFilter 狀態 |

---

## 測試要點

1. **基本功能**
   - 點擊 RUN → Matrix 只顯示 RUN 狀態數量
   - 點擊 QUEUE → Matrix 只顯示 QUEUE 狀態數量
   - 點擊 HOLD → Matrix 只顯示 HOLD 狀態數量
   - 再次點擊 → 恢復全部

2. **視覺回饋**
   - 選中卡片有明顯樣式變化
   - 載入時顯示 Loading 提示

3. **組合篩選**
   - 同時輸入 workorder + 點選 RUN → 兩個條件都生效

4. **自動刷新**
   - 篩選狀態在刷新後保持
