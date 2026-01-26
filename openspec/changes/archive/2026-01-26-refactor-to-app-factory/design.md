## Context

MES Dashboard 目前使用 Flask 開發，但採用「簡易腳本」架構：
- `app = Flask(...)` 在 module level 建立
- 使用 `sys.path.insert(0, ...)` 處理 import 路徑
- 直接 `app.run()` 啟動開發伺服器

這種架構在以下方面有限制：
1. 無法使用 Gunicorn 多 worker 部署
2. 單元測試困難（無法隔離建立 app instance）
3. 不支援多環境設定（dev/staging/prod）
4. import 路徑 hack 導致 IDE 支援不佳、容易出錯

## Goals / Non-Goals

**Goals:**
- 重構為 Application Factory pattern，支援 `create_app(config)` 建立
- 建立標準 Python package 結構，使用正規 import
- 預留擴充點：cache backend 可抽換、connection pool 可調整
- 提供 Gunicorn 部署設定，單 worker + threads 為預設
- 保持所有現有功能不變

**Non-Goals:**
- 不實作 Redis cache（僅建立抽象介面）
- 不做前後端分離
- 不升級到 FastAPI（保持 Flask）
- 不實作多機部署 / Load Balancer

## Decisions

### 1. 目錄結構：src layout

**選擇**: `src/mes_dashboard/` 結構

**替代方案**:
- Flat layout (`mes_dashboard/` 在根目錄) - 較簡單但容易誤 import 本地未安裝的模組
- `apps/` 重命名 - 保留舊名但不符 Python 慣例

**理由**: src layout 是 Python packaging 最佳實踐，強制使用已安裝的 package，避免 import 混淆。

### 2. 設定管理：Environment-based config classes

**選擇**: Config class hierarchy + `.env` file

```python
class Config:
    """Base config"""

class DevelopmentConfig(Config):
    DEBUG = True

class ProductionConfig(Config):
    DEBUG = False
```

**替代方案**:
- Pydantic Settings - 更強大但增加依賴
- 純 `.env` - 不夠結構化

**理由**: Flask 原生支援 config object，無需額外依賴。`.env` 處理機敏資料，class 處理環境差異。

### 3. Cache 抽象：Protocol-based interface

**選擇**: 定義 `CacheBackend` protocol，目前實作 `NoOpCache`

```python
class CacheBackend(Protocol):
    def get(self, key: str) -> Any: ...
    def set(self, key: str, value: Any, ttl: int) -> None: ...

class NoOpCache:
    """Pass-through, no actual caching"""
```

**替代方案**:
- Flask-Caching extension - 功能完整但目前不需要
- 完全移除 cache code - 未來加回時改動大

**理由**: 保留介面但不實作功能，未來加入 Redis 只需新增一個 class。

### 4. Database 連線：Request-scoped via Flask g

**選擇**: 使用 `flask.g` 管理 request-scoped connection

```python
def get_db():
    if 'db' not in g:
        g.db = get_engine().connect()
    return g.db

@app.teardown_appcontext
def close_db(e=None):
    db = g.pop('db', None)
    if db: db.close()
```

**替代方案**:
- SQLAlchemy-Flask extension - 引入較多 magic
- 每次查詢新建連線 - 效能差

**理由**: 輕量、明確、與現有 SQLAlchemy engine 相容。

### 5. 部署方式：Gunicorn gthread worker

**選擇**: `gunicorn --workers 1 --threads 4`

**替代方案**:
- sync worker + 多 process - 對 Oracle connection pool 較不友善
- gevent/eventlet - 需要 monkey patching，增加複雜度

**理由**: gthread 在單 worker 下提供並發，且與同步 DB driver 相容。未來需要時可增加 workers。

## Risks / Trade-offs

| Risk | Mitigation |
|------|------------|
| 重構過程中斷現有功能 | 分階段進行，每階段可獨立測試 |
| Import 路徑變更影響範圍大 | 提供 migration script 批次更新 |
| NoOpCache 造成重複查詢 | 報表系統可接受，監控 DB 負載 |
| 單 worker 成為瓶頸 | 監控 response time，必要時增加 workers |

## Migration Plan

1. **建立新結構** - 在 `src/` 下建立 package，不影響現有 `apps/`
2. **移植模組** - 逐一將 config → core → services → routes 移入
3. **驗證功能** - 確保所有 API 和頁面正常
4. **切換啟動方式** - 更新啟動腳本使用 gunicorn
5. **清理舊檔** - 移除 `apps/` 目錄和舊的啟動腳本

**Rollback**: 保留 `apps/` 直到新架構穩定，隨時可切回。
