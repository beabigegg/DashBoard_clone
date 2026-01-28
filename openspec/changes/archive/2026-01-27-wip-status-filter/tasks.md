## Tasks

### Phase 1: 後端 API 支援

- [x] **修改 wip_service.py - get_wip_matrix()**
  - 新增 `status` 參數（Optional[str]）
  - 加入 WIP 狀態篩選條件
    - RUN: `EQUIPMENTCOUNT > 0`
    - HOLD: `EQUIPMENTCOUNT = 0 AND CURRENTHOLDCOUNT > 0`
    - QUEUE: `EQUIPMENTCOUNT = 0 AND CURRENTHOLDCOUNT = 0`

- [x] **修改 wip_routes.py - api_overview_matrix()**
  - 解析 `status` query parameter
  - 驗證 status 值（RUN/QUEUE/HOLD 或空）
  - 傳遞給 get_wip_matrix()

### Phase 2: 前端互動

- [x] **新增 CSS 樣式**
  - `.wip-status-card` 加入 cursor: pointer 和 hover 效果
  - `.wip-status-card.active` 選中狀態樣式
  - 各狀態的選中陰影顏色

- [x] **修改 HTML 結構**
  - 三張卡片加入 `onclick="toggleStatusFilter('xxx')"`

- [x] **實作 JavaScript 邏輯**
  - 新增 `activeStatusFilter` 狀態變數
  - 實作 `toggleStatusFilter(status)` 函數
  - 實作 `updateCardStyles()` 函數
  - 實作 `loadMatrixOnly()` 獨立載入 Matrix
  - 修改 `fetchMatrix()` 支援 status 參數

### Phase 3: 整合與優化

- [x] **整合 loadAllData()**
  - fetchMatrix() 內部已讀取 activeStatusFilter
  - Summary 和 Hold Summary 不受影響

- [x] **Matrix 標題顯示篩選狀態**
  - 實作 `updateMatrixTitle()` 函數
  - 有篩選時顯示 "- RUN Only" 等後綴

### Phase 4: WIP Detail 頁面整合

- [x] **增強視覺效果（wip_overview.html）**
  - 更強的 active 狀態（scale 1.03, border 4px）
  - 更深的背景色（#DCFCE7, #FEF3C7, #FEE2E2）
  - 非選中卡片變暗（opacity: 0.5）

- [x] **套用至 WIP Detail 頁面**
  - 新增可點擊的 CSS 樣式到 summary cards
  - 移除 Status 下拉選單（原本是 ACTIVE/HOLD）
  - Summary cards 加入 onclick handlers
  - 新增 `activeStatusFilter` 狀態變數
  - 實作 `toggleStatusFilter()`, `updateCardStyles()`, `updateTableTitle()`
  - 修改 `fetchDetail()` 支援 status 參數
  - 新增 `loadTableOnly()` 獨立載入函數（避免 isLoading 阻擋切換）

- [x] **後端 API 更新**
  - 修改 `get_wip_detail()` 支援 RUN/QUEUE/HOLD 篩選
  - 修改 `api_detail()` 驗證 status 參數

### 驗證測試

- [x] **WIP Overview 功能測試**
  - 點擊 RUN → Matrix 只顯示 RUN 數量
  - 點擊 QUEUE → Matrix 只顯示 QUEUE 數量
  - 點擊 HOLD → Matrix 只顯示 HOLD 數量
  - 再次點擊 → 恢復全部

- [x] **WIP Detail 功能測試**
  - 點擊 RUN → Table 只顯示 RUN lots
  - 點擊 QUEUE → Table 只顯示 QUEUE lots
  - 點擊 HOLD → Table 只顯示 HOLD lots
  - 再次點擊 → 恢復全部

- [x] **視覺測試**
  - 選中卡片樣式正確（兩頁面）
  - 非選中卡片變暗
  - 載入時有提示

- [x] **組合篩選測試**
  - workorder + status 同時篩選
  - lotid + status 同時篩選
  - package + status 同時篩選（Detail）

### Bug 修復

- [x] **WIP Detail 無法直接切換篩選狀態**
  - 問題：`loadAllData()` 有 `isLoading` 保護，載入中點擊其他卡片會被忽略
  - 解法：新增 `loadTableOnly()` 獨立載入函數，與 WIP Overview 的 `loadMatrixOnly()` 行為一致

- [x] **快速切換篩選導致連線堆積 Timeout**
  - 問題：連續快速點擊不同狀態卡片，多個請求同時發出，耗盡連線池
  - 解法：使用 `AbortController` 取消前一個進行中的請求
    - WIP Overview: `matrixAbortController` + `loadMatrixOnly()` 取消邏輯
    - WIP Detail: `tableAbortController` + `loadTableOnly()` 取消邏輯
    - `fetchWithTimeout()` 新增 `externalSignal` 參數支援外部取消
