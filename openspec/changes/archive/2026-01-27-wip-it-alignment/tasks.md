## Tasks

### 後端修改

- [x] **修改 wip_service.py::get_wip_summary()**
  - 新增 WIP Status 分組統計 SQL（RUN/QUEUE/HOLD 的 LOTS 和 QTY）
  - 使用 CASE WHEN 計算：EQUIPMENTCOUNT > 0 → RUN，CURRENTHOLDCOUNT > 0 → HOLD，else → QUEUE
  - 修改回傳格式，新增 `byWipStatus` 欄位
  - 將 `total_qty` 改名為 `totalQtyPcs`
  - 將 `sys_date` 改名為 `dataUpdateDate`

- [x] **移除 wip_service.py 中的 hold_lots/hold_qty**
  - 從 get_wip_summary() 回傳中移除獨立的 hold_lots 和 hold_qty（已整合至 byWipStatus.hold）

- [x] **更新 wip_routes.py API 回傳格式**
  - 確保 `/api/wip/overview/summary` 回傳 camelCase 格式

### 前端修改

- [x] **修改 wip_overview.html Summary Cards HTML**
  - 將 4 個 KPI 卡片改為 2 個（Total Lots, Total QTY）
  - 移除 Hold Lots 和 Hold QTY 卡片

- [x] **新增 WIP Status Cards HTML**
  - 在 KPI 卡片下方新增 3 個 WIP Status 卡片容器
  - RUN 卡片：包含 lots 數和 pcs 數
  - QUEUE 卡片：包含 lots 數和 pcs 數
  - HOLD 卡片：包含 lots 數和 pcs 數

- [x] **新增 WIP Status Cards CSS**
  - 定義 `.wip-status-row` 三欄 grid 佈局
  - 定義 `.wip-status-card` 基本樣式
  - 定義 `.run` 綠色樣式（border: #22C55E, bg: #F0FDF4）
  - 定義 `.queue` 黃色樣式（border: #F59E0B, bg: #FFFBEB）
  - 定義 `.hold` 紅色樣式（border: #EF4444, bg: #FEF2F2）
  - 確保 lots 和 qty 數字同樣大小顯示

- [x] **修改 wip_overview.html renderSummary() JavaScript**
  - 更新 renderSummary() 處理新的 API 回傳格式
  - 新增 WIP Status 卡片的數據更新邏輯
  - 移除 holdLots/holdQty 的更新（改用 byWipStatus.hold）

### 測試驗證

- [x] **驗證後端 API 回傳格式**
  - 手動測試 `/api/wip/overview/summary` 回傳正確的 byWipStatus 結構
  - 確認 RUN + QUEUE + HOLD 的 lots 總和等於 totalLots

- [x] **驗證前端顯示**
  - 確認 WIP Status 卡片顯示正確顏色
  - 確認數字格式正確（千分位）
  - 確認 lots 和 qty 數字同樣大小
  - 測試響應式佈局（小螢幕）

### WIP Detail 頁面對齊（追加）

- [x] **修改 wip_service.py::get_wip_detail()**
  - 新增 WIP Status 欄位至每筆 lot 記錄（使用 CASE WHEN 計算）
  - 修改 summary 回傳：totalLots, runLots, queueLots, holdLots

- [x] **修改 wip_detail.html KPI 卡片**
  - 改為 RUN / QUEUE / HOLD 三個狀態卡片
  - 套用對應顏色樣式（綠/黃/紅）

- [x] **修改 wip_detail.html 資料表格**
  - 新增 WIP Status 欄位顯示 RUN/QUEUE/HOLD
  - 移除舊的 On Equipment/Waiting/Hold 邏輯

### 修復與優化（追加）

- [x] **修復 URL 雙重編碼問題**
  - 移除 navigateToDetail() 中的 encodeURIComponent()
  - 讓 URLSearchParams 自動處理編碼

- [x] **修復 race condition**
  - 將 visibilitychange 事件監聽移至 init() 內部

- [x] **增加 API 逾時時間**
  - wip_detail.html: 30s → 60s
  - wip_overview.html: 30s → 60s
  - fetchPackages 改為非阻塞載入

- [x] **Matrix 表格樣式優化**
  - Workcenter 欄位固定顯示（sticky + border）
  - Package 標題列固定顯示（sticky + border）
