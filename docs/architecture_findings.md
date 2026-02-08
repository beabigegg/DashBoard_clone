# MES Dashboard - Architecture Findings

本文件記錄專案開發過程中確立的架構設計、全局規範與資料處理規則。

---

## 1. 資料庫連線管理

### 連線池統一使用
所有資料庫操作必須透過 `mes_dashboard.core.database` 模組：

```python
from mes_dashboard.core.database import read_sql_df, get_engine

# 讀取資料 (推薦方式)
df = read_sql_df(sql, params)

# 取得 engine（若需要直接操作）
engine = get_engine()
```

### 連線池配置 (位置: `core/database.py`)

| 參數 | 開發環境 | 生產環境 | 說明 |
|------|---------|---------|------|
| pool_size | 2 | 10 | 基礎連線數 |
| max_overflow | 3 | 20 | 額外連線數 |
| pool_timeout | 30 | 30 | 等待超時 (秒) |
| pool_recycle | 1800 | 1800 | 回收週期 (30分鐘) |
| pool_pre_ping | True | True | 使用前驗證連線 |

### Keep-Alive 機制
- 背景執行緒每 5 分鐘執行 `SELECT 1 FROM DUAL`
- 防止 NAT/防火牆斷開閒置連線
- 啟動: `start_keepalive()`，停止: `stop_keepalive()`

### 注意事項
- **禁止**在各 service 中自行建立連線
- **禁止**直接使用 `oracledb.connect()`
- 連線池由 `database.py` 統一管理，避免連線洩漏
- 測試環境需在 setUp 中重置：`db._ENGINE = None`

---

## 2. SQL 集中管理

### 目錄結構
所有 SQL 查詢放在 `src/mes_dashboard/sql/` 目錄：

```
sql/
├── loader.py              # SQL 檔案載入器 (LRU 快取)
├── builder.py             # 參數化查詢構建器
├── filters.py             # 通用篩選條件
├── dashboard/             # 儀表板 SQL
│   ├── kpi.sql
│   ├── heatmap.sql
│   └── workcenter_cards.sql
├── wip/                   # WIP SQL
│   ├── summary.sql
│   └── detail.sql
├── resource/              # 設備 SQL
│   ├── by_status.sql
│   └── detail.sql
├── resource_history/      # 歷史 SQL
└── job_query/             # 維修工單 SQL
```

### SQLLoader 使用方式

```python
from mes_dashboard.sql.loader import SQLLoader

# 載入 SQL 檔案 (自動 LRU 快取，最多 100 個)
sql = SQLLoader.load("wip/summary")

# 結構性參數替換 (用於 SQL 片段)
sql = SQLLoader.load_with_params("dashboard/kpi",
    LATEST_STATUS_SUBQUERY="...",
    WHERE_CLAUSE="...")

# 清除快取
SQLLoader.clear_cache()
```

### QueryBuilder 使用方式

```python
from mes_dashboard.sql.builder import QueryBuilder

builder = QueryBuilder()

# 添加條件 (自動參數化，防 SQL 注入)
builder.add_param_condition("STATUS", "PRD")
builder.add_in_condition("STATUS", ["PRD", "SBY"])
builder.add_not_in_condition("HOLD_REASON", exclude_list)
builder.add_like_condition("LOTID", user_input, position="both")
builder.add_or_like_conditions(["COL1", "COL2"], [val1, val2])
builder.add_is_null("COLUMN")
builder.add_is_not_null("COLUMN")
builder.add_condition("FIXED_CONDITION = 1")  # 固定條件

# 構建 WHERE 子句
where_clause, params = builder.build_where_only()

# 替換佔位符並執行
sql = sql.replace("{{ WHERE_CLAUSE }}", where_clause)
df = read_sql_df(sql, params)
```

### 佔位符規範

| 類型 | 語法 | 用途 | 安全性 |
|------|------|------|--------|
| 結構性 | `{{ PLACEHOLDER }}` | 靜態 SQL 片段 | 僅限預定義值 |
| 參數 | `:param_name` | 動態用戶輸入 | Oracle bind variables |

### Oracle IN 子句限制
Oracle IN 子句上限 1000 個值，需分批處理：

```python
BATCH_SIZE = 1000

# 參考 job_query_service.py 的 _build_resource_filter()
```

---

## 3. 快取機制

### 多層快取架構

```
請求 → 進程級快取 (30 秒 TTL)
     → Redis 快取 (可配置 TTL)
     → Oracle 資料庫
```

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

```python
CACHE_TTL_DEFAULT = 60           # 1 分鐘
CACHE_TTL_FILTER_OPTIONS = 600   # 10 分鐘
CACHE_TTL_PIVOT_COLUMNS = 300    # 5 分鐘
CACHE_TTL_KPI = 60               # 1 分鐘
CACHE_TTL_TREND = 300            # 5 分鐘
```

### Redis 快取配置
環境變數：
```
REDIS_ENABLED=true
REDIS_URL=redis://localhost:6379/0
REDIS_KEY_PREFIX=mes_wip
```

### 專用快取服務

| 服務 | 位置 | 用途 |
|------|------|------|
| WIP 快取更新器 | `core/cache_updater.py` | 背景線程自動更新 WIP 數據 |
| 資源快取 | `services/resource_cache.py` | DW_MES_RESOURCE 表快取 (4 小時同步) |
| 設備狀態快取 | `services/realtime_equipment_cache.py` | 設備實時狀態 (5 分鐘同步) |
| Filter 快取 | `services/filter_cache.py` | 篩選選項快取 |

---

## 4. Filter Cache（篩選選項快取）

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

## 5. 熔斷器 (Circuit Breaker)

### 位置
`mes_dashboard.core.circuit_breaker`

### 狀態機制

```
CLOSED (正常)
    ↓ 失敗達到閾值
OPEN (故障，拒絕請求)
    ↓ 等待 recovery_timeout
HALF_OPEN (測試恢復)
    ↓ 成功 → CLOSED / 失敗 → OPEN
```

### 配置 (環境變數)

```
CIRCUIT_BREAKER_ENABLED=true
CIRCUIT_BREAKER_FAILURE_THRESHOLD=5      # 最少失敗次數
CIRCUIT_BREAKER_FAILURE_RATE=0.5         # 失敗率閾值 (0.0-1.0)
CIRCUIT_BREAKER_RECOVERY_TIMEOUT=30      # OPEN 狀態等待秒數
CIRCUIT_BREAKER_WINDOW_SIZE=10           # 滑動窗口大小
```

### 使用方式
熔斷器已整合在 `read_sql_df()` 中，自動：
- 檢查是否允許請求
- 記錄成功/失敗
- 狀態轉移

### 狀態查詢
```python
from mes_dashboard.core.circuit_breaker import get_database_circuit_breaker

cb = get_database_circuit_breaker()
status = cb.get_status()
# status.state, status.failure_count, status.success_count, status.failure_rate
```

---

## 6. 統一 API 響應格式

### 位置
`mes_dashboard.core.response`

### 響應格式

```python
# 成功響應
{
    "success": True,
    "data": {...},
    "meta": {"timestamp": "2024-02-04T10:30:45.123456"}
}

# 錯誤響應
{
    "success": False,
    "error": {
        "code": "DB_CONNECTION_FAILED",
        "message": "資料庫連線失敗，請稍後再試",
        "details": "ORA-12541"  # 僅開發模式
    },
    "meta": {"timestamp": "..."}
}
```

### 錯誤代碼

| 代碼 | HTTP | 說明 |
|------|------|------|
| DB_CONNECTION_FAILED | 503 | 資料庫連線失敗 |
| DB_QUERY_TIMEOUT | 504 | 查詢逾時 |
| DB_QUERY_ERROR | 500 | 查詢執行錯誤 |
| SERVICE_UNAVAILABLE | 503 | 服務不可用 |
| CIRCUIT_BREAKER_OPEN | 503 | 熔斷器開啟 |
| VALIDATION_ERROR | 400 | 驗證失敗 |
| UNAUTHORIZED | 401 | 未授權 |
| FORBIDDEN | 403 | 禁止訪問 |
| NOT_FOUND | 404 | 不存在 |
| TOO_MANY_REQUESTS | 429 | 過多請求 |
| INTERNAL_ERROR | 500 | 內部錯誤 |

### 便利函數

```python
from mes_dashboard.core.response import (
    success_response,
    validation_error,      # 400
    unauthorized_error,    # 401
    forbidden_error,       # 403
    not_found_error,       # 404
    db_connection_error,   # 503
    internal_error,        # 500
)
```

---

## 7. 認證與授權機制

### 認證服務
位置: `mes_dashboard.services.auth_service`

#### LDAP 認證 (生產環境)
```python
from mes_dashboard.services.auth_service import authenticate

user = authenticate(username, password)
# 返回: {username, displayName, mail, department}
```

#### 本地認證 (開發環境)
```
LOCAL_AUTH_ENABLED=true
LOCAL_AUTH_USERNAME=admin
LOCAL_AUTH_PASSWORD=password
```

### Session 管理
```python
# 登入後存入 session
session["admin"] = {
    "username": user.get("username"),
    "displayName": user.get("displayName"),
    "mail": user.get("mail"),
    "department": user.get("department"),
    "login_time": datetime.now().isoformat()
}

# Session 配置
SESSION_COOKIE_SECURE = True     # HTTPS only (生產)
SESSION_COOKIE_HTTPONLY = True   # 防止 JS 訪問
SESSION_COOKIE_SAMESITE = 'Lax'  # CSRF 防護
PERMANENT_SESSION_LIFETIME = 28800  # 8 小時
```

### 權限檢查
位置: `mes_dashboard.core.permissions`

```python
from mes_dashboard.core.permissions import is_admin_logged_in, admin_required

# 檢查登入狀態
if is_admin_logged_in():
    ...

# 裝飾器保護路由
@admin_required
def admin_only_view():
    ...
```

### 登入速率限制
- 單 IP 每 5 分鐘最多 5 次嘗試
- 位置: `routes/auth_routes.py`

---

## 8. 頁面狀態管理

### 位置
- 服務: `mes_dashboard.services.page_registry`
- 數據: `data/page_status.json`

### 狀態定義

| 狀態 | 說明 |
|------|------|
| `released` | 所有用戶可訪問 |
| `dev` | 僅管理員可訪問 |
| `None` | 未註冊，由 Flask 路由控制 |

### 數據格式
```json
{
  "pages": [
    {"route": "/wip-overview", "name": "WIP 即時概況", "status": "released"},
    {"route": "/tables", "name": "表格總覽", "status": "dev"}
  ],
  "api_public": true
}
```

### API

```python
from mes_dashboard.services.page_registry import (
    get_page_status,    # 取得頁面狀態
    set_page_status,    # 設定頁面狀態
    is_api_public,      # API 是否公開
    get_all_pages,      # 取得所有頁面
)
```

### 權限檢查 (自動)
在 `app.py` 的 `@app.before_request` 中自動執行：
- dev 頁面 + 非管理員 → 403

---

## 9. 日誌系統

### 雙層日誌架構

| 層級 | 目標 | 用途 |
|------|------|------|
| 控制台 (stderr) | Gunicorn 捕獲 | 即時監控 |
| SQLite | 管理員儀表板 | 歷史查詢 |

### 配置 (環境變數)
```
LOG_STORE_ENABLED=true
LOG_SQLITE_PATH=logs/admin_logs.sqlite
LOG_SQLITE_RETENTION_DAYS=7
LOG_SQLITE_MAX_ROWS=100000
```

### 日誌記錄規範

```python
import logging
logger = logging.getLogger('mes_dashboard')

logger.debug("詳細調試資訊")
logger.info("一般操作記錄")
logger.warning("警告但可繼續")
logger.error("錯誤需要關注", exc_info=True)  # 包含堆棧
```

### SQLite 日誌查詢
位置: `mes_dashboard.core.log_store`

```python
from mes_dashboard.core.log_store import get_log_store

store = get_log_store()
logs = store.query_logs(
    level="ERROR",
    limit=100,
    offset=0,
    search="keyword"
)
```

---

## 10. 健康檢查

### 端點

| 端點 | 認證 | 說明 |
|------|------|------|
| `/health` | 無需 | 基本健康檢查 |
| `/health/deep` | 需管理員 | 詳細指標 |

### 基本檢查項目
- 資料庫連線 (`SELECT 1 FROM DUAL`)
- Redis 連線 (`PING`)
- 各快取狀態

### 詳細檢查項目 (deep)
- 資料庫延遲 (毫秒)
- 連線池狀態 (size, checked_out, overflow)
- 快取新鮮度
- 熔斷器狀態
- 查詢性能指標 (P50/P95/P99)

### 狀態判定
- `200 OK` (healthy/degraded): DB 正常
- `503 Unavailable` (unhealthy): DB 故障

---

## 11. API 路由結構 (Blueprint)

### Blueprint 列表

| Blueprint | URL 前綴 | 檔案 |
|-----------|---------|------|
| wip | `/api/wip` | `wip_routes.py` |
| resource | `/api/resource` | `resource_routes.py` |
| dashboard | `/api/dashboard` | `dashboard_routes.py` |
| excel_query | `/api/excel-query` | `excel_query_routes.py` |
| hold | `/api/hold` | `hold_routes.py` |
| resource_history | `/api/resource-history` | `resource_history_routes.py` |
| job_query | `/api/job-query` | `job_query_routes.py` |
| admin | `/admin` | `admin_routes.py` |
| auth | `/admin` | `auth_routes.py` |
| health | `/` | `health_routes.py` |

### 路由註冊
位置: `routes/__init__.py` 的 `register_routes(app)`

---

## 12. 前端全局組件

### Toast 通知
定義於 `static/js/toast.js`，透過 `_base.html` 載入：

```javascript
// 正確用法
Toast.info('訊息');
Toast.success('成功');
Toast.warning('警告');
Toast.error('錯誤', { retry: () => loadData() });

const id = Toast.loading('載入中...');
Toast.update(id, { message: '完成!' });
Toast.dismiss(id);

// 錯誤用法（不存在）
MESToast.warning('...');  // ❌ 錯誤
```

### 自動消失時間
- info: 3000ms
- success: 2000ms
- warning: 5000ms
- error: 永久（需手動關閉）
- loading: 永久

### MesApi（HTTP 請求）
定義於 `static/js/mes-api.js`：

```javascript
// GET 請求
const data = await MesApi.get('/api/wip/summary', {
    params: { page: 1 },
    timeout: 60000,
    retries: 5,
    signal: abortController.signal,
    silent: true  // 禁用 toast 通知
});

// POST 請求
const data = await MesApi.post('/api/query_table', {
    table_name: 'TABLE_A',
    filters: {...}
});
```

### MesApi 特性
- 自動重試 (3 次，指數退避: 1s, 2s, 4s)
- 自動 Toast 通知
- 請求 ID 追蹤
- AbortSignal 支援
- 4xx 不重試，5xx 重試

---

## 13. 資料表預篩選規則

### 設備類型篩選
定義於 `mes_dashboard.config.constants.EQUIPMENT_TYPE_FILTER`：

```sql
((OBJECTCATEGORY = 'ASSEMBLY' AND OBJECTTYPE = 'ASSEMBLY')
 OR (OBJECTCATEGORY = 'WAFERSORT' AND OBJECTTYPE = 'WAFERSORT'))
```

### 排除條件
```python
# 排除的地點
EXCLUDED_LOCATIONS = [
    'ATEC', 'F區', 'F區焊接站', '報廢', '實驗室',
    '山東', '成型站_F區', '焊接F區', '無錫', '熒茂'
]

# 排除的資產狀態
EXCLUDED_ASSET_STATUSES = ['Disapproved']
```

### CommonFilters 使用
位置: `mes_dashboard.sql.filters`

```python
from mes_dashboard.sql.filters import CommonFilters

# 添加標準篩選
CommonFilters.add_location_exclusion(builder, 'r')
CommonFilters.add_asset_status_exclusion(builder, 'r')
CommonFilters.add_wip_base_filters(builder, filters)
CommonFilters.add_equipment_filter(builder, filters)
```

---

## 14. 資料庫欄位對應

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

## 15. E10 狀態定義

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

### 狀態顯示名稱
```python
STATUS_DISPLAY_NAMES = {
    'PRD': '生產中',
    'SBY': '待機',
    'UDT': '非計畫停機',
    'SDT': '計畫停機',
    'EGT': '工程時間',
    'NST': '未排單',
}
```

---

## 16. 配置管理

### 環境變數 (.env)

#### 資料庫
```
DB_HOST=<your_database_host>
DB_PORT=1521
DB_SERVICE=<your_service_name>
DB_USER=<your_username>
DB_PASSWORD=<your_password>
DB_POOL_SIZE=5
DB_MAX_OVERFLOW=10
```

> 實際值請參考 `.env` 或 `.env.example`

#### Flask
```
FLASK_ENV=production
FLASK_DEBUG=0
SECRET_KEY=your_secret_key
SESSION_LIFETIME=28800
```

#### 認證
```
LDAP_API_URL=<your_ldap_api_url>
ADMIN_EMAILS=<admin_email_list>
LOCAL_AUTH_ENABLED=false
```

#### Gunicorn
```
GUNICORN_BIND=0.0.0.0:8080
GUNICORN_WORKERS=4
GUNICORN_THREADS=8
```

#### 快取
```
REDIS_ENABLED=true
REDIS_URL=redis://localhost:6379/0
CACHE_CHECK_INTERVAL=600
RESOURCE_CACHE_ENABLED=true
RESOURCE_SYNC_INTERVAL=14400
```

#### 熔斷器
```
CIRCUIT_BREAKER_ENABLED=true
CIRCUIT_BREAKER_FAILURE_THRESHOLD=5
CIRCUIT_BREAKER_FAILURE_RATE=0.5
CIRCUIT_BREAKER_RECOVERY_TIMEOUT=30
```

#### 日誌
```
LOG_STORE_ENABLED=true
LOG_SQLITE_PATH=logs/admin_logs.sqlite
LOG_SQLITE_RETENTION_DAYS=7
```

### 環境配置類
位置: `mes_dashboard.config.settings`

```python
class DevelopmentConfig(Config):
    DEBUG = True
    DB_POOL_SIZE = 2

class ProductionConfig(Config):
    DEBUG = False
    DB_POOL_SIZE = 10

class TestingConfig(Config):
    TESTING = True
    DB_POOL_SIZE = 1
```

---

## 17. 平行查詢

### ThreadPoolExecutor
對於多個獨立查詢，使用平行執行提升效能：

```python
from concurrent.futures import ThreadPoolExecutor, as_completed

with ThreadPoolExecutor(max_workers=4) as executor:
    futures = {
        executor.submit(read_sql_df, kpi_sql): 'kpi',
        executor.submit(read_sql_df, trend_sql): 'trend',
        executor.submit(read_sql_df, heatmap_sql): 'heatmap',
    }
    for future in as_completed(futures):
        query_name = futures[future]
        results[query_name] = future.result()
```

### 注意事項
- Mock 測試時不能使用 `side_effect` 列表（順序不可預測）
- 應使用函式判斷 SQL 內容來回傳對應的 mock 資料

---

## 18. Oracle SQL 優化

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
WHERE TXNDATE >= TO_DATE(:start_date, 'YYYY-MM-DD')
  AND TXNDATE < TO_DATE(:end_date, 'YYYY-MM-DD') + 1
```

### 慢查詢警告
- 閾值: 1 秒 (警告)，5 秒 (`SLOW_QUERY_THRESHOLD`)
- 自動記錄到日誌

---

## 19. 前端資料限制

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

## 20. JavaScript 注意事項

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

## 21. 測試規範

### 測試檔案結構
```
tests/
├── conftest.py              # pytest fixtures
├── test_*_service.py        # 單元測試（service layer）
├── test_*_routes.py         # 整合測試（API endpoints）
├── e2e/
│   └── test_*_e2e.py        # 端對端測試（完整流程）
└── stress/
    └── test_*.py            # 壓力測試
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

# 覆蓋率報告
pytest tests/ --cov=mes_dashboard
```

---

## 22. 錯誤處理模式

### 三層錯誤處理

```python
# 1. 路由層 - 驗證錯誤
@bp.route('/api/query')
def query():
    if not request.json.get('table_name'):
        return validation_error("table_name 為必填")

# 2. 服務層 - 業務錯誤 (優雅降級)
def get_wip_summary(filters):
    try:
        df = query_wip(filters)
        if df.empty:
            return None
        return process_data(df)
    except Exception as exc:
        logger.error(f"WIP query failed: {exc}")
        return None

# 3. 核心層 - 基礎設施錯誤
def read_sql_df(sql, params):
    if not circuit_breaker.allow_request():
        raise RuntimeError("Circuit breaker open")
```

### 全局錯誤處理
位置: `app.py` 的 `_register_error_handlers()`

- 401 → `unauthorized_error()`
- 403 → `forbidden_error()`
- 404 → JSON (API) 或 HTML (頁面)
- 500 → `internal_error()`
- Exception → 通用處理

---

## 參考檔案索引

| 功能 | 檔案位置 |
|------|---------|
| SQL 載入 | `src/mes_dashboard/sql/loader.py` |
| 查詢構建 | `src/mes_dashboard/sql/builder.py` |
| 通用篩選 | `src/mes_dashboard/sql/filters.py` |
| 資料庫操作 | `src/mes_dashboard/core/database.py` |
| 快取 | `src/mes_dashboard/core/cache.py` |
| 熔斷器 | `src/mes_dashboard/core/circuit_breaker.py` |
| API 響應 | `src/mes_dashboard/core/response.py` |
| 權限檢查 | `src/mes_dashboard/core/permissions.py` |
| 日誌存儲 | `src/mes_dashboard/core/log_store.py` |
| 配置類 | `src/mes_dashboard/config/settings.py` |
| 常量定義 | `src/mes_dashboard/config/constants.py` |
| 認證服務 | `src/mes_dashboard/services/auth_service.py` |
| 頁面狀態 | `src/mes_dashboard/services/page_registry.py` |
| Filter 快取 | `src/mes_dashboard/services/filter_cache.py` |
| 資源快取 | `src/mes_dashboard/services/resource_cache.py` |
| API 客戶端 | `src/mes_dashboard/static/js/mes-api.js` |
| Toast 系統 | `src/mes_dashboard/static/js/toast.js` |
