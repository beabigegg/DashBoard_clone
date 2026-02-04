## Context

MES Dashboard 是基於 Flask + Gunicorn + Redis 的報表系統，目前已完成 SQL 查詢安全架構重構。系統運行於：
- Gunicorn: 2 workers × 4 threads
- Oracle Database: 連線池 (pool_size=5, max_overflow=10)
- Redis: 設備狀態快取 (30 秒更新)

**現有架構限制：**
- 錯誤處理分散於各 service/route，格式不一致
- 資料庫異常時無熔斷機制，可能導致連線池耗盡
- 效能指標僅有 warning log，無量化追蹤
- 管理員需 SSH 登入才能處理 worker 問題

**利害關係人：**
- 終端使用者：需要友善的錯誤訊息與穩定的服務
- 管理員：需要效能監控與緊急處理能力
- 維運人員：需要可觀測性與問題診斷工具

## Goals / Non-Goals

**Goals:**
- 統一 API 回應格式，提升前端開發體驗
- 實作熔斷機制，防止資料庫異常導致雪崩
- 提供效能指標收集與視覺化報表
- 允許管理員從前端安全地重啟服務
- 新增本地快取作為 Redis 的二級 fallback

**Non-Goals:**
- 不實作分散式追蹤 (distributed tracing)
- 不整合外部監控系統 (Prometheus/Grafana)
- 不變更現有 API 端點路徑
- 不實作自動擴展 (auto-scaling)
- 不實作 Excel 批次查詢進度回報（需評估前後端架構變更）
- 不實作歷史趨勢查詢優化（預計算/分層快取）

## Decisions

### Decision 1: API 回應格式

**選擇：** 標準化 envelope 格式，向下相容

```python
# 成功回應
{
    "success": True,
    "data": { ... },           # 原有回應內容
    "meta": {                  # 可選的中繼資料
        "timestamp": "...",
        "request_id": "..."
    }
}

# 錯誤回應
{
    "success": False,
    "error": {
        "code": "DB_CONNECTION_FAILED",  # 機器可讀代碼
        "message": "資料庫連線失敗，請稍後再試",  # 使用者友善訊息
        "details": "ORA-12541: TNS:no listener"  # 僅開發模式顯示
    }
}
```

**替代方案考慮：**
- 完全重新設計 API → 破壞向下相容，需前端配合改版
- 僅加 HTTP status code → 錯誤資訊不夠豐富

**理由：** 保持原有 `data` 結構，僅加上 `success` 和 `error` 包裝，前端可漸進式遷移。

---

### Decision 2: Circuit Breaker 熔斷器

**選擇：** 自製輕量熔斷器，基於滑動視窗計數

```
狀態轉換：
CLOSED → (失敗率 > 50% 且失敗數 > 5) → OPEN
OPEN → (等待 30 秒) → HALF_OPEN
HALF_OPEN → (探測成功) → CLOSED
HALF_OPEN → (探測失敗) → OPEN
```

**參數設計：**
| 參數 | 值 | 說明 |
|------|-----|------|
| failure_threshold | 5 | 最少失敗次數才觸發 |
| failure_rate | 0.5 | 失敗率閾值 (50%) |
| recovery_timeout | 30s | OPEN 狀態等待時間 |
| window_size | 10 | 滑動視窗大小 |

**計數層級：**
- 熔斷器 SHALL 在 `read_sql_df()` 層級實作（所有 SQL 查詢共用單一熔斷器）
- 這確保所有資料庫查詢（包含 WIP、Equipment、Hold 等）共同計算失敗率
- 當熔斷器 OPEN 時，所有查詢立即回傳錯誤，避免連線池耗盡
- 單一熔斷器設計簡化狀態管理，且符合「資料庫整體健康」的概念

**替代方案考慮：**
- 使用 `pybreaker` 套件 → 增加外部依賴
- 使用 `tenacity` retry → 只處理重試，無熔斷

**理由：** 需求簡單，自製可完全控制行為，無外部依賴。

---

### Decision 3: 效能指標收集

**選擇：** 記憶體內滑動視窗 + 定期彙總

```python
class QueryMetrics:
    # 使用 deque 儲存最近 1000 筆查詢延遲
    latencies: deque[float] = deque(maxlen=1000)

    # 計算 percentiles
    def get_percentiles(self) -> dict:
        sorted_latencies = sorted(self.latencies)
        return {
            "p50": percentile(sorted_latencies, 50),
            "p95": percentile(sorted_latencies, 95),
            "p99": percentile(sorted_latencies, 99),
            "count": len(sorted_latencies),
            "slow_count": sum(1 for l in sorted_latencies if l > 1.0)
        }
```

**儲存策略：**
- 即時指標：記憶體內滑動視窗
- 不持久化歷史資料（避免複雜度）
- 每個 worker 獨立統計（不跨 worker 合併，前端顯示當前 Worker PID）

**替代方案考慮：**
- 使用 Redis 儲存 → 增加 Redis 負擔
- 使用 Prometheus → 需要額外基礎設施

**理由：** 簡單場景不需複雜方案，記憶體內統計足夠。

---

### Decision 4: 本地快取 Fallback

**選擇：** TTL-aware LRU Cache 作為 Redis 的二級快取

```
快取查詢流程：
1. 查詢 Redis → 命中則回傳
2. Redis 失敗/未命中 → 查詢本地 LRU Cache
3. 本地未命中 → 查詢 Oracle
4. 回填：同時寫入 Redis 和本地快取
```

**本地快取參數：**
| 參數 | 值 | 說明 |
|------|-----|------|
| maxsize | 500 | 最大條目數（足以容納多組快取如 WIP、Equipment、Hold） |
| ttl | 60s | 過期時間（比 Redis 短） |

**替代方案考慮：**
- 只用 Redis → Redis 故障時無 fallback
- 使用 `cachetools.TTLCache` → 可接受，但自製更靈活

**理由：** 增加一層本地快取，Redis 故障時仍能從本地取得較新資料。

---

### Decision 5: Worker 重啟機制

**選擇：** 方案 C - 控制檔案 + Watchdog 腳本

```
架構：
┌─────────────┐     寫入檔案      ┌─────────────────┐
│ Flask App   │ ───────────────→ │ /tmp/restart.flag│
│ (Admin API) │                  └────────┬────────┘
└─────────────┘                           │ 監控
                                          ▼
┌─────────────┐     SIGHUP       ┌─────────────────┐
│ Gunicorn    │ ←─────────────── │ worker_watchdog │
│ Master      │                  │ (獨立 Python)   │
└─────────────┘                  └─────────────────┘
```

**流程：**
1. Admin 點擊「重啟服務」按鈕
2. Flask 寫入 `/tmp/mes_dashboard_restart.flag`
3. Watchdog 腳本偵測到檔案，發送 SIGHUP 給 Gunicorn master
4. Gunicorn graceful reload 所有 workers
5. Watchdog 刪除 flag 檔案

**安全機制：**
- API 僅限 admin_required
- 冷卻時間 60 秒（防止連續觸發）
- 操作日誌記錄到檔案和資料庫
- 前端需二次確認

**替代方案考慮：**
- 方案 A (SIGHUP 直接發送) → Flask worker 無法發送信號給 Gunicorn master
- 方案 B (systemctl) → 需要 sudo 權限，安全風險高
- 方案 D (獨立控制服務) → 過度設計

**理由：** 安全、解耦、不需要特殊權限，Flask 只需寫檔案。

---

### Decision 6: 效能報表頁面

**選擇：** 整合至現有 Admin 頁面，使用 Chart.js 視覺化

**頁面內容：**
```
┌─────────────────────────────────────────────────────┐
│  效能監控儀表板                          [重新整理] │
├─────────────────────────────────────────────────────┤
│  系統狀態                                           │
│  ┌─────────┐ ┌─────────┐ ┌─────────┐ ┌─────────┐  │
│  │ Database│ │  Redis  │ │ Circuit │ │ Workers │  │
│  │   ✅    │ │   ✅    │ │ CLOSED  │ │   2/2   │  │
│  └─────────┘ └─────────┘ └─────────┘ └─────────┘  │
├─────────────────────────────────────────────────────┤
│  查詢效能 (最近 1000 筆)                           │
│  P50: 0.12s  P95: 0.45s  P99: 1.23s  慢查詢: 15   │
│  [========================================] 延遲分布│
├─────────────────────────────────────────────────────┤
│  快取狀態                                           │
│  Redis: 命中率 85%  本地: 命中率 92%               │
│  最後更新: 2026-02-03 16:30:22                     │
├─────────────────────────────────────────────────────┤
│  服務控制                                           │
│  [重啟 Workers]  冷卻時間: 可用                    │
│  最後重啟: 2026-02-03 10:15:00 by admin@example    │
└─────────────────────────────────────────────────────┘
```

**API 端點：**
- `GET /admin/api/metrics` - 取得效能指標
- `GET /admin/api/system-status` - 取得系統狀態
- `GET /admin/api/logs` - 取得近期 log 紀錄
- `GET /admin/api/worker/status` - 取得 Worker 狀態（cooldown、last_restart、啟動時間）
- `POST /admin/api/worker/restart` - 觸發重啟

**自動重新整理：**
- 前端支援 30 秒自動重新整理間隔
- 使用者可手動停用自動重新整理

**Log 紀錄檢視：**
- 顯示最近 N 筆 log（預設 200 筆）
- 支援依等級（INFO/WARNING/ERROR）篩選與關鍵字搜尋
- 顯示欄位包含時間、等級、來源、訊息、操作者（若有）

---

### Decision 7: 深度健康檢查

**選擇：** 新增 `/health/deep` 端點，包含延遲指標


```json
{
    "status": "healthy",
    "checks": {
        "database": {
            "status": "healthy",
            "latency_ms": 12,
            "pool_size": 5,
            "pool_checked_out": 2
        },
        "redis": {
            "status": "healthy",
            "latency_ms": 2
        },
        "circuit_breaker": {
            "database": "CLOSED",
            "failures": 0
        },
        "cache": {
            "redis_hit_rate": 0.85,
            "local_hit_rate": 0.92,
            "last_update": "2026-02-03T16:30:22Z"
        }
    },
    "metrics": {
        "query_p50_ms": 120,
        "query_p95_ms": 450,
        "query_p99_ms": 1230
    }
}
```

---

### Decision 8: 管理員 Log 儲存與檢視

**選擇：** 使用本機 SQLite 儲存結構化 log，供管理員介面查詢

**策略：**
- 既有檔案/STDERR log 保留（維運與除錯用途）
- 另新增 SQLite log store 供管理員查詢（本機檔案）
- SQLite 以 append-only 方式寫入，避免重鎖

**建議預設：**
- 檔案位置：`logs/admin_logs.sqlite`
- 保留策略：保留最近 7 天或最多 100,000 筆（可由環境變數調整）

**理由：**
- 管理員需要可查詢的 log 紀錄
- SQLite 為標準函式庫，無新增 Python 第三方依賴
- 保留檔案 log 可維持既有維運流程



## Risks / Trade-offs

| 風險 | 緩解措施 |
|------|---------|
| Worker 重啟期間短暫服務中斷 | Gunicorn graceful reload 確保現有請求完成 |
| 本地快取資料過期 | TTL 設為 60 秒，比 Redis 短；加入版本檢查 |
| 熔斷器誤判導致服務不可用 | 設定合理閾值；HALF_OPEN 狀態快速探測 |
| 效能指標記憶體佔用 | 限制 deque maxsize=1000；每個 worker 獨立 |
| Watchdog 腳本異常 | 加入 systemd 監控 |
| SQLite log 檔案成長 | 設定保留天數/最大筆數並定期清理 |
| 管理員誤操作重啟 | 二次確認 + 60 秒冷卻時間 |

## Migration Plan

**Phase 1: 基礎設施 (無影響)**
1. 新增 `core/response.py` - API 回應格式
2. 新增 `core/circuit_breaker.py` - 熔斷器
3. 新增 `core/metrics.py` - 效能指標
4. 新增 `core/local_cache.py` - 本地快取
5. 新增 `core/log_store.py` - SQLite log store
6. 新增單元測試

**Phase 2: 整合 (低風險)**
1. `database.py` 整合熔斷器（預設關閉）
2. `cache.py` 整合本地快取 fallback
3. 環境變數控制開關：`CIRCUIT_BREAKER_ENABLED=true`

**Phase 3: API 遷移 (漸進式)**
1. 新建立的 API 直接使用新格式
2. 現有 API 保持原格式（向下相容）
3. 前端視需要逐步遷移使用新格式

**Phase 4: 管理功能**
1. 新增效能報表頁面
2. 新增 log 檢視區塊與 logs API
3. 部署 watchdog 腳本
4. 新增 Worker 控制 API

**Rollback 策略：**
- 熔斷器：環境變數關閉 `CIRCUIT_BREAKER_ENABLED=false`
- 本地快取：環境變數關閉 `LOCAL_CACHE_ENABLED=false`
- Worker 控制：移除 watchdog 腳本即可

## Open Questions

1. **效能指標保留時間**：目前設計為記憶體內 1000 筆，是否需要持久化歷史？
2. ~~**多 Worker 指標合併**~~：已決定採用 per-worker 方式，前端顯示當前 Worker PID
3. **Watchdog 部署方式**：使用 systemd service 或 cron 監控？
4. ~~**API 格式遷移時程**~~：已決定不強制遷移，新 API 用新格式，舊 API 保持原格式
