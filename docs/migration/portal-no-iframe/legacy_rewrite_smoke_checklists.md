# Legacy Rewrite Smoke Checklists (Per-Page)

本文件是 `7.2 ~ 7.4` 的執行前置與驗收基準。
每一頁在「重寫前(wrapper baseline)」與「重寫後(rewrite candidate)」都必須執行同一組 smoke。

## 0. 執行規則

- 必須記錄：執行日期、分支/commit、執行人、環境(DEV/UAT)。
- 每頁 smoke 通過率要求：`100%`。
- 任何 P0 smoke 失敗即視為 `No-Go`，不得進入 wrapper 移除。
- `excel-query`、`query-tool` 為 admin/dev 可見頁，需使用 admin 身份執行。

## 1. `tmtt-defect`（Rewrite Exemplar）

### 前置條件
- 可取得有效 `start_date/end_date` 測試區間。
- `/api/tmtt-defect/analysis` 與 `/api/tmtt-defect/export` 可連線。

### Smoke Cases
- [ ] `TMTT-SMOKE-01` Route reachable: `/tmtt-defect` 可直接開啟，無白屏/JS error。
- [ ] `TMTT-SMOKE-02` Required params guard: 缺少日期時，顯示明確錯誤且不崩潰。
- [ ] `TMTT-SMOKE-03` Query success: 送出合法日期後，KPI/Charts/Detail 皆成功渲染。
- [ ] `TMTT-SMOKE-04` Drill-down: 點擊 Pareto 圖欄位可套用/清除篩選，明細同步。
- [ ] `TMTT-SMOKE-05` Table behavior: 明細表格可排序，排序方向切換正確。
- [ ] `TMTT-SMOKE-06` Export CSV: 匯出成功，response 為 CSV 且檔名包含日期區間。

## 2. `job-query`

### 前置條件
- `resource` 清單可取得。
- 至少有一組可查詢日期區間。

### Smoke Cases
- [ ] `JOB-SMOKE-01` Route reachable: `/job-query` 可直接開啟。
- [ ] `JOB-SMOKE-02` Resource loading: `/api/job-query/resources` 回傳清單，UI 可選取。
- [ ] `JOB-SMOKE-03` Query jobs: 選設備+日期後可查詢成功並顯示結果。
- [ ] `JOB-SMOKE-04` Txn detail: 由查詢結果可開啟某筆 job 的 txn history。
- [ ] `JOB-SMOKE-05` Export CSV: 匯出成功且檔案可下載。
- [ ] `JOB-SMOKE-06` Validation: 缺日期/無設備/超過上限時回傳明確錯誤訊息。

## 3. `excel-query`（Admin）

### 前置條件
- 準備一份有效 `.xlsx` 測試檔。
- Admin session 已登入。

### Smoke Cases
- [ ] `EXCEL-SMOKE-01` Route/auth: `/excel-query` admin 可進入，非 admin 受保護。
- [ ] `EXCEL-SMOKE-02` Upload: 上傳有效 Excel 後可解析欄位與預覽。
- [ ] `EXCEL-SMOKE-03` Column detect: 欄位唯一值與型別偵測可正常運作。
- [ ] `EXCEL-SMOKE-04` Execute query: 標準查詢與進階查詢都可回傳資料。
- [ ] `EXCEL-SMOKE-05` Export CSV: 查詢結果可匯出 CSV。
- [ ] `EXCEL-SMOKE-06` Invalid file guard: 非 `.xls/.xlsx` 檔案被拒絕且回傳可讀錯誤。

## 4. `query-tool`（Admin）

### 前置條件
- Admin session 已登入。
- 可用測試 lot/equipment/date range。

### Smoke Cases
- [ ] `QTOOL-SMOKE-01` Route reachable: `/query-tool` 可開啟。
- [ ] `QTOOL-SMOKE-02` Resolve flow: lot_id/serial/work_order 至少一種解析成功。
- [ ] `QTOOL-SMOKE-03` History flow: lot history 可查詢並顯示。
- [ ] `QTOOL-SMOKE-04` Adjacent flow: adjacent lots 查詢可回傳。
- [ ] `QTOOL-SMOKE-05` Associations: materials/rejects/holds/splits/jobs 查詢可用。
- [ ] `QTOOL-SMOKE-06` Equipment period: status_hours/lots/materials/rejects/jobs 至少各成功一次。
- [ ] `QTOOL-SMOKE-07` Export CSV: 匯出可下載且欄位合理。
- [ ] `QTOOL-SMOKE-08` Validation: 缺參數、非法日期範圍會回傳可讀錯誤。

## 5. Exit Rule（與 7.4 連動）

只有在下列條件全成立，才可移除 wrapper：

- [ ] 四頁 rewrite smoke 全部通過。
- [ ] 與 `legacy_wrapper_telemetry_contract.md` 對照，error 率在門檻內。
- [ ] 與 `parity_checklist.md` 的 Route/Workflow/API contract 檢查一致。
