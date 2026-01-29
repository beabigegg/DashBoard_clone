## Context

目前系統的 `DW_MES_RESOURCE` 設備主檔資料散佈在多個查詢中：

1. **filter_cache.py** - 獨立查詢 `RESOURCEFAMILYNAME` 供篩選器使用
2. **resource_service.py** - 與 `DW_MES_RESOURCESTATUS` JOIN 查詢即時狀態
3. **resource_history_service.py** - 與 `DW_MES_RESOURCESTATUS_SHIFT` JOIN 查詢歷史績效

每次使用者開啟頁面都需等待 Oracle 查詢，且多個功能重複查詢相同資料。

系統已有 WIP 快取機制（`cache_updater.py`），使用 Redis 儲存 `DW_PJ_LOT_V` 資料並以 `SYS_DATE` 作為版本識別。Resource 快取可沿用類似架構。

## Goals / Non-Goals

**Goals:**
- 將篩選後的 `DW_MES_RESOURCE` 全表（78 欄位）快取至 Redis
- 每 4 小時自動同步，以 `MAX(LASTCHANGEDATE)` 作為版本識別
- 提供統一 API 供各模組取用設備資料和篩選器選項
- 整合至現有 `CacheUpdater` 背景任務
- Redis 不可用時自動 fallback 到 Oracle

**Non-Goals:**
- 不修改 SQL JOIN 查詢邏輯（仍由 Oracle 執行 JOIN）
- 不快取 `DW_MES_RESOURCESTATUS` 或 `DW_MES_RESOURCESTATUS_SHIFT`（變動頻繁）
- 不實作即時同步（WebSocket / trigger）

## Decisions

### Decision 1: 新增獨立模組 `resource_cache.py`

**選擇**：建立新模組 `src/mes_dashboard/services/resource_cache.py`

**替代方案**：
- A) 擴充現有 `filter_cache.py` - 但該模組同時處理 WIP 和 Resource，職責不清
- B) 合併至 `wip_cache.py` - 但兩者資料來源和同步週期不同

**理由**：
- 職責單一：專門處理 Resource 設備主檔
- 易於測試：獨立模組可單獨測試
- 擴展性：未來可增加更多 Resource 相關功能

---

### Decision 2: 全表快取（78 欄位）

**選擇**：`SELECT * FROM DW_MES_RESOURCE WHERE <filters>`

**替代方案**：
- A) 只快取常用欄位（~15 欄位）- 約 2-3 MB
- B) 全表快取（78 欄位）- 約 10-18 MB

**理由**：
- 避免未來新增需求時需修改快取邏輯
- 10-18 MB 對 Redis 仍屬輕量（相較 WIP 可能數十 MB）
- 一次載入，多處使用

---

### Decision 3: 4 小時同步週期

**選擇**：`RESOURCE_SYNC_INTERVAL = 14400` 秒（4 小時）

**替代方案**：
- A) 1 小時 - 更即時但增加 Oracle 負載
- B) 24 小時 - 負載最低但延遲過長
- C) 事件驅動 - 需要額外 trigger 機制

**理由**：
- 設備主檔變動不頻繁（新機台、報廢等）
- 4 小時延遲對報表場景可接受
- 平衡即時性與資源消耗

---

### Decision 4: 使用 `MAX(LASTCHANGEDATE)` 作為版本識別

**選擇**：查詢 `SELECT MAX(LASTCHANGEDATE) FROM DW_MES_RESOURCE WHERE <filters>`

**替代方案**：
- A) 每次都全表同步 - 簡單但浪費資源
- B) COUNT(*) 比對 - 無法偵測更新
- C) CHECKSUM - Oracle 不原生支援

**理由**：
- 可偵測新增和更新
- 查詢效率高（索引欄位）
- 與 WIP 的 `SYS_DATE` 機制類似

---

### Decision 5: 整合至現有 CacheUpdater

**選擇**：擴充 `cache_updater.py`，新增 resource 同步邏輯

**替代方案**：
- A) 獨立背景任務 - 增加維護複雜度
- B) 使用 APScheduler - 引入新依賴

**理由**：
- 複用現有架構
- 統一快取管理
- 減少程式碼重複

---

### Decision 6: Python 端篩選 vs Redis 查詢

**選擇**：資料存為 JSON array，篩選在 Python 端執行

**替代方案**：
- A) 每筆資料獨立 key（`resource:{id}`）- 需多次 Redis 呼叫
- B) 使用 Redis Search - 需額外模組
- C) JSON array + Python 篩選 - 單次讀取，記憶體運算

**理由**：
- 資料量小（~5000 筆），全載入記憶體無壓力
- 單次 Redis 呼叫取得所有資料
- 篩選邏輯在 Python 端靈活可控

## Risks / Trade-offs

| 風險 | 緩解措施 |
|------|----------|
| **Redis 不可用** → 篩選器無法載入 | 實作 fallback 到 Oracle 直查；記錄 warning 日誌 |
| **新設備 4 小時內不顯示** → 使用者困惑 | 提供手動刷新 API；文件說明延遲機制 |
| **記憶體使用增加** → Redis 資源競爭 | 監控記憶體用量；資料壓縮（如需要） |
| **NOTES/RESOURCECOMMENTS 大欄位** → 浪費空間 | 實際填充率低（~40%）；可接受 |
| **JSON 解析效能** → 回應延遲 | 使用 orjson 加速；預估 <50ms |

## Migration Plan

### Phase 1: 新增模組（不影響現有功能）
1. 建立 `resource_cache.py` 模組
2. 實作 Redis 同步邏輯
3. 整合至 `CacheUpdater`
4. 新增單元測試

### Phase 2: 整合設備歷史績效
1. 修改 `resource_history_service.get_filter_options()`
2. 驗證型號篩選器功能

### Phase 3: 整合機台狀態報表
1. 修改 `resource_service.query_resource_filter_options()`
2. 驗證所有篩選器功能

### Phase 4: 清理
1. 移除 `filter_cache._load_resource_families()`
2. 更新 Health Check 端點

### Rollback Strategy
- 設定 `RESOURCE_CACHE_ENABLED=false` 可立即回退到 Oracle 直查
- 無資料遷移，回退無風險

## Open Questions

1. **是否需要 ID 索引？**
   - 目前設計為全表載入 + Python 篩選
   - 如果未來需要高頻 ID 查詢，可加入 Redis Hash 索引

2. **是否需要 API 強制刷新？**
   - 目前只有 `refresh_cache(force=True)` 內部方法
   - 可考慮新增 `/api/admin/cache/resource/refresh` 端點
