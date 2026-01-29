# 提案：DW_MES_RESOURCE 全表快取至 Redis

## 背景

目前系統多處功能需要查詢 `DW_MES_RESOURCE` 表來取得設備主檔資料，主要用於：
1. 篩選器下拉選項（型號、站點、部門等）
2. 設備資訊 JOIN 查詢

現況問題：
- 每次載入篩選器都需查詢 Oracle
- 多個功能重複查詢相同資料
- 使用者等待時間較長

## 目標

將 `DW_MES_RESOURCE`（套用全域篩選後）**全表全欄位**快取至 Redis，實現：
1. **快速篩選器載入** - 使用者開啟頁面時無需等待 Oracle 查詢
2. **集中管理** - 統一資料來源，確保各功能使用一致的設備清單
3. **降低 Oracle 負載** - 減少重複查詢
4. **擴展彈性** - 全欄位快取，未來新功能可直接使用

## 資料規格

### 篩選條件（與現有一致）

```sql
WHERE ((OBJECTCATEGORY = 'ASSEMBLY' AND OBJECTTYPE = 'ASSEMBLY')
    OR (OBJECTCATEGORY = 'WAFERSORT' AND OBJECTTYPE = 'WAFERSORT'))
  AND (LOCATIONNAME IS NULL OR LOCATIONNAME NOT IN (
       'ATEC', 'F區', 'F區焊接站', '報廢', '實驗室',
       '山東', '成型站_F區', '焊接F區', '無錫', '熒茂'))
  AND (PJ_ASSETSSTATUS IS NULL OR PJ_ASSETSSTATUS NOT IN ('Disapproved'))
```

### 快取欄位（全表 78 欄位）

```
SELECT * FROM DW_MES_RESOURCE WHERE <篩選條件>
```

完整欄位清單：

| 類別 | 欄位 |
|------|------|
| **識別** | RESOURCEID, RESOURCENAME, DESCRIPTION |
| **分類** | OBJECTCATEGORY, OBJECTTYPE, EQUIPMENTTYPE, RESOURCEFAMILYID, RESOURCEFAMILYNAME |
| **組織** | FACTORYID, LOCATIONID, LOCATIONNAME, WORKCENTERNAME, PJ_WORKCENTERID, PJ_WORKCENTER_ID, PJ_DEPARTMENT |
| **供應商** | VENDORID, VENDORNAME, VENDORMODEL, VENDORSERIALNUMBER, PJ_ERPVENDORID |
| **狀態旗標** | PJ_ASSETSSTATUS, PJ_ISPRODUCTION, PJ_ISKEY, PJ_ISMONITOR, PJ_ISAUEQUIPMENT |
| **自動化** | AUTOMATIONPLANID, AUTOMATIONPLANNAME, PJ_AUTOMATIONLEVEL, PJ_AUEQUIPMENTGROUPID |
| **製程** | RECIPEID, BOMID, BOMBASEID, PACKAGEGROUPID, TOOLPLANID |
| **SPC** | SPCSETUPID, PJ_SPCSETUP, USESPCMATRIX, PJ_VERIFYSPCRESULT |
| **檢查** | PJ_CHECKBYHOUR, PJ_CHECKBYIDLETIME, PJ_CHECKBYLOT, PJ_CHECKBYPRODUCT, PJ_CHECKBYTYPE, PJ_CHECKBYWORKORDER |
| **產品** | PJ_DATECODE1, PJ_DATECODE2, PJ_FINISHEDPRODUCT, PJ_WAFERPRODUCT, PJ_PROCESSSPEC, PJ_WORKORDER |
| **容量** | LOTCOUNT, MAXLOTS, MAXUNITS, MULTILOTSFLAG |
| **其他** | CONTAINERID, DOCUMENTSETID, MACHINEGROUPID, MAINTENANCECLASSID, NOTES, RESOURCECOMMENTS, PJ_OWNER, PJ_EMPLOYEE, PJ_LOTID, PJ_CONTROLLENGTH |
| **關聯** | PARENTRESOURCEID, PRODUCTIONSTATUSID, STATUSMODELID, SETUPACCESSID, PJ_SETUPACCESSID, PARAMLISTID, SUBEQUIPMENTLOGICALID, TRAININGREQGROUPID, UOMID, WIPMSGDEFMGRID |
| **審計** | CREATIONDATE, CREATIONUSERNAME, LASTCHANGEDATE, USERID |

### 資料量估算

| 項目 | 數值 |
|------|------|
| 原始總筆數 | 90,620 |
| 篩選後估計 | ~3,000 - 5,000 |
| 欄位數 | 78 |
| 最大單筆大小 | ~6,045 bytes |
| 平均單筆大小 (含 JSON) | ~3,600 bytes |
| **總快取大小** | **~10 - 18 MB** |

### 同步策略

| 項目 | 設定 |
|------|------|
| 同步週期 | 每 4 小時 |
| 初始載入 | 應用啟動時 |
| 版本識別 | `MAX(LASTCHANGEDATE)` |
| 失效策略 | 查詢失敗時 fallback 到 Oracle |

### Redis Key 結構

```
{prefix}:resource:data          - 完整資料 (JSON array)
{prefix}:resource:meta:version  - MAX(LASTCHANGEDATE)
{prefix}:resource:meta:updated  - 同步時間 (ISO 8601)
{prefix}:resource:meta:count    - 記錄筆數
```

---

## 影響盤點

### 1. 設備歷史績效 (Resource History)

**檔案**: `resource_history_service.py`, `resource_history_routes.py`

| 功能 | 現況 | 改動後 |
|------|------|--------|
| 型號篩選器 (families) | `filter_cache.get_resource_families()` 查 Oracle | 改從 Redis 取 |
| 站點篩選器 (workcenter_groups) | `filter_cache.get_workcenter_groups()` 查 DW_PJ_LOT_V | 不變 (來源不同) |
| `/api/resource/history/options` | 呼叫 filter_cache | 改用新的 resource_cache |

**前端**: `resource_history.html`
- `familiesDropdown` - 型號多選下拉

### 2. 機台狀態報表 (Resource Status)

**檔案**: `resource_service.py`, `resource_routes.py`

| 功能 | 現況 | 改動後 |
|------|------|------|
| `query_resource_filter_options()` | 直接查 Oracle + JOIN status | 改從 Redis 取維度欄位 |
| `/resource/filter_options` | 查 Oracle，結果快取 60 秒 | 改用 Redis 快取 |

**前端**: `resource.html`
- 站點篩選 (workcenter)
- 狀態篩選 (status) - **不變**，需即時資料
- 型號篩選 (family)
- 部門篩選 (department)

### 3. Filter Cache 模組

**檔案**: `filter_cache.py`

| 功能 | 現況 | 改動後 |
|------|------|--------|
| `get_resource_families()` | 獨立查 DW_MES_RESOURCE | 廢棄，改用 resource_cache |
| `_load_resource_families()` | 內部載入函數 | 廢棄 |
| `get_workcenter_groups()` | 查 DW_PJ_LOT_V | 不變 |
| `get_workcenter_mapping()` | 查 DW_PJ_LOT_V | 不變 |

### 4. Dashboard Service

**檔案**: `dashboard_service.py`

| 功能 | 現況 | 改動後 |
|------|------|--------|
| UDT/SDT drill-down | JOIN DW_MES_RESOURCE | 考慮改用 Python 端 JOIN |

---

## 新增模組設計

### resource_cache.py (新增)

```python
"""Resource Cache - DW_MES_RESOURCE 全表快取模組

全表快取套用全域篩選後的設備主檔資料至 Redis。
"""

# ============================================================
# 主要查詢 API
# ============================================================

def get_all_resources() -> List[Dict]:
    """取得所有快取中的設備資料（全欄位）"""

def get_resource_by_id(resource_id: str) -> Optional[Dict]:
    """依 RESOURCEID 取得單筆設備資料"""

def get_resources_by_ids(resource_ids: List[str]) -> List[Dict]:
    """依 RESOURCEID 清單批次取得設備資料"""

def get_resources_by_filter(
    workcenters: List[str] = None,
    families: List[str] = None,
    departments: List[str] = None,
    locations: List[str] = None,
    is_production: bool = None,
    is_key: bool = None,
    is_monitor: bool = None,
) -> List[Dict]:
    """依條件篩選設備資料（在 Python 端篩選）"""

# ============================================================
# 篩選器選項 API（取代現有 filter_cache 功能）
# ============================================================

def get_distinct_values(column: str) -> List[str]:
    """取得指定欄位的唯一值清單（排序後）

    常用欄位:
    - RESOURCEFAMILYNAME (型號)
    - WORKCENTERNAME (站點)
    - PJ_DEPARTMENT (部門)
    - LOCATIONNAME (區域)
    - VENDORNAME (供應商)
    - PJ_ASSETSSTATUS (資產狀態)
    """

def get_resource_families() -> List[str]:
    """取得型號清單（便捷方法）"""
    return get_distinct_values('RESOURCEFAMILYNAME')

def get_workcenters() -> List[str]:
    """取得站點清單（便捷方法）"""
    return get_distinct_values('WORKCENTERNAME')

def get_departments() -> List[str]:
    """取得部門清單（便捷方法）"""
    return get_distinct_values('PJ_DEPARTMENT')

# ============================================================
# 快取管理 API
# ============================================================

def get_cache_status() -> Dict:
    """取得快取狀態

    Returns:
        {
            'enabled': True,
            'loaded': True,
            'count': 3500,
            'version': '2026-01-29 10:30:00',  # MAX(LASTCHANGEDATE)
            'updated_at': '2026-01-29 14:00:00',
            'size_bytes': 12582912,
        }
    """

def refresh_cache(force: bool = False) -> bool:
    """手動刷新快取

    Args:
        force: 強制刷新，忽略版本檢查
    """

def init_cache():
    """初始化快取（應用啟動時呼叫）"""

# ============================================================
# 內部函數
# ============================================================

def _load_from_oracle() -> pd.DataFrame:
    """從 Oracle 載入全表資料（套用全域篩選）"""

def _sync_to_redis(df: pd.DataFrame) -> bool:
    """同步至 Redis（使用 pipeline 確保原子性）"""

def _get_version_from_oracle() -> Optional[str]:
    """取得 Oracle 資料版本（MAX(LASTCHANGEDATE)）"""

def _get_version_from_redis() -> Optional[str]:
    """取得 Redis 快取版本"""
```

### Redis Key 結構

```
{prefix}:resource:data           - 完整資料 (JSON array, 全欄位)
{prefix}:resource:index:id       - ID 索引 (Hash: RESOURCEID -> row_index)
{prefix}:resource:meta:version   - 資料版本 MAX(LASTCHANGEDATE)
{prefix}:resource:meta:updated   - 同步時間 (ISO 8601)
{prefix}:resource:meta:count     - 記錄筆數
```

### 背景同步任務

整合至現有 `CacheUpdater`，新增 resource 同步邏輯：

```python
class CacheUpdater:
    def __init__(self):
        self.wip_check_interval = 600        # 10 分鐘 (現有 WIP)
        self.resource_sync_interval = 14400  # 4 小時 (新增 Resource)
        self._last_resource_sync = None

    def _check_resource_update(self):
        """檢查並同步 Resource 快取

        1. 檢查距上次同步是否超過 4 小時
        2. 比對 Oracle MAX(LASTCHANGEDATE) 與 Redis 版本
        3. 若有差異則全表同步
        """
```

### 環境變數

| 變數 | 預設值 | 說明 |
|------|--------|------|
| `RESOURCE_CACHE_ENABLED` | `true` | 是否啟用 Resource 快取 |
| `RESOURCE_SYNC_INTERVAL` | `14400` | 同步間隔（秒），預設 4 小時 |

---

## 遷移計畫

### Phase 1: 新增 resource_cache 模組
- 建立 `resource_cache.py`
- 實作 Redis 同步邏輯
- 加入背景同步任務
- 新增 health check 項目

### Phase 2: 整合設備歷史績效
- 修改 `resource_history_service.get_filter_options()`
- 更新 `/api/resource/history/options` 端點
- 測試型號篩選器

### Phase 3: 整合機台狀態報表
- 修改 `query_resource_filter_options()`
- 更新 `/resource/filter_options` 端點
- 測試所有篩選器

### Phase 4: 清理
- 移除 `filter_cache._load_resource_families()`
- 移除 `filter_cache.get_resource_families()`
- 更新文件

---

## 測試重點

1. **快取載入**
   - 應用啟動時成功載入
   - Redis 不可用時 fallback 到 Oracle

2. **篩選器功能**
   - 設備歷史績效 - 型號下拉正確顯示
   - 機台狀態報表 - 所有篩選器正確顯示

3. **同步機制**
   - 4 小時自動同步
   - 手動強制同步

4. **效能**
   - 篩選器載入時間 < 100ms
   - 記憶體使用量符合預期

---

## 風險評估

| 風險 | 影響 | 緩解措施 |
|------|------|----------|
| Redis 不可用 | 篩選器無法載入 | Fallback 到 Oracle 直查 |
| 資料不一致 | 新設備 4 小時內不顯示 | 可手動觸發同步、提供 API 強制刷新 |
| 記憶體使用 | 快取約 10-18 MB | 相較 WIP 快取（可能數十 MB）仍屬輕量 |
| 大欄位浪費 | NOTES/RESOURCECOMMENTS 最大 2000 chars | 實際使用率低，平均填充率 ~40% |

---

## 預期效益

1. **使用者體驗** - 篩選器載入從 ~500ms 降至 <100ms
2. **Oracle 負載** - 減少設備主檔查詢次數約 80%
3. **維護性** - 集中管理設備資料來源
4. **擴展性** - 未來可支援更多維度查詢

