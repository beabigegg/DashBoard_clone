## Why

設備歷史績效頁面目前只顯示 OU%（Overall Utilization）趨勢圖，但使用者需要同時監控設備的 Availability%（可用率）來完整評估設備效能。Availability% 是衡量設備「可用時間」佔「總排程時間」的重要指標，與 OU% 互補使用可提供更全面的設備績效分析。

## What Changes

- 在設備歷史績效頁面的趨勢圖區塊新增 Availability% 趨勢圖
- 新增 Availability% 的計算邏輯：`(PRD + SBY + EGT) / (PRD + SBY + EGT + SDT + UDT + NST)`
- 與現有 OU% 趨勢圖並列顯示，使用相同的時間軸與篩選條件
- KPI 卡片區新增 Availability% 指標

## Capabilities

### New Capabilities

（無新增獨立模組，此功能擴展現有 resource-history 模組）

### Modified Capabilities

- `resource-cache`: 新增 Availability% 計算與趨勢資料輸出

## Impact

- **後端服務**: `resource_history_service.py` - 新增 Availability% 計算邏輯
- **API 回應**: `/api/resource/history/summary` - 回應結構新增 availability 欄位
- **前端頁面**: `resource_history.html` - 新增趨勢圖與 KPI 卡片
- **無破壞性變更**: 現有 API 回應結構維持向下相容
