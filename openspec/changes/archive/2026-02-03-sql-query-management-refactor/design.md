## Context

目前 MES Dashboard 專案的 SQL 查詢管理存在以下問題：

**現況：**
- 約 62 個 SQL 查詢（服務層約 46 個 + core 層約 16 個）分散在 8 個 service 檔案及 core 層中
- 最大的 `wip_service.py` 有 2,423 行，包含 20 個 SQL 查詢
- 查詢使用 f-string 內嵌於 Python 中，難以維護與版控
- 使用者輸入直接插入 SQL，存在注入風險
- 相同的 filter 建構邏輯重複出現 4+ 次（分散於 `utils.py` 與各 service）

**技術限制：**
- 使用 Oracle Database，需支援 Oracle 特定語法
- 需向下相容現有的 `read_sql_df()` 和 `cursor.execute()` 呼叫
- 不變更 API 介面，僅重構內部實作
- 動態表名/欄位名無法用 bind variable 參數化

## Goals / Non-Goals

**Goals:**
- 建立可維護的 SQL 檔案管理機制
- 消除 SQL 注入風險，所有使用者輸入皆參數化
- 整合 `utils.py` 與新的 `sql/filters.py`，減少重複程式碼
- 提供型別安全的查詢建構 API

**Non-Goals:**
- 不遷移至 ORM（維持原生 SQL 以保持查詢效能與可讀性）
- 不變更現有 API 端點介面
- 不重構非 SQL 相關的程式碼
- 不新增外部依賴套件
- **不重構 `/api/query_table` 動態查表 API**（前端限定 TABLES_CONFIG 清單，後端未強制驗證）
- **不重構 `resource_routes.py`**（屬於 route 層，維持現狀）

## Decisions

### Decision 1: SQL 檔案組織結構

**選擇：** 按 service 領域分類的目錄結構

```
src/mes_dashboard/sql/
├── __init__.py
├── loader.py           # SQL 載入器
├── builder.py          # 查詢建構器
├── filters.py          # 共用篩選條件（整合自 utils.py）
├── wip/
│   ├── summary.sql
│   ├── matrix.sql
│   └── detail.sql
├── dashboard/
│   └── kpi.sql
└── resource/
    ├── latest_status.sql
    └── history_trend.sql
```

**替代方案考慮：**
- 單一 `queries.py` 常數檔案 → 不夠靈活，大檔案難維護
- 使用 SQLAlchemy ORM → 學習曲線高，複雜查詢不易表達

**理由：** 按領域分類便於查找，`.sql` 檔案可獲得 IDE 語法支援

### Decision 2: 參數化策略

**選擇：** 使用 Oracle bind variables (`:param_name`)

```python
# 參數化 IN 條件
sql = "SELECT * FROM t WHERE status IN (:p0, :p1, :p2)"
params = {"p0": "RUN", "p1": "QUEUE", "p2": "HOLD"}
cursor.execute(sql, params)
```

**替代方案考慮：**
- 使用 `?` placeholder → Oracle 不支援
- 使用 f-string + escape → 仍有注入風險

**理由：** Oracle 原生支援，查詢計畫可快取，完全避免注入

### Decision 3: 動態條件建構

**選擇：** Builder 模式，使用 placeholder 替換

```python
# SQL 檔案使用 placeholder
"""
SELECT * FROM t
{{ WHERE_CLAUSE }}
"""

# Builder 建構 WHERE 條件
builder = QueryBuilder(sql_template)
builder.add_in_condition("status", ["RUN", "QUEUE"])
sql, params = builder.build()
```

**替代方案考慮：**
- Jinja2 模板 → 過於複雜，不適合 SQL
- 純字串拼接 → 難以追蹤參數

**理由：** 保持 SQL 檔案可讀性，同時支援動態條件

### Decision 4: utils.py 整合策略

**選擇：** 將 `core/utils.py` 中的 SQL filter 邏輯遷移至 `sql/filters.py`，原函數改為 wrapper 呼叫新實作

**現有 utils.py 函數：**
- `build_filter_conditions()` → 遷移至 `CommonFilters.build_conditions()`
- `build_equipment_filter_sql()` → 遷移至 `CommonFilters.add_equipment_filter()`
- `build_location_filter_sql()` → 遷移至 `CommonFilters.add_location_filter()`
- `build_asset_status_filter_sql()` → 遷移至 `CommonFilters.add_asset_status_filter()`
- `build_exclusion_sql()` → 遷移至 `CommonFilters.add_exclusion()`

**整合方式：**
```python
# core/utils.py（保留向下相容）
from mes_dashboard.sql.filters import CommonFilters

def build_location_filter_sql(locations, excluded_locations):
    """Deprecated: use CommonFilters.add_location_filter() instead"""
    # 呼叫新實作，回傳相容格式...
    return CommonFilters.build_location_filter_legacy(locations, excluded_locations)
```

**理由：** 避免破壞現有呼叫點，漸進式遷移

### Decision 5: 打包設定更新

**選擇：** 修改 `pyproject.toml` 加入 SQL 檔案

```toml
[tool.setuptools.package-data]
mes_dashboard = [
    "templates/**/*",
    "sql/**/*.sql"  # 新增
]
```

**理由：** 確保部署時 SQL 檔案被包含在 package 中

### Decision 6: 遷移策略

**選擇：** 漸進式遷移，按複雜度排序

1. 先建立 `sql/` 基礎架構
2. 遷移 `resource_service.py`（7 queries，複雜度中等）作為 POC
3. 遷移 `dashboard_service.py`（5 queries）
4. 遷移 `resource_history_service.py`（6 queries）
5. 遷移 `wip_service.py`（20 queries，最大檔案）
6. 遷移其餘 service（realtime_equipment_cache, resource_cache, filter_cache）
7. 遷移 core 層（database.py, utils.py, cache_updater.py）
8. 驗證 `excel_query_service.py`（已有良好參數化）

**理由：** 降低風險，可早期驗證設計，逐步累積經驗

## Risks / Trade-offs

| 風險 | 緩解措施 |
|------|---------|
| SQL 檔案與 Python 程式碼不同步 | 建立單元測試驗證 SQL 語法正確性 |
| 遷移期間功能回歸 | 保留原始實作，新舊並行測試 |
| 效能下降（額外的檔案 I/O） | 使用 LRU cache 快取載入的 SQL |
| 團隊學習曲線 | 提供使用範例與文件 |
| utils.py 整合造成相依性問題 | 保留 wrapper 函數維持向下相容 |
| 部署時遺失 SQL 檔案 | 更新 pyproject.toml 並加入 CI 驗證 |

## Migration Plan

**Phase 1：基礎架構**
- 建立 `sql/` 目錄結構
- 實作 `SQLLoader` 類別
- 實作 `QueryBuilder` 類別
- 實作 `CommonFilters` 類別
- 更新 `pyproject.toml` 包含 SQL 檔案
- 新增單元測試

**Phase 2：POC 驗證**
- 遷移 `resource_service.py`（7 queries）
- 驗證功能正確性與效能

**Phase 3：Service 層遷移**
- 遷移 `dashboard_service.py`（5 queries）
- 遷移 `resource_history_service.py`（6 queries）
- 遷移 `wip_service.py`（20 queries）
- 遷移其餘 service 檔案

**Phase 4：Core 層遷移**
- 整合 `core/utils.py` filter 邏輯
- 遷移 `core/database.py` 確保所有呼叫使用 params
- 遷移 `core/cache_updater.py`

**Phase 5：清理與驗證**
- 移除舊實作
- 更新文件
- 執行完整測試套件

**Rollback 策略：**
- 每個 service 保留原始函數（加 `_legacy` 後綴）
- 遷移期間可快速切換回舊實作
