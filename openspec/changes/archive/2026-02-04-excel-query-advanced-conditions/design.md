## Context

現有 Excel 批次查詢工具 (`/excel-query`) 提供基本的 `WHERE column IN (...)` 查詢功能，處理流程：
1. 上傳 Excel → pandas 解析
2. 選擇欄位 → 提取不重複值
3. 選擇資料表 → 查詢 Oracle 欄位
4. 執行查詢 → 分批處理（每批 1000 筆）→ 合併結果
5. 匯出 CSV

**現有檔案**：
- `routes/excel_query_routes.py`：5 個端點
- `services/excel_query_service.py`：Excel 解析、批次查詢、CSV 生成
- `templates/excel_query.html`：前端介面
- `config/tables.py`：19 張資料表配置（含 `time_field` 定義）

**約束**：
- Oracle IN clause 限制 1000 個值
- 歷史表資料量龐大（數千萬筆），需考慮查詢效能
- 需維持向後相容，現有功能不可中斷

## Goals / Non-Goals

**Goals:**
- 支援日期範圍篩選，利用 `TABLES_CONFIG` 中已定義的 `time_field`
- 支援 LIKE 模糊查詢（包含/前綴/後綴）
- 顯示 Excel 與 Oracle 欄位類型資訊，輔助使用者選擇
- 提供效能警告機制，避免使用者觸發全表掃描
- 保持 API 向後相容

**Non-Goals:**
- 不實作全文搜索（Oracle Text）
- 不支援跨表 JOIN 查詢
- 不支援 BLOB/CLOB 欄位查詢
- 不實作查詢結果快取

## Decisions

### D1: API 設計策略 - 新增端點 vs 擴充現有端點

**決定**：新增 `/execute-advanced` 端點，保留原 `/execute` 端點

**理由**：
- 向後相容：現有使用者/腳本不受影響
- 關注點分離：進階查詢邏輯獨立，易於維護
- 漸進式遷移：未來可考慮 deprecate 舊端點

**替代方案**：
- 擴充現有端點加入可選參數 → 增加複雜度，難以維護
- 完全取代現有端點 → 破壞向後相容

### D2: 日期範圍條件生成

**決定**：使用 Oracle `BETWEEN TO_DATE(...) AND TO_DATE(...) + 1` 語法

**理由**：
- 包含結束日期當天的所有資料（+1 處理時間部分）
- 參數化查詢防止 SQL injection
- 可利用日期欄位索引

**SQL 範例**：
```sql
WHERE {time_column} BETWEEN TO_DATE(:date_from, 'YYYY-MM-DD')
                        AND TO_DATE(:date_to, 'YYYY-MM-DD') + 1
```

### D3: LIKE 查詢效能保護

**決定**：限制 LIKE 包含查詢（`%keyword%`）最多 100 個關鍵字，並顯示警告

**理由**：
- `LIKE '%xxx%'` 無法使用索引，會觸發全表掃描
- 100 個關鍵字 × 多個 OR 已足夠大多數使用場景
- 對大型表（>10M）顯示效能警告，讓使用者知情

**替代方案**：
- 不限制 → 可能導致查詢 timeout
- 完全禁止大表使用 LIKE → 降低功能可用性

### D4: 欄位類型偵測實作

**決定**：
- Excel 欄位：採樣前 100 筆，使用正則表達式判斷 text/number/date/id
- Oracle 欄位：查詢 `ALL_TAB_COLUMNS` 取得 DATA_TYPE

**理由**：
- Excel 類型偵測：pandas dtype 不可靠（常為 object），需自行分析
- Oracle metadata：標準做法，一次查詢取得所有欄位資訊

**Oracle 查詢**：
```sql
SELECT COLUMN_NAME, DATA_TYPE, DATA_LENGTH, DATA_PRECISION, DATA_SCALE
FROM ALL_TAB_COLUMNS
WHERE OWNER = :owner AND TABLE_NAME = :table_name
ORDER BY COLUMN_ID
```

### D5: 前端 UI 擴充方式

**決定**：在 Step 4 區塊新增摺疊式「進階條件」面板

**理由**：
- 保持介面簡潔，進階功能隱藏於摺疊面板
- 不影響現有使用流程
- 可漸進式展開功能

## Risks / Trade-offs

| 風險 | 影響 | 緩解措施 |
|------|------|----------|
| LIKE 查詢效能差 | 大表查詢 timeout | 限制 100 關鍵字 + 效能警告 + 建議配合日期範圍 |
| Oracle metadata 查詢權限 | 無法取得欄位類型 | Fallback 到現有 `SELECT * WHERE ROWNUM <= 1` 方式 |
| 日期格式不一致 | 前端傳入格式錯誤 | 後端驗證 + 統一 YYYY-MM-DD 格式 |
| 複合條件 SQL 過長 | 超過 Oracle 限制 | 分批處理已有實作，LIKE 另外限制數量 |

## Migration Plan

1. **Phase 1**：新增後端 API（`/table-metadata`, `/execute-advanced`）
2. **Phase 2**：前端新增進階條件 UI
3. **Phase 3**：整合測試與效能驗證
4. **Rollback**：移除新端點即可，不影響現有功能
