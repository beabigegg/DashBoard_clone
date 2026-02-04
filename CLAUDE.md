# MES Dashboard 開發指南

> 此文檔為 AI 開發助手的專案開發規範，確保後續開發保持一致性。

## 專案概述

MES Dashboard 是一個**製造執行系統儀表板**，用於即時監控在製品 (WIP)、設備狀態、生產效率等 MES/ERP 數據。

- **技術棧**: Flask 3.0 + SQLAlchemy 2.0 + Oracle (oracledb) + Redis + Jinja2 + Vue 3
- **Python 版本**: 3.9+（推薦 3.11）
- **部署**: Gunicorn + Systemd

---

## 開始任務前

1. **閱讀架構文檔**: 查看 `docs/architecture_findings.md` 了解:
   - 資料庫連線管理模式
   - 快取機制和 TTL 常量
   - Filter cache (workcenter/family) 使用方式
   - 前端全局組件 (Toast, MesApi)
   - 數據表篩選規則和欄位映射
   - E10 狀態定義和 OU% 計算
   - 測試慣例

2. **修改後更新文檔**: 如果修改了以下模式，需更新 `docs/architecture_findings.md`:
   - 資料庫連線或連線池方式
   - 快取策略或 TTL 值
   - 全局前端組件使用
   - 數據表欄位名稱或篩選規則
   - 新的共用工具或服務
   - 測試慣例或設置模式

---

## 目錄結構

```
/home/egg/Project/DashBoard/
├── src/mes_dashboard/          # 主應用程式
│   ├── config/                 # 配置管理
│   │   ├── settings.py        # Flask 環境配置類
│   │   ├── database.py        # 資料庫連線配置
│   │   ├── constants.py       # 應用常量 (狀態碼、TTL、排除條件)
│   │   ├── tables.py          # 表格元數據配置
│   │   └── workcenter_groups.py
│   ├── core/                   # 核心基礎設施
│   │   ├── database.py        # 連線池、查詢執行、keep-alive
│   │   ├── cache.py           # 快取抽象層
│   │   ├── cache_updater.py   # WIP 快取背景更新
│   │   ├── circuit_breaker.py # 熔斷器保護
│   │   ├── redis_client.py    # Redis 客戶端
│   │   ├── response.py        # API 響應標準化
│   │   ├── permissions.py     # 權限檢查
│   │   ├── log_store.py       # SQLite 日誌儲存
│   │   ├── metrics.py         # 性能指標收集
│   │   └── utils.py           # 通用工具函數
│   ├── routes/                 # API 路由 (Blueprint)
│   ├── services/               # 業務邏輯層
│   ├── sql/                    # SQL 查詢模板 (集中管理)
│   │   ├── loader.py          # SQL 檔案載入器
│   │   ├── builder.py         # 參數化查詢構建器
│   │   ├── filters.py         # 通用篩選條件
│   │   ├── dashboard/         # 儀表板 SQL
│   │   ├── wip/               # WIP SQL
│   │   ├── resource/          # 設備 SQL
│   │   ├── resource_history/  # 歷史 SQL
│   │   └── job_query/         # 維修工單 SQL
│   ├── templates/              # Jinja2 HTML 模板
│   └── static/                 # 靜態資源 (JS/CSS/dist)
├── tests/                      # 測試套件
├── data/                       # 運行時數據 (page_status.json)
├── logs/                       # 日誌目錄
├── .env                        # 環境變數 (不提交版控)
└── requirements.txt            # Python 依賴
```

---

## SQL 管理規範

### 原則
1. **SQL 檔案集中管理**: 所有 SQL 查詢放在 `src/mes_dashboard/sql/` 目錄下
2. **禁止硬編碼 SQL**: 不在 Python 程式碼中直接寫入複雜 SQL
3. **使用 QueryBuilder**: 所有動態條件必須使用 `QueryBuilder` 構建

### SQL 檔案位置規範

```
sql/
├── dashboard/     # 儀表板相關 (kpi.sql, heatmap.sql, ...)
├── wip/           # WIP 相關 (summary.sql, detail.sql, ...)
├── resource/      # 設備相關 (by_status.sql, detail.sql, ...)
├── resource_history/  # 歷史相關
└── job_query/     # 維修工單相關
```

### SQL 載入方式

```python
from mes_dashboard.sql.loader import SQLLoader

# 載入 SQL 檔案 (自動 LRU 快取)
sql = SQLLoader.load("wip/summary")

# 結構性參數替換 (用於 SQL 片段)
sql = SQLLoader.load_with_params("dashboard/kpi",
    LATEST_STATUS_SUBQUERY="...")
```

### QueryBuilder 使用規範

```python
from mes_dashboard.sql.builder import QueryBuilder

builder = QueryBuilder()

# 添加條件 (自動參數化，防 SQL 注入)
builder.add_in_condition("STATUS", ["PRD", "SBY"])
builder.add_like_condition("LOTID", user_input, position="both")
builder.add_not_in_condition("HOLD_REASON", exclude_list)

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
| 參數 | `:param_name` | 動態用戶輸入 | Bind variables |

### Oracle SQL 特殊規則

```sql
-- CTE 多次使用時加 MATERIALIZE 提示
WITH cte AS (/*+ MATERIALIZE */ SELECT ...)

-- 日期範圍查詢
TXNDATE >= :start_date AND TXNDATE < :end_date + 1

-- IN 子句上限 1000 個值，需分批處理
```

---

## 資料庫連線規範

### 連線池設置 (位置: `core/database.py`)

```python
# 生產環境配置
QueuePool(
    pool_size=10,           # 基礎連線數
    max_overflow=20,        # 額外連線數 (總計 30)
    pool_timeout=30,        # 等待超時 30 秒
    pool_recycle=1800,      # 30 分鐘回收
    pool_pre_ping=True,     # 使用前驗證
)

# 開發環境配置
pool_size=2, max_overflow=3
```

### 查詢執行規範

```python
from mes_dashboard.core.database import read_sql_df

# 標準查詢執行
df = read_sql_df(sql, params)

# 自動功能:
# - Circuit Breaker 檢查
# - 慢查詢警告 (>1 秒)
# - 指標記錄
# - 連線自動歸還
```

### 禁止事項

- ❌ 直接使用 `oracledb.connect()` 建立連線
- ❌ 在 Service 層手動管理連線
- ❌ 忘記使用 `with` 語句或 `g.db`
- ❌ 在 SQL 字串中拼接用戶輸入

---

## 資料表欄位規則

### 關鍵欄位映射

| 表名 | 正確欄位 | 錯誤欄位 |
|------|---------|---------|
| DW_MES_RESOURCE | `PJ_ASSETSSTATUS` | ~~ASSETSTATUS~~ |
| DW_MES_RESOURCE | `LOCATIONNAME` | ~~LOCATION~~ |
| DW_MES_RESOURCESTATUS_SHIFT | `HISTORYID` (映射到 RESOURCEID) | |
| DW_PJ_LOT_V | `WORKCENTER_GROUP` 映射來源 | |

### 標準篩選條件

```python
# 位置排除 (config/constants.py)
EXCLUDED_LOCATIONS = ['ATEC', 'F區', '報廢', '實驗室', ...]

# 資產狀態排除
EXCLUDED_ASSET_STATUSES = ['Disapproved']

# 設備類型篩選
EQUIPMENT_TYPE_FILTER = """
((OBJECTCATEGORY = 'ASSEMBLY' AND OBJECTTYPE = 'ASSEMBLY')
 OR (OBJECTCATEGORY = 'WAFERSORT' AND OBJECTTYPE = 'WAFERSORT'))
"""
```

---

## API 設計規範

### Blueprint 結構

```python
# 路由檔案位置: routes/<module>_routes.py
# URL 前綴: /api/<module>/

wip_bp = Blueprint('wip', __name__, url_prefix='/api/wip')
resource_bp = Blueprint('resource', __name__, url_prefix='/api/resource')
```

### 統一響應格式 (位置: `core/response.py`)

```python
# 成功響應
{
    "success": True,
    "data": {...},
    "meta": {"timestamp": "ISO8601"}
}

# 錯誤響應
{
    "success": False,
    "error": {
        "code": "DB_CONNECTION_FAILED",
        "message": "資料庫連線失敗，請稍後再試",
        "details": "ORA-12541" # 僅開發模式
    }
}
```

### 錯誤代碼規範

```python
# 使用預定義的錯誤函數
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

## 前端開發規範

### 範本繼承

```jinja2
{# 頁面模板必須繼承 _base.html #}
{% extends "_base.html" %}

{% block head_extra %}
{# 頁面特定的 CSS #}
{% endblock %}

{% block content %}
{# 頁面內容 #}
{% endblock %}

{% block scripts %}
{# 頁面特定的 JS #}
{% endblock %}
```

### API 調用規範

使用統一的 API 客戶端 (`static/js/mes-api.js`)：

```javascript
// GET 請求
const data = await MesApi.get('/api/wip/summary', {
    params: { page: 1 },
    timeout: 60000,
});

// POST 請求
const data = await MesApi.post('/api/query_table', {
    table_name: 'TABLE_A',
    filters: {...}
});

// 特性:
// - 自動重試 (3 次，指數退避)
// - 自動 Toast 通知
// - 請求 ID 追蹤
// - AbortSignal 支援
```

### Toast 通知規範

```javascript
// 使用全局 Toast 系統 (NOT MESToast)
Toast.info('訊息內容');
Toast.success('操作成功');
Toast.warning('警告訊息');
Toast.error('連線失敗', { retry: () => loadData() });

const id = Toast.loading('載入中...');
Toast.dismiss(id);
```

### JavaScript 注意事項

```javascript
// .reverse() 會修改原陣列，使用前先複製
const reversed = [...originalArray].reverse();
```

---

## 快取策略

### 多層快取架構

```
請求 → 進程級快取 (30 秒 TTL)
     → Redis 快取 (可配置 TTL)
     → Oracle 資料庫
```

### 快取 TTL 常量 (位置: `config/constants.py`)

```python
CACHE_TTL_DEFAULT = 60           # 1 分鐘
CACHE_TTL_FILTER_OPTIONS = 600   # 10 分鐘
CACHE_TTL_KPI = 60               # 1 分鐘
```

### 快取使用方式

```python
# 通用快取
from mes_dashboard.core.cache import cache_get, cache_set

# Filter 快取 (workcenter/family)
from mes_dashboard.services.filter_cache import get_workcenters

# 重要: WORKCENTERNAME → WORKCENTER_GROUP 轉換
```

---

## 配置管理規範

### 環境變數 (.env)

```bash
# 資料庫 (必需) - 實際值請參考 .env.example
DB_HOST=<your_database_host>
DB_PORT=1521
DB_SERVICE=<your_service_name>
DB_USER=<your_username>
DB_PASSWORD=<your_password>

# Flask (必需)
FLASK_ENV=production
SECRET_KEY=<your_secret_key>

# 認證 (必需)
LDAP_API_URL=<your_ldap_api_url>
ADMIN_EMAILS=<admin_email_list>

# 快取 (建議)
REDIS_ENABLED=true
REDIS_URL=redis://localhost:6379/0

# 熔斷器 (生產建議啟用)
CIRCUIT_BREAKER_ENABLED=true
CIRCUIT_BREAKER_FAILURE_THRESHOLD=5
```

### 環境配置類 (位置: `config/settings.py`)

```python
# 根據 FLASK_ENV 自動選擇配置
class DevelopmentConfig(Config):
    DEBUG = True
    DB_POOL_SIZE = 2

class ProductionConfig(Config):
    DEBUG = False
    DB_POOL_SIZE = 10
```

### 禁止事項

- ❌ 硬編碼敏感資訊 (密碼、密鑰)
- ❌ 提交 `.env` 檔案到版控
- ❌ 在程式碼中直接寫死配置值

---

## 錯誤處理規範

### 三層錯誤處理

```python
# 1. 路由層 - 驗證錯誤
@bp.route('/api/query')
def query():
    if not request.json.get('table_name'):
        return validation_error("table_name 為必填")

# 2. 服務層 - 業務錯誤
def get_wip_summary(filters):
    try:
        df = query_wip(filters)
        if df.empty:
            return None  # 返回 None，不拋出異常
        return process_data(df)
    except Exception as exc:
        logger.error(f"WIP query failed: {exc}")
        return None  # 優雅降級

# 3. 核心層 - 基礎設施錯誤
def read_sql_df(sql, params):
    if not circuit_breaker.allow_request():
        raise RuntimeError("Circuit breaker open")
    # ... 執行查詢
```

### 熔斷器狀態

```
CLOSED    → 正常運作
OPEN      → 拒絕請求 (達到失敗閾值)
HALF_OPEN → 測試恢復
```

### 日誌記錄規範

```python
import logging
logger = logging.getLogger('mes_dashboard')

# 層級使用:
logger.debug("詳細調試資訊")
logger.info("一般操作記錄")
logger.warning("警告但可繼續")
logger.error("錯誤需要關注", exc_info=True)  # 包含堆棧
```

---

## 頁面狀態管理

### 頁面狀態 (位置: `data/page_status.json`)

```json
{
  "pages": [
    {"route": "/wip-overview", "name": "WIP 即時概況", "status": "released"},
    {"route": "/tables", "name": "表格總覽", "status": "dev"}
  ],
  "api_public": true
}
```

### 狀態定義

- `released`: 所有用戶可訪問
- `dev`: 僅管理員可訪問
- `None`: 未註冊，由 Flask 路由控制

---

## 測試規範

### 測試目錄結構

```
tests/
├── conftest.py              # pytest fixtures
├── test_*_service.py        # 服務層測試 (單元測試)
├── test_*_routes.py         # API 端點測試 (整合測試)
├── e2e/test_*_e2e.py        # 端對端測試
└── stress/                  # 壓力測試
```

### 測試注意事項

```python
# 在 setUp 中重置資料庫引擎
from mes_dashboard.core import database as db
db._ENGINE = None

# 並行查詢 mock (ThreadPoolExecutor)
# 使用 function-based side_effect，不用 list
mock_read_sql.side_effect = lambda sql, params: ...
```

### 執行測試

```bash
# 單元測試
pytest tests/ -v

# 特定測試
pytest tests/test_wip_service.py -v

# 覆蓋率報告
pytest tests/ --cov=mes_dashboard
```

---

## 常見反模式

### ❌ 避免的做法

```python
# 1. SQL 字串拼接 (SQL 注入風險)
sql = f"SELECT * FROM TABLE WHERE ID = '{user_input}'"

# 2. 直接建立資料庫連線
conn = oracledb.connect(...)

# 3. 硬編碼配置
DB_HOST = "192.168.1.100"  # 不要這樣做!

# 4. 忽略錯誤
try:
    do_something()
except:
    pass

# 5. 在路由中直接執行 SQL
@bp.route('/api/data')
def get_data():
    sql = "SELECT * FROM TABLE"
    df = pd.read_sql(sql, conn)  # 錯誤!
```

### ✅ 正確做法

```python
# 1. 使用 QueryBuilder
builder = QueryBuilder()
builder.add_param_condition("ID", user_input)

# 2. 使用 read_sql_df()
df = read_sql_df(sql, params)

# 3. 使用環境變數
DB_HOST = os.getenv('DB_HOST')

# 4. 記錄錯誤
try:
    do_something()
except Exception as exc:
    logger.error(f"Failed: {exc}")
    return error_response(...)

# 5. 分層架構
# routes → services → core/database
```

---

## 新功能開發檢查清單

- [ ] SQL 查詢放在 `sql/` 目錄
- [ ] 使用 `QueryBuilder` 構建動態條件
- [ ] 使用 `read_sql_df()` 執行查詢
- [ ] API 響應使用標準格式
- [ ] 錯誤處理有日誌記錄
- [ ] 敏感配置使用環境變數
- [ ] 有對應的單元測試
- [ ] 頁面註冊到 `page_status.json`
- [ ] 更新 `docs/architecture_findings.md` (如有架構變更)

---

## 參考檔案

| 功能 | 檔案位置 |
|------|---------|
| SQL 載入 | `src/mes_dashboard/sql/loader.py` |
| 查詢構建 | `src/mes_dashboard/sql/builder.py` |
| 資料庫操作 | `src/mes_dashboard/core/database.py` |
| API 響應 | `src/mes_dashboard/core/response.py` |
| 熔斷器 | `src/mes_dashboard/core/circuit_breaker.py` |
| 配置類 | `src/mes_dashboard/config/settings.py` |
| 常量定義 | `src/mes_dashboard/config/constants.py` |
| 頁面狀態 | `src/mes_dashboard/services/page_registry.py` |
| API 客戶端 | `src/mes_dashboard/static/js/mes-api.js` |
| Toast 系統 | `src/mes_dashboard/static/js/toast.js` |
| 架構文檔 | `docs/architecture_findings.md` |
