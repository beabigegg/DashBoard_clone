## Tasks

### Phase 1: 結構化錯誤紀錄

- [x] **修改 config/database.py - 密碼 URL 編碼**
  - 使用 `urllib.parse.quote_plus()` 編碼密碼
  - 防止特殊字元造成連線字串解析錯誤

- [x] **修改 core/database.py - 加入 logging**
  - 將所有 `print()` 改為 `logging.logger`
  - 設定 logger: `mes_dashboard.database`
  - 記錄連線成功/失敗事件

- [x] **加入查詢時間統計**
  - 在 `read_sql_df()` 加入計時
  - 標記 >1s 查詢為 WARNING（慢查詢）
  - 正常查詢記錄為 DEBUG

- [x] **加入 ORA 錯誤碼擷取**
  - 從例外訊息擷取 ORA-XXXXX
  - 錯誤訊息包含錯誤碼便於追蹤

- [x] **配置 logging handler**
  - 在 app.py 加入 `_configure_logging()` 函數
  - 設定 `mes_dashboard` logger 輸出至 stderr
  - Gunicorn `--capture-output` 會將 stderr 導向 error.log

### Phase 2: 連線池化

- [x] **將 NullPool 改為 QueuePool**
  - pool_size=5（基本連線數）
  - max_overflow=10（尖峰額外連線）
  - pool_timeout=30（等待連線超時）
  - pool_recycle=1800（30 分鐘回收）

- [x] **加入 pool_pre_ping**
  - 使用連線前先做健康檢查
  - 避免使用已斷線的連線

- [x] **更新 Keep-Alive 機制**
  - 改為定期 ping（每 5 分鐘）保持連線活躍
  - 防止防火牆/NAT 斷開閒置連線

### Phase 2.5: 啟動驗證與監控

- [x] **加入連線池監控事件**
  - SQLAlchemy event: checkout / checkin / invalidate / connect
  - 記錄 pool 使用狀況至 DEBUG log

- [ ] **應用啟動時驗證連線**
  - 在 init_db() 加入 SELECT 1 FROM DUAL 測試
  - 失敗時記錄錯誤但不中斷啟動

### Phase 3: 重試策略與熔斷（可選）

- [ ] **加入 query-level retry decorator**
  - 針對可重試的 ORA 錯誤碼（如 ORA-03113, ORA-03114）
  - 最多重試 2 次，間隔 1 秒

- [ ] **Circuit Breaker 模式**
  - 連續失敗 5 次後熔斷 60 秒
  - 熔斷期間直接返回錯誤，不嘗試連線

### 測試驗證

- [ ] **驗證 logging 輸出**
  - 確認錯誤進入 error.log
  - 確認慢查詢被記錄

- [ ] **驗證連線池行為**
  - 併發請求時連線數符合預期
  - 閒置連線正確回收

- [ ] **壓力測試**
  - 模擬高併發請求
  - 確認無連線洩漏
