## Context

### 背景

MES Dashboard 是一個 Flask 應用，提供 WIP（在製品）即時監控儀表板。所有 WIP 相關查詢都來自 Oracle 視圖 `DWH.DW_PJ_LOT_V`，此視圖由 DWH 每 20 分鐘刷新一次。

### 現況架構

```
Browser ──(每10分鐘刷新)──▶ Flask API ──(每次查詢)──▶ Oracle DW_PJ_LOT_V
```

### 問題

1. **Oracle 查詢負載高**：資料 20 分鐘更新一次，但每次 API 請求都查詢 Oracle
2. **Worker 卡死無法恢復**：SQLAlchemy 連接沒有 `call_timeout`，gthread worker 的 timeout 機制對工作線程無效
3. **服務可用性低**：Worker 耗盡時只能手動重啟

### 相關方

- MES 團隊：使用 WIP Dashboard 監控生產狀況
- IT 維運：負責服務穩定性
- DBA：關注 Oracle 查詢負載

## Goals / Non-Goals

### Goals

1. **減少 Oracle 查詢負載**：透過 Redis 表級快取，將 Oracle 查詢降至每 10 分鐘一次（背景任務）
2. **提升服務穩定性**：Worker 卡死時能自動恢復或定期重啟
3. **維持資料即時性**：快取資料與 Oracle 保持一致（基於 SYS_DATE 檢查）
4. **降級容錯**：Redis 不可用時自動 fallback 到直接查詢 Oracle

### Non-Goals

1. **不改變前端刷新邏輯**：前端仍維持每 10 分鐘自動刷新
2. **不快取其他資料表**：僅針對 `DW_PJ_LOT_V`
3. **不實作 Redis 叢集**：單節點 Redis 即可滿足需求
4. **不改變 API 介面**：所有 API 的 request/response 格式維持不變

## Decisions

### Decision 1: 表級快取 vs API 結果快取

**選擇**：表級快取（將整個 `DW_PJ_LOT_V` 快取到 Redis）

**替代方案**：
- API 結果快取：每個 API + 篩選條件組合各自快取

**理由**：
- 快取邏輯簡單，只需維護一份資料
- 所有 API 使用同一份快取，資料一致性好
- Redis key 數量少（3 個 vs 數十個）
- 更新邏輯單純：SYS_DATE 變化 → 載入整表

**權衡**：
- 需要在 Python 層進行篩選/聚合計算
- 需要足夠的 Redis 記憶體儲存整表

---

### Decision 2: 快取資料格式

**選擇**：JSON 格式儲存

**替代方案**：
- MessagePack：更小、更快，但可讀性差
- Pickle：Python 原生，但有安全風險且跨版本相容性差

**理由**：
- 可讀性佳，便於除錯和監控
- 跨語言相容（未來可能有其他服務讀取）
- Python `json` 模組效能足夠

**權衡**：
- JSON 體積較大（約 MessagePack 的 1.5-2 倍）
- 如資料量過大，可考慮改用 MessagePack 或 gzip 壓縮

---

### Decision 3: 背景任務實作方式

**選擇**：Python threading 背景線程

**替代方案**：
- Celery：功能強大但架構複雜，需要 broker
- APScheduler：額外依賴，對簡單定時任務過重
- 系統 cron：與應用分離，部署和監控較複雜

**理由**：
- 專案已有類似模式（`database.py` 的 keepalive 線程）
- 無需額外依賴
- 與應用生命週期綁定，隨應用啟停

**實作**：
```python
# cache_updater.py
import threading

class CacheUpdater:
    def __init__(self, interval=600):
        self.interval = interval
        self._stop_event = threading.Event()
        self._thread = None

    def start(self):
        self._thread = threading.Thread(target=self._worker, daemon=True)
        self._thread.start()

    def _worker(self):
        while not self._stop_event.wait(self.interval):
            self._check_and_update()
```

---

### Decision 4: Redis 連接管理

**選擇**：使用 `redis-py` 內建連接池

**配置**：
```python
import redis

redis_client = redis.Redis.from_url(
    REDIS_URL,
    decode_responses=True,
    socket_timeout=5,
    socket_connect_timeout=5,
    retry_on_timeout=True,
    health_check_interval=30
)
```

**理由**：
- `redis-py` 預設使用連接池，無需額外配置
- 內建重試和健康檢查機制
- 與現有 Flask 應用整合簡單

---

### Decision 5: Worker 穩定性策略

**選擇**：組合策略

1. **SQLAlchemy call_timeout**：在連接 checkout 時設置 55 秒超時
2. **Gunicorn max_requests**：每 500-1000 請求後重啟 worker
3. **健康檢查端點**：供外部監控系統使用

**實作**：

```python
# database.py - 連接 checkout 時設置超時
@event.listens_for(engine, "checkout")
def on_checkout(dbapi_conn, connection_record, connection_proxy):
    dbapi_conn.call_timeout = 55000  # 55 秒
```

```python
# gunicorn.conf.py
max_requests = 1000
max_requests_jitter = 100
timeout = 65  # > call_timeout
```

**理由**：
- call_timeout 確保單一查詢不會無限卡住
- max_requests 定期重啟避免狀態累積（記憶體洩漏、連接問題）
- 健康檢查支援 Kubernetes/systemd 等監控工具

---

### Decision 6: 降級策略

**選擇**：Redis 不可用時自動 fallback 到 Oracle 直接查詢

**實作邏輯**：
```python
def get_wip_data():
    if redis_enabled and redis_available():
        data = get_from_redis()
        if data:
            return data

    # Fallback: 直接查詢 Oracle
    return query_oracle_directly()
```

**理由**：
- 確保服務可用性，不因 Redis 故障導致整個服務不可用
- 降級時效能下降但功能正常

---

### Decision 7: Redis Key 命名空間

**選擇**：使用可配置的前綴 `{REDIS_KEY_PREFIX}:`

**預設前綴**：`mes_wip`

**Key 結構**：
| Key | 用途 |
|-----|------|
| `mes_wip:meta:sys_date` | Oracle 資料的 SYS_DATE |
| `mes_wip:meta:updated_at` | 快取更新時間（ISO 8601） |
| `mes_wip:data` | 完整表資料（JSON） |

**理由**：
- 前綴可透過環境變數配置，支援多環境/多專案共用 Redis
- 結構清晰，便於管理和清理

## Risks / Trade-offs

### Risk 1: 資料量過大導致效能問題

**風險**：`DW_PJ_LOT_V` 資料量大，JSON 序列化/反序列化耗時

**緩解**：
- 實作前先確認資料量：`SELECT COUNT(*) FROM DWH.DW_PJ_LOT_V`
- 如超過 10 萬筆，考慮：
  - 使用 MessagePack 取代 JSON
  - 使用 gzip 壓縮
  - 只快取必要欄位

---

### Risk 2: Redis 記憶體不足

**風險**：表資料 + Redis 運作開銷超過配置的記憶體限制

**緩解**：
- 配置 `maxmemory-policy allkeys-lru`，自動清理舊資料
- 監控 Redis 記憶體使用率
- 預留 2 倍快取大小的記憶體

---

### Risk 3: 快取更新期間的資料不一致

**風險**：背景任務更新快取時，API 可能讀到部分更新的資料

**緩解**：
- 使用 Redis MULTI/EXEC 確保原子更新
- 或使用雙緩衝：寫入新 key，完成後切換

```python
# 原子更新方案
pipe = redis_client.pipeline()
pipe.set(f"{prefix}:data", new_data)
pipe.set(f"{prefix}:meta:sys_date", new_sys_date)
pipe.set(f"{prefix}:meta:updated_at", now)
pipe.execute()
```

---

### Risk 4: 背景線程異常終止

**風險**：cache_updater 線程因未捕獲的異常而終止

**緩解**：
- 在 worker 函數中使用 try-except 包裹
- 記錄錯誤日誌
- 定期檢查線程存活狀態

---

### Risk 5: 首次啟動時無快取

**風險**：應用啟動時 Redis 無資料，第一個請求會觸發 Oracle 查詢

**緩解**：
- 應用啟動時立即執行一次快取更新
- 或接受首次請求的延遲（可接受的權衡）

## Migration Plan

### Phase 1: 基礎建設（Day 1）

1. 安裝 Redis 服務
   ```bash
   sudo apt install redis-server
   sudo systemctl enable redis-server
   ```

2. 更新 `requirements.txt`
   ```
   redis>=5.0.0
   hiredis>=2.0.0  # 可選，效能優化
   ```

3. 新增環境變數到 `.env`
   ```
   REDIS_URL=redis://localhost:6379/0
   REDIS_ENABLED=true
   REDIS_KEY_PREFIX=mes_wip
   CACHE_CHECK_INTERVAL=600
   ```

### Phase 2: 程式碼變更（Day 2-3）

1. 新增 `core/redis_client.py` - Redis 連接管理
2. 重寫 `core/cache.py` - 表級快取實作
3. 新增 `core/cache_updater.py` - 背景更新任務
4. 修改 `core/database.py` - 加入 call_timeout
5. 修改 `services/wip_service.py` - 改用快取
6. 新增 `routes/health_routes.py` - 健康檢查
7. 修改 `gunicorn.conf.py` - 加入 max_requests

### Phase 3: 測試（Day 4）

1. 單元測試：快取讀寫、降級邏輯
2. 整合測試：API 回傳結果正確性
3. 效能測試：比較快取前後的回應時間
4. 降級測試：停止 Redis，確認 fallback 正常

### Phase 4: 部署（Day 5）

1. 部署 Redis 服務
2. 部署應用程式更新
3. 監控 Redis 記憶體和應用程式日誌
4. 確認 Oracle 查詢頻率降低

### Rollback Strategy

如需回滾：

1. 設置 `REDIS_ENABLED=false` 並重啟應用
2. 應用會自動 fallback 到直接查詢 Oracle
3. 無需回滾程式碼，功能完全向後相容

## Open Questions

### Q1: DW_PJ_LOT_V 資料量？

**待確認**：執行 `SELECT COUNT(*) FROM DWH.DW_PJ_LOT_V` 確認筆數和資料大小

**影響**：
- < 1 萬筆：JSON 格式無問題
- 1-10 萬筆：可能需要效能優化
- > 10 萬筆：需要考慮 MessagePack 或只快取必要欄位

---

### Q2: 是否需要快取特定欄位？

**現況**：計劃快取整表所有欄位

**考量**：
- 如只快取 API 需要的欄位，可減少記憶體使用
- 但需要確保不遺漏任何欄位

---

### Q3: 前端刷新間隔是否需要調整？

**現況**：前端每 10 分鐘刷新，與背景任務檢查間隔相同

**考量**：
- 如前端更頻繁刷新（如 5 分鐘），快取效益更明顯
- 但現有間隔已足夠，暫不調整
