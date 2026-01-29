# Tasks: add-availability-trend

## Backend

- [x] 在 `resource_history_service.py` 新增 `_calc_availability_pct()` 函數
  - 公式: `(prd + sby + egt) / (prd + sby + egt + sdt + udt + nst) * 100`
  - 分母為零時回傳 0

- [x] 修改 `_build_kpi_from_df()` 新增 `availability_pct` 欄位

- [x] 修改 `_build_trend_from_df()` 在每個資料點新增 `availability_pct`

- [x] 修改 `_build_detail_from_df()` 新增 `availability_pct` 欄位

- [x] 修改 `export_csv()` 新增 Availability% 欄位
  - 標頭新增 `Availability%`（位於 `OU%` 之後）
  - 各列計算並輸出 Availability%

## Frontend

- [x] 修改 `resource_history.html` 趨勢圖新增 Availability% 趨勢線
  - 使用綠色 (`#10B981`)
  - 更新圖例顯示兩項指標

- [x] 修改 `resource_history.html` KPI 區新增 Availability% 卡片
  - 顯示格式: `XX.X%`
  - 位置: OU% 卡片之後

## Testing

- [x] 新增單元測試 `test_calc_availability_pct`
  - 測試正常計算
  - 測試分母為零情況

- [x] 新增 API 整合測試驗證 `availability_pct` 欄位存在
