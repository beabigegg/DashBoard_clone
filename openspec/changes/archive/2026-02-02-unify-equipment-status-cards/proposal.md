## Why

設備即時機況與設備歷史績效兩個頁面的 KPI 卡片設計不一致，造成使用者在切換頁面時需要重新理解卡片含義。統一卡片設計可提升使用體驗並確保數據呈現的一致性。

## What Changes

- **統一卡片數量與排序**：兩個頁面統一為 9 張卡片，順序相同
- **統一卡片標籤**：主標籤（OU%、Availability%、PRD、SBY、UDT、SDT、EGT、NST、機台數）與副標籤（稼動率、可用率、生產、待機、非計畫停機、計畫停機、工程、未排程、設備總數）
- **即時機況新增指標**：新增 OU%、Availability%、NST 卡片；將 UDT/SDT 合併卡片拆分為獨立卡片
- **歷史績效新增指標**：新增 SBY、NST 卡片；所有狀態卡片新增佔比顯示
- **統一佔比計算**：佔比% = 該狀態 / (PRD + SBY + UDT + SDT + EGT + NST) × 100

## Capabilities

### New Capabilities

- `equipment-status-cards`: 統一的設備狀態 KPI 卡片組件規格，定義卡片結構、排序、標籤、計算公式

### Modified Capabilities

（無既有規格需修改）

## Impact

- **前端模板**：
  - `src/mes_dashboard/templates/resource_status.html` - 即時機況頁面卡片區塊
  - `src/mes_dashboard/templates/resource_history.html` - 歷史績效頁面卡片區塊
- **後端服務**：
  - `src/mes_dashboard/services/resource_service.py` - 即時機況 API 需新增 OU%、Availability% 計算
  - `src/mes_dashboard/services/resource_history_service.py` - 歷史績效 API 需新增 SBY、NST 欄位
- **API 端點**：
  - `/api/resource/status/summary` - 回傳資料結構調整
