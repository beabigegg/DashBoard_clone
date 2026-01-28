# Design: WIP Exclude NULL Workorder

## Overview

在 `_build_base_conditions()` 函數中新增預設條件，排除 `WORKORDER` 為 NULL 的紀錄（原物料）。

## Technical Approach

### 修改位置

**File**: `src/mes_dashboard/services/wip_service.py`
**Function**: `_build_base_conditions()`
**Line**: 44-48 區域

### 實作方式

在 `conditions` 列表建立後，立即加入 NULL WORKORDER 排除條件：

```python
def _build_base_conditions(
    include_dummy: bool = False,
    workorder: Optional[str] = None,
    lotid: Optional[str] = None
) -> List[str]:
    conditions = []

    # Exclude raw materials (NULL WORKORDER)
    conditions.append("WORKORDER IS NOT NULL")

    # DUMMY exclusion (default behavior)
    if not include_dummy:
        conditions.append("LOTID NOT LIKE '%DUMMY%'")

    # ... rest unchanged
```

### 條件順序

將 `WORKORDER IS NOT NULL` 放在條件列表最前面，因為：
1. 這是最基本的篩選條件，應最先套用
2. 可能有助於 SQL 優化器先過濾大量資料

### 影響的查詢

此條件會自動套用到所有使用 `_build_base_conditions()` 的函數：

| 函數 | API Endpoint |
|------|--------------|
| `get_wip_summary()` | `/api/wip/overview/summary` |
| `get_wip_matrix()` | `/api/wip/overview/matrix` |
| `get_wip_hold_summary()` | `/api/wip/overview/hold` |
| `get_wip_detail()` | `/api/wip/detail/<workcenter>` |
| `get_workcenters()` | `/api/wip/meta/workcenters` |
| `get_packages()` | `/api/wip/meta/packages` |
| `search_workorders()` | `/api/wip/meta/search?type=workorder` |
| `search_lot_ids()` | `/api/wip/meta/search?type=lotid` |

## Data Considerations

### 原物料判斷邏輯

- `WORKORDER IS NULL` → 原物料，不納入 WIP 統計
- `WORKORDER IS NOT NULL` → 生產中的 Lot，納入 WIP 統計

### 無需額外參數

不提供 `include_raw_materials` 參數，因為：
1. WIP 系統設計上就不應該顯示原物料
2. 簡化 API，避免混淆
3. 如未來需要，可再新增參數

## Testing

### 驗證方式

1. 比較修改前後的 WIP 總數
2. 確認 NULL WORKORDER 的 Lot 不再出現於：
   - Overview Summary 統計
   - Matrix 表格
   - Hold Summary 列表
   - Detail 頁面

### 預期結果

- WIP 總數會減少（排除原物料）
- 各狀態統計更準確
- 不影響現有功能和 UI
