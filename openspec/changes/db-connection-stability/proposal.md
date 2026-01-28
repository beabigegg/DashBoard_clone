# DB Connection Stability 提案

## 問題描述

目前資料庫連線架構存在以下問題，導致「看起來像連線不穩」的現象：

### 1. 無連線池化（NullPool）
- 每次查詢都建立新連線
- 高併發時造成連線風暴
- 容易碰到 Oracle listener/SESSION 限制

### 2. 併發放大效應
- Gunicorn 2 workers × 4 threads
- 前端同頁多 API 並行請求 + 定時刷新
- 短時間大量新連線

### 3. 超時設定問題
- Gunicorn worker timeout 60s
- 前端 fetch 超時 60s
- 查詢稍慢就會被中止，呈現 500/請求中斷

### 4. 密碼 URL 編碼問題
- CONNECTION_STRING 未對密碼做 URL encode
- 若密碼含 `@:/?#` 等特殊字元會被誤解析

### 5. 錯誤紀錄不足
- 連線失敗用 `print()` 而非 logging
- 錯誤不一定進入 error.log

## 解決方案

### Phase 1: 結構化錯誤紀錄（低風險）
- 將所有 `print()` 改為 `logging`
- 記錄 ORA error code
- 加入查詢時間統計

### Phase 2: 連線池化（中風險）
- 改用 SQLAlchemy QueuePool
- 設定合理的 pool_size 和 max_overflow
- 加入 pool_pre_ping 健康檢查

### Phase 3: 重試策略優化（低風險）
- 增加 query-level retry
- 針對特定 ORA 錯誤碼進行重試

## 影響範圍

- `src/mes_dashboard/config/database.py` - 密碼 URL 編碼
- `src/mes_dashboard/core/database.py` - 連線池、logging、重試
- 所有使用 `read_sql_df()` 的 service

## 風險評估

- Phase 1: 低風險，僅增加 logging
- Phase 2: 中風險，需測試連線池行為
- Phase 3: 低風險，僅增加重試邏輯
