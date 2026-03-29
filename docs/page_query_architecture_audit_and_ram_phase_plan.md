# Page Query Architecture Audit And RAM Phase Plan

> 日期：2026-03-29（Phase 0 完成：2026-03-29）
>
> 範圍：對照 `docs/page_query_architecture.md` 與目前 repo 實作，並提出一個以降低 RAM 為目標的分階段落地方案。
>
> 註：你提到的 `ARROR`，本文先按 `Arrow/Parquet` 解讀。以這個專案現況來看，建議落地形式是 `RQ -> Arrow/Parquet spool -> DuckDB`，不是把大型 Arrow payload 長時間放進 Redis。
>
> **Phase 進度：**
> - [x] Phase 0 — 基線量測 → 完成，詳見 `docs/phase0_baseline_assessment.md`
> - [x] Phase 1 — hot cache 整理 → 實作完成 (2026-03-29)，commit `77e6819`，提案封存於 `openspec/changes/archive/2026-03-29-phase1-hot-cache-normalization/`
> - [ ] Phase 2 — heavy dataset metadata-only Redis
> - [ ] Phase 3 — 重查詢 primary query 全部先落 spool
> - [ ] Phase 4 — 對外語意分兩類
> - [ ] Phase 5 — 退休 pandas heavy fallback

---

## 1. 結論先講

`docs/page_query_architecture.md` 比較像「目前已做 + 近期目標架構」的混合文件，不是完全等同於 repo 當下 runtime reality。

整體方向沒有錯，尤其是：

- 即時域走 Redis / process cache
- 歷史大查詢走 spool + DuckDB
- RQ 承接高成本非同步查詢

但文件裡有幾個明顯不準、過時、或把「設計目標」寫成「已完全落地」的地方。若你接下來要用它當重構基準，建議先把它視為參考，不要直接當事實來源。

---

## 2. 已確認的文件落差

### 2.1 `/` 不是首頁 Dashboard，而是 portal 入口

文件寫：

- 4.1 首頁 Dashboard
- 路由 `/`

實際上：

- `src/mes_dashboard/app.py` 的 `/` 是 `portal_index()`
- `PORTAL_SPA_ENABLED=true` 時會導向 `/portal-shell`
- repo 內沒有對應的 `frontend/src/dashboard`

判斷：

- 這一段是明顯不準
- Dashboard API 存在，但 `/` 並不是文件描述的 dashboard page

### 2.2 `production-history` 有 API 與前端頁面，但我目前沒找到 Flask page route

文件寫：

- 4.11 生產歷程查詢
- 路由 `/production-history`
- 狀態 `released`

實際上：

- `src/mes_dashboard/routes/production_history_routes.py` 只有 API
- `frontend/src/production-history` 存在
- `src/mes_dashboard/app.py` 與 `src/mes_dashboard/routes/` 目前沒看到 `/production-history` page route

判斷：

- 若 runtime 是靠 portal shell 內部路由承接，文件至少也該註明
- 若不是，這裡就是文件高估了實際落地狀態

### 2.3 Hold Overview 不是單純「WIP subset」

文件寫：

- 4.4 Hold 即時概況
- `/api/hold-overview/*` 走 `wip_service` 的 hold subset

實際上：

- `src/mes_dashboard/routes/hold_overview_routes.py` 是獨立 page + API route
- API 包含 `summary` / `matrix` / `treemap` / `lots`
- 內部同時用到 `wip_service.get_wip_matrix()`、`get_hold_detail_summary()`、`get_hold_overview_treemap()`、`get_hold_detail_lots()`

判斷：

- 文件簡化過頭
- 這頁不是單純 WIP overview 的一個薄薄子集

### 2.4 Resource History 還沒真正做到「主流程已完全脫離 in-memory pandas」

文件寫：

- `POST /api/resource/history/query` 主路徑是 DuckDB canonical spool，fallback 才進 Oracle
- `GET /view` 是 DuckDB SQL runtime，fallback 才 pandas

實際上：

- `src/mes_dashboard/routes/resource_history_routes.py` 的確先嘗試 `try_compute_query_from_canonical_spool()`
- 但 miss 後仍進 `resource_dataset_cache.execute_primary_query()`
- `src/mes_dashboard/services/resource_dataset_cache.py` 在 spool path 下仍會 `load_spooled_df()` 回 pandas，再做 `_derive_summary()` / `_derive_detail()`

判斷：

- 目前比較像「先試 canonical spool reuse，失敗則同步查詢並在 server 端做 pandas 衍生」
- DuckDB 路徑已存在，但還不是全域唯一主路

### 2.5 重查詢域並沒有真的「其餘一律 async」

文件中把一些頁面寫成已經高度統一，但實際上：

- `reject-history`：新 API spool miss 會走 RQ + 202，這點成立
- `material-trace`：spool miss 會走 RQ + 202，這點成立
- `mid-section-defect`：detail/export 走 spool miss -> 409 + background job，這點成立
- `hold-history`：仍是同步 `POST /query`
- `yield-alert`：仍是同步 `POST /query`
- `resource-history`：仍是同步 `POST /query`
- `production-history`：仍是同步 `POST /query`

判斷：

- 文件描述的方向對，但「統一 async」尚未成真

### 2.6 共用快取層定義過度理想化，實作其實不一致

文件寫：

- L1 Process 可視為統一層
- L2 Redis 15min 左右
- filter cache 是 30min
- resource cache 是 L1 30s + L2 Redis 15min

實際上：

- `wip` 使用 `core/cache.py` 的 `ProcessLevelCache`
- `resource_cache`、`realtime_equipment_cache` 各自有自製 `_ProcessLevelCache`
- `filter_cache` / `container_filter_cache` / `reason_filter_cache` 目前 TTL 已是 24 小時
- `resource_cache` / `realtime_equipment_cache` 寫 Redis 時沒有明確 TTL，偏向版本/同步驅動，不是 15min
- `wip` 還有 JSON + parquet 雙份 Redis 表示

判斷：

- 文件中的 cache layer summary 不能直接視為 runtime truth
- 現況是多套 cache strategy 並存

### 2.7 6.5 的異步任務對照表有一項對錯服務

文件寫：

- `trace_job_service` 是 Material trace 異步 wrapper

實際上：

- Material trace route 直接使用 `async_query_job_service.enqueue_job()`
- worker function 來自 `material_trace_service.rq_material_trace_job`
- `trace_job_service` 對應的是 `/api/trace/*` 那組 trace events / lineage job

判斷：

- 這一段映射有誤

### 2.8 6.4 的 filter cache 資訊有兩處不準

文件寫：

- `filter_cache` TTL 30min
- `reason_filter_cache` 是 Redis SET

實際上：

- `CACHE_TTL_FILTER_GENERAL = 86400`
- `filter_cache` / `container_filter_cache` / `reason_filter_cache` 都已走 24h
- `reason_filter_cache` 目前是 JSON payload 寫 Redis，不是 Redis SET 結構

判斷：

- 文件需要更新

---

## 3. 對「Redis 存熱資料，其餘走 RQ -> Arrow/Parquet -> DuckDB」的評估

## 3.1 方向是對的，但要收斂成「Redis 存小而熱，spool 存大而重」

我同意大方向，但不同意把它理解成：

- 大資料也放 Redis，只是格式從 DataFrame 變 Arrow

這樣只會把 gunicorn RAM 壓力轉移成 Redis RAM 壓力。

比較正確的切法應該是：

- Redis：熱資料、小資料、metadata、job status、cross-worker lookup
- Arrow/Parquet spool：大查詢結果
- DuckDB：所有大資料的 view/page/filter/sort/export 計算
- RQ：把高成本 Oracle 查詢與 spool 寫入移出 gunicorn request path

## 3.2 哪些應該留在 Redis

建議保留在 Redis 的資料：

- WIP 即時快照
- realtime equipment status
- resource master / resource lookup / cascade metadata
- filter caches
- job metadata / polling status
- spool metadata
- distributed locks / leader locks

但要注意兩件事：

- 熱資料盡量只保留單一 canonical 表示，不要 JSON + parquet 雙存
- gunicorn 的 L1 process cache 要縮小，不要讓每個 worker 都長時間持有大型副本

## 3.3 哪些不該再放 Redis 大 payload

建議逐步移出 Redis 大 payload 的域：

- reject-history dataset
- hold-history dataset
- yield-alert dataset
- resource-history dataset
- production-history dataset
- material-trace 結果集
- MSD staged result

這些域的 Redis 應該只保留：

- dataset/job id
- params hash
- spool path / namespace
- row_count / column hash / created_at / ttl
- progress / error / retry info

## 3.4 「其餘一律走 RQ」也要留例外

不建議硬把下面這些也改成 RQ 主路徑：

- QC-GATE summary
- job-query 單次窄範圍查詢
- query-tool resolve / lot-history / 局部 lookup
- WIP detail / hold-detail 這種使用者期待即時互動的輕量查詢

理由：

- RQ 會引入排隊延遲與更複雜的 UX
- 這些查詢的瓶頸通常不是「大資料集衍生計算」
- 它們更像低延遲互動 API，不是報表批次查詢

所以更好的原則是：

- 即時互動、窄查詢、回應量小：同步
- 大日期範圍、可重用 dataset、後續會有 view/page/export：RQ + spool + DuckDB

## 3.5 這個專案最該優先打的 RAM 痛點

若目標是「先明顯壓 RAM」，優先順序我建議是：

1. 停止在 gunicorn request path 載入大型 spooled DataFrame 再做 pandas 衍生
2. 停止在 Redis 長期保存大型 dataset payload
3. 消除同一資料的雙重或三重表示
4. 降低 worker 內 L1 cache 的複本數
5. 讓 heavy query 主要在 RQ worker 執行，且 RQ pool 維持小 DB pool

---

## 4. 建議的目標架構

### 4.1 即時域

```
Browser
  -> Flask route
  -> Redis hot cache
  -> optional tiny L1 process cache
  -> Oracle fallback / periodic updater
```

適用：

- WIP overview / detail / hold detail
- resource status
- filter options
- job-query resources

### 4.2 歷史重查詢域

```
Browser
  -> Flask route
  -> Redis metadata hit?
      -> YES: use existing spool id
      -> NO: enqueue RQ job

RQ worker
  -> chunked Oracle query
  -> Arrow/Parquet spool write
  -> Redis metadata update

Browser / Flask / Frontend DuckDB-WASM
  -> DuckDB over Parquet spool
```

適用：

- reject-history
- hold-history
- yield-alert
- resource-history
- production-history
- material-trace
- mid-section-defect

---

## 5. Phase 拆分建議

## Phase 0: 先把基線量清楚 ✅ 完成 (2026-03-29)

> 詳細盤點結果：`docs/phase0_baseline_assessment.md`

目標：

- 不先改架構，先量出記憶體熱點與資料流

### Phase 0 結論：RAM 主要被三類資料吃掉

1. **大型 dataset Redis payload** — reject/hold/resource/yield-alert 的完整 DataFrame 以 Parquet+base64 存入 Redis（每筆 5–100 MB），同時在 L1 ProcessLevelCache 中保留最多 3 份副本 × N workers。Redis 尖峰估算 200–400 MB。
2. **WIP JSON + Parquet 雙重表示** — WIP 資料在 Redis 同時有 JSON (`mes_wip:data`, 14+ MB) 和 Parquet (`mes_wip:data:parquet`, ~10 MB) 兩份，每個 worker 的 L1 cache 還各持一份 parsed DataFrame。
3. **gunicorn request path 載入 spooled DataFrame 做 pandas 衍生** — hold/resource/reject/yield-alert 的 view 路徑在 DuckDB SQL runtime 失敗時，fallback 把整個 spool parquet 載回 pandas，造成瞬間 RSS spike。

### Phase 0 各頁面分類表

| 分類 | 頁面 |
|------|------|
| **hot-cache** | WIP overview/detail, Hold overview, Resource status, Equipment status, Filter options |
| **sync-direct** | QC-Gate, Job query, Analytics |
| **dataset-spool (async RQ)** | reject-history, material-trace, MSD, trace events/lineage |
| **dataset-spool (sync query → DuckDB-only view)** | production-history ⭐ 唯一完全不走 pandas fallback |
| **dataset-spool (sync query → DuckDB + pandas fallback)** | hold-history, resource-history, yield-alert |
| **dataset-spool (sync + DuckDB pagination)** | query-tool |

### Phase 0 關鍵發現

- **Cache 策略不一致**：`resource_cache` / `realtime_equipment_cache` 各自有 `_ProcessLevelCache`（自製），與 `core/cache.py` 的共用版本不同
- **dataset cache L1 max_size=3**：4 workers × 4 域 × 3 entries = 最多 48 份大型 DataFrame 常駐記憶體
- **resource_cache / equipment_status_cache Redis 端無 TTL**：若 updater 停止，舊資料永不過期
- **production-history 可作為改造參考模型**：它的 page/matrix/options/export 路由全部走 DuckDB on spool，無 pandas fallback

### Phase 0 Telemetry 覆蓋度

已有（~70%）：gunicorn RSS + memory guard, Redis used_memory, Redis 全局 hit/miss, process cache registry stats, route cache L1/L2, DB pool, query p50/p95/p99, circuit breaker, RQ worker status

缺少：
- RQ worker RSS
- 各 cache per-namespace hit/miss counter
- 各 spool namespace 磁碟用量
- per-page query/view/export latency
- per-namespace Redis memory 估算

## Phase 1: 先整理 hot cache，不碰重查詢 contract

> **狀態：✅ 實作完成 (2026-03-29)，commit `77e6819`**
> openspec 封存於 `openspec/changes/archive/2026-03-29-phase1-hot-cache-normalization/`
> 實作任務追蹤：`openspec/changes/archive/2026-03-29-phase1-hot-cache-normalization/tasks.md`
>
> **實作結果（6 工作群組全數完成）：**
> - Group 1：WIP cache Parquet-only — `cache_updater.py` 移除 JSON 路徑，`cache.py` 移除 JSON fallback
> - Group 2：Dataset L1 max_size→1 — `hold/reject/resource_dataset_cache.py`（3→1），`yield_alert_dataset_cache.py`（2→1）
> - Group 3：Redis TTL EX 300 — `resource_cache.py` pipeline、`realtime_equipment_cache.py` pipeline
> - Group 4：Spool 磁碟用量 telemetry — `admin_routes.py` 新增 `spool_disk_usage`
> - Group 5：Redis namespace 記憶體 telemetry — `admin_routes.py` 新增 `redis_namespace_memory`（6 namespace）
> - Group 6：Validation — pytest 49 passed，2 pre-existing failures（`TestWarmupTasks`，與 Phase 1 無關）

目標：

- 先把即時域收斂，拿最小風險收益

工作（依 Phase 0 盤點結果具體化）：

- **1.1 WIP cache 改成單一 canonical 表示**
  - ✅ 現況確認：Redis 同時存 `mes_wip:data` (JSON, 14+ MB) + `mes_wip:data:parquet` (Parquet+base64, ~10 MB)
  - `core/cache.py:470–486` 先試 parquet，fallback JSON
  - 動作：保留 Parquet，移除 JSON 路徑（`cache_updater.py` 停止寫 JSON；`cache.py` 移除 JSON fallback）
  - 預估收益：Redis -14 MB，parse 路徑簡化
  - 實作位置：`cache_updater.py:280`（移除 JSON rename）、`cache.py:481-486`（移除 fallback）

- **1.2 dataset cache L1 max_size 縮小**
  - ✅ 現況確認：reject/hold/resource 各 `max_size=3`，yield-alert `max_size=2`
  - 4 workers × (3+3+3+2) = 最多 44 份大型 DataFrame 常駐記憶體
  - 動作：全部壓到 `max_size=1`
  - 預估收益：每 worker 最多從 11 份降到 4 份
  - 實作位置：`reject_dataset_cache.py:82`、`hold_dataset_cache.py:46`、`resource_dataset_cache.py:37`、`yield_alert_dataset_cache.py:61`

- **1.3 resource_cache / realtime_equipment_cache Redis 加 TTL**
  - ✅ 現況確認：兩者 Redis 端無 TTL，依賴版本同步
  - 動作：加 `EX 300`，updater 正常時不會過期，updater 停止時 5 分鐘後自動清除
  - 實作位置：`resource_cache.py:587–592` pipeline、`realtime_equipment_cache.py:357–364` pipeline

- **1.4 filter cache**（Phase 1 不動）
  - ✅ 現況確認：filter/container_filter/reason_filter 都已是 Redis 24h，無 L1 mirror，parse 開銷可接受
  - 動作：維持現狀，不納入 Phase 1

- **1.5 補齊 Phase 0 缺少的 telemetry（低風險項）**
  - spool namespace 磁碟用量 → 擴充 `/admin/api/performance-detail`，新增 `spool_disk_usage` 陣列
  - per-namespace Redis memory 估算 → 新增 `redis_namespace_memory` 陣列（`MEMORY USAGE` 抽樣，500ms timeout）

不做：

- 不改前端 API contract
- 不把 WIP / resource status 改成 RQ

完成條件：

- 即時頁面功能不變
- Gunicorn RSS 下降（L1 max_size 壓縮 + WIP 單存）
- Redis hot cache schema 明確化（WIP 單一表示、resource/equipment 有 TTL）

## Phase 2: 建立 heavy dataset 的 metadata-only Redis 模型

目標：

- 讓 Redis 不再承擔大型 dataset 本體

工作（依 Phase 0 盤點結果具體化）：

- **2.1 需轉換的域（目前仍有大型 Redis payload）：**

  | 域 | 目前 Redis 格式 | Redis TTL | 預估大小 |
  |---|----------------|-----------|---------|
  | reject-history | Parquet+base64 (`reject_dataset_cache.py:191`) | 15min | 10–100 MB |
  | hold-history | Parquet+base64 (`hold_dataset_cache.py:90`) | 15min | 5–50 MB |
  | resource-history | Parquet+base64 (`resource_dataset_cache.py:76`) | 15min | 5–20 MB |
  | yield-alert | Parquet+base64 (`yield_alert_dataset_cache.py:499`) | 5min | 5–50 MB |
  | batch chunks | Parquet+base64 (`batch_query_engine.py`) | 15min | 1–10 MB/chunk |

- **2.2 已有 metadata-only 模式的域（可作參考）：**
  - `query_spool_store.py` 已有 `spool_meta:{query_id}` 結構（schema_version, namespace, relative_path, row_count, columns_hash, created_at, expires_at, file_size_bytes）
  - production-history 已完全走 spool metadata → DuckDB，不存大型 Redis payload

- **2.3 不需轉換的域（已是 metadata-only 或資料量小）：**
  - material-trace：spool + DuckDB，Redis 只存 job metadata
  - MSD：spool + DuckDB，Redis 只存 job metadata
  - trace events/lineage：spool + job metadata

- Redis 統一只存：
  - dataset_id / params_hash / namespace / spool path
  - row_count / columns_hash / created_at / expires_at
  - status / progress / error
- 先保留現有 Redis DataFrame 路徑作 compatibility fallback，但新路徑預設不再寫入大型 payload

完成條件：

- reject/hold/resource/yield-alert 能只靠 metadata 找到 spool
- 新舊路徑可以並行切換（feature flag）
- 預估 Redis peak 從 200–400 MB 降至 50–100 MB

## Phase 3: 讓重查詢 primary query 全部先落 spool

目標：

- 把最大 RAM 壓力從 gunicorn request thread 搬出去

工作（依 Phase 0 盤點結果具體化）：

> 參考模型：`production-history` — 它的 page/matrix/options/export 路由全部走 DuckDB on spool，無 pandas fallback

- **3.1 `resource-history`**（Phase 0 分類：sync query → DuckDB + pandas fallback）
  - 現況：`try_compute_query_from_canonical_spool()` → miss 後走 `resource_dataset_cache.execute_primary_query()` → `load_spooled_df()` 回 pandas 做 `_derive_summary()` / `_derive_detail()`
  - 已有 DuckDB runtime：`resource_history_sql_runtime.py`
  - 動作：移除 view path 的 `load_spooled_df` fallback，讓 DuckDB runtime 成為唯一 view 路徑
  - fallback 位置：`resource_dataset_cache.py:278` `_loaded = load_spooled_df(...)`

- **3.2 `hold-history`**（Phase 0 分類：sync query → DuckDB + pandas fallback）
  - 現況：`apply_view()` 先試 `hold_history_sql_runtime.try_compute_view_from_spool()`，失敗後走 `_get_cached_df()` → `load_spooled_df()` → pandas `_derive_all_views()`
  - 已有 DuckDB runtime：`hold_history_sql_runtime.py`
  - 動作：同 3.1 模式
  - fallback 位置：`hold_dataset_cache.py:337`

- **3.3 `yield-alert`**（Phase 0 分類：sync query → DuckDB + pandas fallback）
  - 現況：`apply_view()` 走 DuckDB first，失敗後 `pd.read_parquet(spool_path)` 回 pandas
  - 已有 DuckDB runtime：`yield_alert_sql_runtime.py` + 內建 DuckDB
  - 動作：同 3.1 模式
  - fallback 位置：`yield_alert_dataset_cache.py:628`

- **3.4 `reject-history`**（Phase 0 分類：async RQ + DuckDB + pandas fallback）
  - 保留 async miss → 202
  - 逐步移除 `reject_dataset_cache.py:340` 的 `load_spooled_df` fallback
  - 已有 DuckDB runtime：`reject_cache_sql_runtime.py`

- **3.5 `production-history`** ✅ 已達標
  - 維持現有 spool + DuckDB 主幹，不需改動

完成條件：

- hold/resource/yield-alert/reject 的 view path 不再需要 `load_spooled_df` → pandas 衍生
- DuckDB SQL runtime 成為所有歷史域的唯一 view engine

## Phase 4: 對外語意再分兩類，不強求全部同一 UX

目標：

- 技術架構統一，但外部 UX/contract 依頁面特性決定

分法：

- 類型 A：保留同步 bootstrap
  - `resource-history`
  - `hold-history`
  - `yield-alert`
  - `production-history`
- 類型 B：miss 時直接 async + polling
  - `reject-history`
  - `material-trace`
  - `MSD`

原因：

- 這比較符合現在前端與使用者操作心智
- 不需要為了「統一」而把所有頁面都改成 202 polling

完成條件：

- 重查詢域內部都已經是 spool-first
- 但前端 contract 不必同一天全部切掉

## Phase 5: 退休 pandas heavy fallback 與舊大 payload 路徑

目標：

- 真正把 RAM 成本從設計上移除

工作：

- 對已穩定的域移除：
  - Redis 大型 DataFrame 寫入
  - `load_spooled_df()` 後再做大範圍 pandas 衍生
  - 已無人使用的 legacy fallback
- 保留：
  - DuckDB runtime
  - frontend DuckDB-WASM 適用頁面
  - Redis job/spool/filter metadata

完成條件：

- 歷史報表域的 server-side pandas 只剩 compatibility emergency fallback

---

## 6. 建議實作順序

如果你要一步一步做，我建議順序是：

1. ~~Phase 0~~ ✅ 完成 — `docs/phase0_baseline_assessment.md`
2. Phase 1 — hot cache 整理（WIP 單存、L1 max_size 縮小、Redis TTL）
3. Phase 2 — heavy dataset metadata-only Redis
4. Phase 3 先切 `resource-history`（已有 `resource_history_sql_runtime.py`，最接近 production-history 模式）
5. Phase 3 再切 `hold-history`（已有 `hold_history_sql_runtime.py`）
6. Phase 3 再切 `yield-alert`（已有 `yield_alert_sql_runtime.py`）
7. Phase 3 最後整理 `reject-history`（已有 async + `reject_cache_sql_runtime.py`，移除 pandas fallback）
8. `production-history` / `material-trace` / `MSD` — ✅ 已達標或接近達標，不需大改

原因：

- Phase 0 盤點確認 `resource-history`、`hold-history`、`yield-alert` 三者都已有 DuckDB SQL runtime 但仍有 pandas fallback，是最大 RAM spike 來源
- `production-history` 已是完全 DuckDB-only 模式，可作為改造範本
- `material-trace` / `MSD` 已是 async + DuckDB，不構成 gunicorn RSS 壓力

---

## 7. 我對最終策略的建議版本

最終建議不是：

- `WIP/resource/filter 放 Redis，其餘全部 Redis miss -> RQ -> Arrow`

而是：

- `WIP/resource/filter/job-meta/spool-meta 放 Redis`
- `大結果集不放 Redis，只放 spool metadata`
- `重查詢統一收斂到 RQ -> Arrow/Parquet spool -> DuckDB`
- `只有真的需要低延遲首屏的頁面保留同步 bootstrap`

換句話說，真正要壓 RAM 的關鍵不是「多用 Redis」，而是：

- 不要在 gunicorn 和 Redis 裡同時保留大型資料副本
- 讓大型結果盡快變成 spool + metadata
- 讓 view/filter/page/export 都只碰 DuckDB

---

## 8. 這份文件可直接拿來當後續實作 checklist

Phase 0 已完成。若接下來要進入實作，建議依以下分組推進：

| 分組 | 範圍 | 風險面 | 參考文件 |
|------|------|--------|---------|
| **Phase 1** | hot cache normalization | 低風險，不改 API contract | 本文 Phase 1 + `phase0_baseline_assessment.md` §2 |
| **Phase 2–3** | dataset metadata + spool-first runtime | 中風險，需 feature flag 並行切換 | 本文 Phase 2–3 + `phase0_baseline_assessment.md` §4 |
| **Phase 4–5** | contract migration + legacy retirement | 高風險，需前後端協調 | 本文 Phase 4–5 |

這樣你可以一次只處理一個風險面，不會把 WIP 即時頁、歷史報表頁、RQ worker、frontend contract 一次綁在同一個大改動裡。
