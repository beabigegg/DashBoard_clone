## Why

WIP Dashboard 的所有查詢（WIP Overview、WIP Detail、Hold Detail）都來自同一個 Oracle 視圖 `DWH.DW_PJ_LOT_V`。此視圖由 DWH 每 **20 分鐘**刷新一次。

### 現況問題

1. **前端自動刷新機制**：
   - `wip_overview.html:808` - 每 10 分鐘自動刷新
   - `wip_detail.html:756` - 每 10 分鐘自動刷新
   - 每次刷新都直接發送 API 請求查詢 Oracle

2. **重複查詢問題**：
   - Oracle 資料 20 分鐘才更新一次，但前端 10 分鐘刷新一次
   - 多個用戶同時使用時，同一份資料被重複查詢多次
   - 造成不必要的 Oracle 查詢負載

3. **Worker 卡死問題**：
   - Gunicorn 使用 gthread worker（2 workers × 4 threads）
   - SQLAlchemy 連接池的連接**沒有設置 `call_timeout`**（見 `database.py:46-59`）
   - gthread 的 timeout 機制對工作線程無效（心跳由主線程發送）
   - Worker 卡死時無法自動恢復，只能手動重啟服務

## What Changes

### Redis 快取層（表級快取）

將整個 `DW_PJ_LOT_V` 表快取到 Redis，而非快取各 API 的查詢結果：

- **背景任務每 10 分鐘檢查** Oracle 的 `SYS_DATE`
- 僅在 `SYS_DATE` 有變化時，重新載入整個 `DW_PJ_LOT_V` 表存入 Redis
- 所有 WIP API 從 Redis 讀取完整資料，在 Python 層進行篩選/聚合計算
- Redis 不可用時自動 fallback 到直接查詢 Oracle

**優點**：
- 快取邏輯簡單 - 只需維護一份完整資料
- 資料一致性好 - 所有 API 使用同一份快取
- Oracle 查詢降至最低 - 只有背景任務會查詢

### Worker 穩定性強化

- 修復 SQLAlchemy 連接池缺少 `call_timeout` 的問題，確保查詢超時機制生效
- 強化 Gunicorn 配置，加入 `max_requests` 讓 worker 定期重啟，避免狀態累積
- 新增 `/health` 健康檢查端點，支援外部監控系統偵測服務狀態

## Capabilities

### New Capabilities

- `redis-cache`: WIP 表級快取層，包含：
  - 背景任務每 10 分鐘檢查 `SYS_DATE` 並載入完整 `DW_PJ_LOT_V` 表
  - Redis 資料讀取與 Python 層篩選/聚合
  - 降級機制（Redis 不可用時 fallback）
- `health-check`: 服務健康檢查端點，檢測資料庫和 Redis 連接狀態

### Modified Capabilities

- （無現有 specs 需要修改）

## Impact

### 快取架構

```
┌─────────────────────────────────────────────────────────────────┐
│                      表級快取流程                                 │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  cache_updater (背景任務，每 10 分鐘執行)                          │
│      │                                                           │
│      ├─1─▶ SELECT MAX(SYS_DATE) FROM DW_PJ_LOT_V                │
│      │                                                           │
│      ├─2─▶ 比對 Redis 中的 mes_wip:meta:sys_date                 │
│      │                                                           │
│      └─3─▶ 如有變化：                                            │
│            SELECT * FROM DW_PJ_LOT_V → 存入 Redis                │
│                                                                  │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  API 請求處理                                                     │
│      │                                                           │
│      ├─1─▶ 從 Redis 讀取 mes_wip:data (完整表資料)               │
│      │                                                           │
│      ├─2─▶ Python (pandas) 進行篩選/聚合                         │
│      │                                                           │
│      └─3─▶ 回傳計算結果                                          │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

### 需要修改的 API 端點

以下 API 都查詢 `DWH.DW_PJ_LOT_V`，需要改為從 Redis 讀取後計算：

| 路由 | 服務函數 | 說明 |
|------|---------|------|
| `/api/wip/overview/summary` | `get_wip_summary()` | WIP 摘要 KPI |
| `/api/wip/overview/matrix` | `get_wip_matrix()` | 工作中心 × 產品線矩陣 |
| `/api/wip/overview/hold` | `get_wip_hold_summary()` | Hold 摘要 |
| `/api/wip/detail/<workcenter>` | `get_wip_detail()` | 工作中心詳細批次 |
| `/api/wip/hold-detail/summary` | `get_hold_detail_summary()` | Hold 原因統計 |
| `/api/wip/hold-detail/distribution` | `get_hold_detail_distribution()` | Hold 分佈 |
| `/api/wip/hold-detail/lots` | `get_hold_detail_lots()` | Hold 批次清單 |
| `/api/wip/meta/workcenters` | - | 工作中心清單 |
| `/api/wip/meta/packages` | - | 產品線清單 |
| `/api/wip/meta/search` | - | 搜尋批次/工單 |

**相關檔案**：
- `src/mes_dashboard/services/wip_service.py` - 主要查詢邏輯（需重構為從 Redis 讀取）
- `src/mes_dashboard/services/filter_cache.py` - 工作中心群組快取
- `src/mes_dashboard/routes/wip_routes.py` - WIP API 路由
- `src/mes_dashboard/routes/hold_routes.py` - Hold API 路由

### 程式碼變更

| 檔案 | 變更類型 | 說明 |
|------|---------|------|
| `src/mes_dashboard/core/database.py` | 修改 | 為 SQLAlchemy 連接池加入 call_timeout |
| `src/mes_dashboard/core/redis_client.py` | 新增 | Redis 連接管理 |
| `src/mes_dashboard/core/cache.py` | 重寫 | 表級快取實作（取代現有的 NoOpCache） |
| `src/mes_dashboard/core/cache_updater.py` | 新增 | 背景任務：檢查 SYS_DATE 並載入整表 |
| `src/mes_dashboard/services/wip_service.py` | 重構 | 改為從 Redis 讀取 + pandas 計算 |
| `src/mes_dashboard/routes/health_routes.py` | 新增 | 健康檢查端點 |
| `gunicorn.conf.py` | 修改 | 加入 max_requests 配置 |

### 新增依賴

| 套件 | 版本 | 用途 |
|------|------|------|
| `redis` | >= 5.0 | Redis 客戶端 |
| `hiredis` | >= 2.0 | Redis 高效能解析器（可選） |

### 環境變數

| 變數 | 說明 | 預設值 |
|------|------|--------|
| `REDIS_URL` | Redis 連接字串 | `redis://localhost:6379/0` |
| `REDIS_ENABLED` | 是否啟用 Redis 快取 | `true` |
| `REDIS_KEY_PREFIX` | Redis key 前綴，區分不同專案/需求 | `mes_wip` |
| `CACHE_CHECK_INTERVAL` | 背景任務檢查 SYS_DATE 間隔（秒） | `600` (10分鐘) |

### Redis Key 命名規範

為區分此專案與其他需求，所有 Redis key 使用統一前綴：

| Key | 說明 |
|-----|------|
| `{prefix}:meta:sys_date` | 目前快取的 SYS_DATE 版本 |
| `{prefix}:meta:updated_at` | 快取更新時間 |
| `{prefix}:data` | 完整 DW_PJ_LOT_V 表資料（JSON 或 MessagePack） |

**範例**（prefix = `mes_wip`）：
```
mes_wip:meta:sys_date     → "2024-01-15 10:30:00"
mes_wip:meta:updated_at   → "2024-01-15 10:35:22"
mes_wip:data              → [完整表資料 JSON]
```

### 資料量評估

需確認 `DW_PJ_LOT_V` 的資料量：
- 預估筆數：待確認
- 預估大小：待確認（JSON 格式）
- Redis 記憶體需求：待確認

**建議**：實作前先執行 `SELECT COUNT(*) FROM DWH.DW_PJ_LOT_V` 確認筆數

### 基礎設施

#### Redis 安裝（Linux 直接安裝）

```bash
# Ubuntu/Debian
sudo apt update
sudo apt install redis-server

# 啟用並設定開機自動啟動
sudo systemctl enable redis-server
sudo systemctl start redis-server

# 驗證安裝
redis-cli ping  # 應回傳 PONG
```

**配置建議** (`/etc/redis/redis.conf`)：
```conf
# 綁定本機（如需遠端存取請調整）
bind 127.0.0.1

# 記憶體限制（依資料量調整，建議預留 2x 快取大小）
maxmemory 512mb
maxmemory-policy allkeys-lru

# 持久化（可選，快取資料可不持久化）
save ""
appendonly no
```

#### 為何不使用 Docker

- 減少額外的容器管理複雜度
- 直接安裝效能較佳（無容器網路開銷）
- 與現有 Linux 環境整合更簡單
- 適合單一用途的快取服務
