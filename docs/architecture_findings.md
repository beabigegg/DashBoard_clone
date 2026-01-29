# MES Dashboard - Architecture Findings

本文件記錄專案開發過程中確立的架構設計、全局規範與資料處理規則。

---

## 1. 資料庫連線管理

### 連線池統一使用
所有資料庫操作必須透過 `mes_dashboard.core.database` 模組：

```python
from mes_dashboard.core.database import read_sql_df, get_engine

# 讀取資料
df = read_sql_df(sql)

# 取得 engine（若需要直接操作）
engine = get_engine()
```

### 注意事項
- **禁止**在各 service 中自行建立連線
- 連線池由 `database.py` 統一管理，避免連線洩漏
- 測試環境需在 setUp 中重置：`db._ENGINE = None`

---

## 2. 快取機制

### 全局快取 API
使用 `mes_dashboard.core.cache` 模組：

```python
from mes_dashboard.core.cache import cache_get, cache_set, make_cache_key

# 建立快取 key（支援 filters dict）
cache_key = make_cache_key("resource_history_summary", filters={
    'start_date': start_date,
    'workcenter_groups': sorted(groups) if groups else None,
})

# 讀取/寫入快取
result = cache_get(cache_key)
if result is None:
    result = query_data()
    cache_set(cache_key, result, ttl=CACHE_TTL_TREND)
```

### 快取 TTL 常數
定義於 `mes_dashboard.config.constants`：
- `CACHE_TTL_FILTER_OPTIONS`: 篩選選項（較長）
- `CACHE_TTL_TREND`: 趨勢資料（中等）
- `CACHE_TTL_REALTIME`: 即時資料（較短）

---

## 3. Filter Cache（篩選選項快取）

### 位置
`mes_dashboard.services.filter_cache`

### 用途
快取全站共用的篩選選項，避免重複查詢資料庫：

```python
from mes_dashboard.services.filter_cache import (
    get_workcenter_groups,      # 取得 workcenter group 列表
    get_workcenter_mapping,     # 取得 workcentername → group 對應
    get_workcenters_for_groups, # 根據 group 取得 workcentername 列表
    get_resource_families,      # 取得 resource family 列表
)
```

### Workcenter 對應關係
```
WORKCENTERNAME (資料庫)  →  WORKCENTER_GROUP (顯示)
焊接_DB_1                →  焊接_DB
焊接_DB_2                →  焊接_DB
成型_1                   →  成型
```

### 資料來源
- Workcenter Groups: `DW_PJ_LOT_V` (WORKCENTER_GROUP, WORKCENTERSEQUENCE_GROUP)
- Resource Families: `DW_MES_RESOURCE` (RESOURCEFAMILYNAME)

---

## 4. 前端全局組件

### Toast 通知
定義於 `static/js/toast.js`，透過 `_base.html` 載入：

```javascript
// 正確用法
Toast.info('訊息');
Toast.success('成功');
Toast.warning('警告');
Toast.error('錯誤');
Toast.loading('載入中...');

// 錯誤用法（不存在）
MESToast.warning('...');  // ❌ 錯誤
```

### MesApi（HTTP 請求）
定義於 `static/js/api.js`，提供統一的 API 呼叫介面：

```javascript
const result = await MesApi.get('/api/endpoint', { timeout: 30000 });
if (result.success) {
    // 處理資料
} else {
    Toast.error(result.error);
}
```

---

## 5. 資料表預篩選規則

### 設備類型篩選
定義於 `mes_dashboard.config.constants.EQUIPMENT_TYPE_FILTER`：

```sql
-- 只查詢特定設備類型
r.EQUIPMENTTYPE IN ('主要設備', '輔助設備')
```

### 排除條件
```python
# 排除的地點
EXCLUDED_LOCATIONS = ['TEST', 'LAB', ...]

# 排除的資產狀態
EXCLUDED_ASSET_STATUSES = ['報廢', '停用', ...]
```

### SQL 範例
```python
# 建立篩選條件
location_filter = _build_location_filter('r')
# → AND (r.LOCATIONNAME IS NULL OR r.LOCATIONNAME NOT IN ('TEST', 'LAB'))

asset_status_filter = _build_asset_status_filter('r')
# → AND r.PJ_ASSETSSTATUS NOT IN ('報廢', '停用')
```

---

## 6. 資料庫欄位對應

### DW_MES_RESOURCE
| 常見錯誤 | 正確欄位名 |
|---------|-----------|
| ASSETSTATUS | PJ_ASSETSSTATUS（雙 S）|
| LOCATION | LOCATIONNAME |
| ISPRODUCTION | PJ_ISPRODUCTION |
| ISKEY | PJ_ISKEY |
| ISMONITOR | PJ_ISMONITOR |

### DW_MES_RESOURCESTATUS_SHIFT
| 欄位 | 說明 |
|-----|------|
| HISTORYID | 對應 DW_MES_RESOURCE.RESOURCEID |
| TXNDATE | 交易日期 |
| OLDSTATUSNAME | E10 狀態 (PRD, SBY, UDT, SDT, EGT, NST) |
| HOURS | 該狀態時數 |

### DW_PJ_LOT_V
| 欄位 | 說明 |
|-----|------|
| WORKCENTERNAME | 站點名稱（細分）|
| WORKCENTER_GROUP | 站點群組（顯示用）|
| WORKCENTERSEQUENCE_GROUP | 群組排序 |

---

## 7. E10 狀態定義

| 狀態 | 說明 | 計入 OU% |
|-----|------|---------|
| PRD | Production（生產）| 是（分子）|
| SBY | Standby（待機）| 是（分母）|
| UDT | Unscheduled Downtime（非計畫停機）| 是（分母）|
| SDT | Scheduled Downtime（計畫停機）| 是（分母）|
| EGT | Engineering Time（工程時間）| 是（分母）|
| NST | Non-Scheduled Time（非排程時間）| 否 |

### OU% 計算公式
```
OU% = PRD / (PRD + SBY + UDT + SDT + EGT) × 100
```

---

## 8. 平行查詢

### ThreadPoolExecutor
對於多個獨立查詢，使用平行執行提升效能：

```python
from concurrent.futures import ThreadPoolExecutor, as_completed

with ThreadPoolExecutor(max_workers=4) as executor:
    futures = {
        executor.submit(read_sql_df, kpi_sql): 'kpi',
        executor.submit(read_sql_df, trend_sql): 'trend',
        executor.submit(read_sql_df, heatmap_sql): 'heatmap',
        executor.submit(read_sql_df, comparison_sql): 'comparison',
    }
    for future in as_completed(futures):
        query_name = futures[future]
        results[query_name] = future.result()
```

### 注意事項
- Mock 測試時不能使用 `side_effect` 列表（順序不可預測）
- 應使用函式判斷 SQL 內容來回傳對應的 mock 資料

---

## 9. Oracle SQL 優化

### CTE MATERIALIZE Hint
防止 Oracle 優化器將 CTE inline 多次執行：

```sql
WITH shift_data AS (
    SELECT /*+ MATERIALIZE */ HISTORYID, TXNDATE, OLDSTATUSNAME, HOURS
    FROM DW_MES_RESOURCESTATUS_SHIFT
    WHERE TXNDATE >= TO_DATE('2024-01-01', 'YYYY-MM-DD')
      AND TXNDATE < TO_DATE('2024-01-07', 'YYYY-MM-DD') + 1
)
SELECT ...
```

### 日期範圍查詢
```sql
-- 包含 end_date 當天
WHERE TXNDATE >= TO_DATE('{start_date}', 'YYYY-MM-DD')
  AND TXNDATE < TO_DATE('{end_date}', 'YYYY-MM-DD') + 1
```

---

## 10. 前端資料限制

### 明細資料上限
為避免瀏覽器記憶體問題，明細查詢有筆數限制：

```python
MAX_DETAIL_RECORDS = 5000

if total > MAX_DETAIL_RECORDS:
    df = df.head(MAX_DETAIL_RECORDS)
    truncated = True
```

前端顯示警告：
```javascript
if (result.truncated) {
    Toast.warning(`資料超過 ${result.max_records} 筆，請使用篩選條件縮小範圍。`);
}
```

---

## 11. JavaScript 注意事項

### Array.reverse() 原地修改
```javascript
// 錯誤 - 原地修改陣列
const arr = [1, 2, 3];
arr.reverse();  // arr 被修改為 [3, 2, 1]

// 正確 - 建立新陣列
const reversed = arr.slice().reverse();  // arr 不變
// 或
const reversed = [...arr].reverse();
```

---

## 12. 測試規範

### 測試檔案結構
```
tests/
├── test_*_service.py      # 單元測試（service layer）
├── test_*_routes.py       # 整合測試（API endpoints）
└── e2e/
    └── test_*_e2e.py      # 端對端測試（完整流程）
```

### 測試前重置
```python
def setUp(self):
    db._ENGINE = None  # 重置連線池
    self.app = create_app('testing')
```

### 執行測試
```bash
# 單一模組
pytest tests/test_resource_history_service.py -v

# 全部相關測試
pytest tests/test_resource_history_*.py tests/e2e/test_resource_history_e2e.py -v
```
