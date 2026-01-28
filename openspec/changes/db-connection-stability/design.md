# Technical Design

## Decision: 連線池策略

**選擇**: SQLAlchemy QueuePool（而非 oracledb SessionPool）

**原因**:
- 現有程式碼已使用 SQLAlchemy
- QueuePool 提供內建的連線健康檢查（pool_pre_ping）
- 更容易與現有 `read_sql_df()` 整合

**設定**:
```python
create_engine(
    CONNECTION_STRING,
    pool_size=5,           # 基本連線數
    max_overflow=10,       # 額外連線數（尖峰時）
    pool_timeout=30,       # 等待連線的超時
    pool_recycle=1800,     # 30分鐘回收連線
    pool_pre_ping=True,    # 使用前檢查連線健康
)
```

---

## Decision: Logging 策略

**選擇**: 使用 Python logging 模組 + 結構化格式

**Logger 配置**:
```python
import logging

logger = logging.getLogger('mes_dashboard.database')
logger.setLevel(logging.INFO)

# Format: [時間] [層級] [模組] 訊息
formatter = logging.Formatter(
    '%(asctime)s [%(levelname)s] %(name)s: %(message)s'
)
```

**記錄內容**:
- 連線成功/失敗（含 ORA 錯誤碼）
- 查詢時間（標記 >1s 為慢查詢）
- 重試次數

---

## Decision: 密碼 URL 編碼

**選擇**: 使用 `urllib.parse.quote_plus()` 編碼密碼

**實作**:
```python
from urllib.parse import quote_plus

CONNECTION_STRING = (
    f"oracle+oracledb://{DB_USER}:{quote_plus(DB_PASSWORD)}"
    f"@{DB_HOST}:{DB_PORT}/?service_name={DB_SERVICE}"
)
```

---

## Implementation Approach

### 1. config/database.py 修改

```python
from urllib.parse import quote_plus

# 安全的連線字串（密碼已編碼）
CONNECTION_STRING = (
    f"oracle+oracledb://{DB_USER}:{quote_plus(DB_PASSWORD)}"
    f"@{DB_HOST}:{DB_PORT}/?service_name={DB_SERVICE}"
)
```

### 2. core/database.py 修改

```python
import logging
import time
from functools import wraps

logger = logging.getLogger('mes_dashboard.database')

def get_engine():
    global _ENGINE
    if _ENGINE is None:
        _ENGINE = create_engine(
            CONNECTION_STRING,
            pool_size=5,
            max_overflow=10,
            pool_timeout=30,
            pool_recycle=1800,
            pool_pre_ping=True,
            connect_args={
                "tcp_connect_timeout": 15,
                "retry_count": 2,
                "retry_delay": 1,
            }
        )
        logger.info("Database engine created with QueuePool")
    return _ENGINE


def read_sql_df(sql: str, params=None) -> pd.DataFrame:
    """Execute SQL with timing and error logging."""
    start_time = time.time()
    engine = get_engine()

    try:
        with engine.connect() as conn:
            df = pd.read_sql(text(sql), conn, params=params)
            df.columns = [str(c).upper() for c in df.columns]

            elapsed = time.time() - start_time
            if elapsed > 1.0:
                logger.warning(f"Slow query ({elapsed:.2f}s): {sql[:100]}...")
            else:
                logger.debug(f"Query completed in {elapsed:.3f}s")

            return df

    except Exception as exc:
        elapsed = time.time() - start_time
        # 擷取 ORA 錯誤碼
        ora_code = _extract_ora_code(exc)
        logger.error(
            f"Query failed after {elapsed:.2f}s - "
            f"ORA-{ora_code}: {exc}"
        )
        raise


def _extract_ora_code(exc: Exception) -> str:
    """從例外中擷取 ORA 錯誤碼."""
    import re
    match = re.search(r'ORA-(\d+)', str(exc))
    return match.group(1) if match else 'UNKNOWN'
```

---

## Data Flow

```
┌──────────────────────────────────────────────────────────────┐
│                     改進後的連線流程                          │
├──────────────────────────────────────────────────────────────┤
│                                                              │
│  API Request                                                 │
│       │                                                      │
│       ▼                                                      │
│  ┌─────────────────────────────────────────────────────┐    │
│  │  read_sql_df()                                      │    │
│  │  - 記錄開始時間                                     │    │
│  │  - 從 QueuePool 取得連線（或等待/新建）            │    │
│  └─────────────────────────────────────────────────────┘    │
│       │                                                      │
│       │ pool_pre_ping (健康檢查)                            │
│       ▼                                                      │
│  ┌─────────────────────────────────────────────────────┐    │
│  │  執行查詢                                           │    │
│  │  - 成功: 記錄查詢時間，標記慢查詢                  │    │
│  │  - 失敗: 記錄 ORA 錯誤碼，考慮重試                 │    │
│  └─────────────────────────────────────────────────────┘    │
│       │                                                      │
│       │ 連線歸還 Pool（不關閉）                             │
│       ▼                                                      │
│  API Response                                                │
│                                                              │
└──────────────────────────────────────────────────────────────┘
```

---

## Testing Strategy

### 1. 單元測試
- Mock engine 測試 logging 輸出
- 測試 ORA 錯誤碼擷取

### 2. 整合測試
- 驗證連線池行為（pool_size, max_overflow）
- 模擬連線失敗，驗證重試邏輯

### 3. 監控驗證
- 確認 error.log 記錄 DB 錯誤
- 確認慢查詢被標記

---

## 額外考量

### 連線池大小與 Gunicorn 配置協調

```
Gunicorn: 2 workers × 4 threads = 8 併發
Pool: pool_size=5 + max_overflow=10 = 最多 15 連線/worker

實際最大連線數: 2 workers × 15 = 30 連線
```

**注意**: 確認 Oracle 端 `SESSIONS` 參數足夠（通常 >100 沒問題）

### 應用啟動時驗證連線

```python
def init_db(app):
    app.teardown_appcontext(close_db)

    # 啟動時驗證連線
    try:
        with get_engine().connect() as conn:
            conn.execute(text("SELECT 1 FROM DUAL"))
        logger.info("Database connection verified on startup")
    except Exception as e:
        logger.error(f"Database connection failed on startup: {e}")
        # 不中斷啟動，讓應用可以在 DB 恢復後自動運作
```

### Gunicorn preload_app 考量

```python
# gunicorn.conf.py
preload_app = False  # 建議保持 False，讓每個 worker 建立自己的 pool
```

若啟用 `preload_app = True`，需在 `post_fork` hook 重新初始化 engine。

### 連線池監控（可觀測性）

```python
from sqlalchemy import event

@event.listens_for(engine, "checkout")
def log_checkout(dbapi_conn, connection_record, connection_proxy):
    logger.debug("Connection checked out from pool")

@event.listens_for(engine, "checkin")
def log_checkin(dbapi_conn, connection_record):
    logger.debug("Connection returned to pool")
```

### Circuit Breaker 模式（Phase 3 可選）

```python
class CircuitBreaker:
    def __init__(self, failure_threshold=5, reset_timeout=60):
        self.failures = 0
        self.last_failure = None
        self.threshold = failure_threshold
        self.reset_timeout = reset_timeout

    def is_open(self):
        if self.failures >= self.threshold:
            if datetime.now() - self.last_failure < timedelta(seconds=self.reset_timeout):
                return True  # 熔斷中，直接拒絕
            self.failures = 0  # 重置嘗試
        return False

    def record_failure(self):
        self.failures += 1
        self.last_failure = datetime.now()

    def record_success(self):
        self.failures = 0
```

---

## 風險矩陣

| 項目 | 風險 | 優先級 |
|------|------|--------|
| 密碼 URL 編碼 | 低 | 高 |
| print → logging | 低 | 高 |
| 查詢時間統計 | 低 | 高 |
| NullPool → QueuePool | 中 | 高 |
| 啟動時驗證連線 | 低 | 中 |
| Pool 監控事件 | 低 | 低 |
| Circuit Breaker | 中 | 低 |

---

## 實作順序建議

1. **Phase 1**（logging + URL 編碼）→ 先上線觀察
2. **Phase 2**（連線池化 + 啟動驗證）→ 根據 Phase 1 的 log 調整參數
3. **Phase 3**（Circuit Breaker + 監控）→ 視需求加入
