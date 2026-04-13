## Context

Admin Dashboard SPA 中 WorkerTab 與 LogsTab 各自管理一部份 log：
- WorkerTab `儲存空間管理` 區塊呼叫 `/admin/api/log-files/cleanup` 清空 `logs/*.log` 與 `logs/archive/`。
- LogsTab 呼叫 `/admin/api/logs/cleanup` 清空結構化 log（`admin_logs.sqlite` + MySQL `dashboard_logs`）。

兩個入口名稱（「清空 Log 檔案」vs「清理日誌」）對使用者不易區分；同時後端 `api_logs` 用 `str(timestamp)` 排序合併資料，因 SQLite ISO `T` 與 MySQL DATETIME 空白格式不同，跨來源排序會錯亂。前端 LogsTab 顯示 raw timestamp、WorkerTab 用 `toLocaleString('zh-TW')`，整體不一致。

相關檔案：
- `frontend/src/admin-dashboard/tabs/LogsTab.vue`
- `frontend/src/admin-dashboard/tabs/WorkerTab.vue` (lines 413-479 為儲存區塊)
- `src/mes_dashboard/routes/admin_routes.py` (`api_logs` 248-293, `_query_mysql_logs` 296-329, `api_log_files_cleanup` 750-800, `api_logs_cleanup` 803-)
- `src/mes_dashboard/core/log_store.py` (`write_log` 175-235)

## Goals / Non-Goals

**Goals:**
- LogsTab 成為 admin dashboard 唯一的 log 檢視/管理入口，涵蓋結構化 logs、`.log` 檔、`archive/`。
- WorkerTab 專注於 worker/記憶體/RQ/效能快照，不再顯示或清理任何 `.log` / archive。
- 後端 log timestamp 統一序列化為 UTC ISO 8601（含 `+00:00`），跨來源合併排序正確。
- 前端時間顯示用單一共用 formatter（本地時區、`zh-TW`、24 小時制）。

**Non-Goals:**
- 不修改 `/admin/api/log-files/cleanup`、`/admin/api/logs/cleanup` 兩個 endpoint 的 request/response 契約。
- 不對既有 `admin_logs.sqlite` 資料做 migration。
- 不變更 MySQL `dashboard_logs` 表結構。
- 不調整 RQ worker `birth_date` 顯示（已是 `formatUptime()` 算 duration，不屬於本變更）。
- 不重新設計 LogsTab 的 filter/分頁互動（保持現有）。

## Decisions

### D1. 後端 log timestamp 一律 UTC ISO 8601
- **決策**：`log_store.write_log()` 改用 `datetime.now(timezone.utc).isoformat()`。讀路徑（`query_logs`、`query_logs_all`、`_query_mysql_logs`）回傳前用 helper `_normalize_iso_to_utc(value)` 把任意輸入（naive str、aware str、`datetime` 物件）轉為 `YYYY-MM-DDTHH:MM:SS.ffffff+00:00`。
- **理由**：避免讓前端猜測來源時區；單一格式才能正確排序。
- **替代方案**：後端輸出本地時區 ISO（含 `+08:00`）。被否決，因為跨機器/容器時區設定不一定一致，且未來若導入分散式服務會更亂。

### D2. 既有 naive 資料的處理
- **決策**：讀取時若字串不含時區資訊（無 `+`、無 `Z`），假設是「伺服器當前本地時區」（用 `datetime.now().astimezone().tzinfo` 取 offset）後轉 UTC。
- **理由**：使用者選擇「不處理舊資料」；保留簡單 fallback 以免與新資料時間軸出現巨大跳躍。
- **風險**：若伺服器曾跨時區搬遷或未來 OS 時區改變，舊資料時間會與當時實際略有偏差；可接受。

### D3. 合併排序用 datetime 物件
- **決策**：`api_logs` 合併 SQLite + MySQL 後，sort key 改為 `datetime.fromisoformat(r["timestamp"])`，無法解析則 fallback 到 `datetime.min`。
- **理由**：修掉現有 `str()` 比較 bug（SQLite `T` 字元 ASCII > 空白，導致同分鐘 SQLite log 永遠排在 MySQL 之後）。

### D4. 前端共用 formatter 位置
- **決策**：在 `frontend/src/core/datetime.js`（無此檔則新建，有則擴充）匯出 `formatLogTime(iso)`，使用 `Intl.DateTimeFormat('zh-TW', { hour12:false, year/month/day/hour/minute/second:'2-digit' })` 並 cache 一個 formatter instance。
- **理由**：避免每個 component 各自呼叫 `toLocaleString` 用不同 options；`core/` 是現有共用層放置處。
- **替代方案**：放在 `shared-ui/`。被否決，因為 shared-ui 是 component 層，純函式工具屬於 core。

### D5. WorkerTab 仍保留 `useStorageInfo()`
- **決策**：WorkerTab 仍呼叫 `useStorageInfo()`，但只渲染 `sqlite_files` DataTable（為了 `metrics_history.sqlite` 的「清除快照」按鈕與整體存量可視化）。
- **理由**：`metrics_history.sqlite` 屬於效能快照，與 worker 效能監控同類；移到 LogsTab 不合理。LogsTab 也獨立呼叫 `useStorageInfo()` 取得 `log_files` / `archive_files`。
- **替代方案**：把 `useStorageInfo()` 拆成兩個 endpoint。被否決，現有 endpoint 已能滿足，拆分只增加複雜度。

### D6. 不引入新 API
- **決策**：保留 `/admin/api/log-files/cleanup` 與 `/admin/api/logs/cleanup` 兩個 endpoint，不合併。
- **理由**：兩者作用對象本質不同（檔案系統 vs SQLite 寫入），合併會讓 request body 更複雜且影響既有契約。前端整合到同一頁即可解決使用者混淆問題。

## Risks / Trade-offs

- **舊資料時區假設可能偏差** → 在 LogsTab 顯示「歷史資料時區為估算值」？決定不顯示，避免雜訊；release notes 提及即可。
- **`Intl.DateTimeFormat` 在極舊瀏覽器不支援** → 專案目標瀏覽器為現代 Chromium/Firefox，可接受。
- **WorkerTab 使用者習慣改變** → 在第一次 release 加 changelog/notice；按鈕位置變更為已知預期。
- **`datetime.fromisoformat` 對 Python <3.11 不接受 `Z` 後綴** → 統一輸出 `+00:00` 而非 `Z`，避免相容性問題。

## Migration Plan

1. 後端先上線：log_store 寫入改 UTC、`_query_mysql_logs` + `query_logs*` 加 normalize、`api_logs` 排序修正。部署後既有 SQLite naive 資料會被 read-side normalize，輸出格式立即一致。
2. 前端緊接著上線：新增 `formatLogTime`、LogsTab 接管 log 檔案/archive 區塊、WorkerTab 移除對應 SectionCard 區塊。
3. Rollback：兩部分皆為純粹邏輯/UI 變更，rollback 即回退 commit 即可，無資料遷移。

## Open Questions

- 無。
