## Context

現有 WIP 報表使用 `DW_MES_WIP` 交易歷史表，需要 ROW_NUMBER() 窗口函數來計算每個 Lot 的最新狀態。IT 已建立即時 View `DWH.DW_PJ_LOT_V`，每 5 分鐘更新一次，直接提供當前 WIP 快照。

**現有架構問題**:
- 查詢複雜 (ROW_NUMBER + 90天範圍掃描)
- 缺少預算好的 WORKCENTER_GROUP
- 前端沒有自動刷新機制

**新 View 優勢**:
- 直接查詢，無需窗口函數
- 內建 WORKCENTER_GROUP、WORKCENTERSEQUENCE_GROUP 排序欄位
- 包含完整 HOLD 資訊 (HOLDEMP, COMMENT_HOLD 等)
- SYS_DATE 欄位標記資料更新時間

## Goals / Non-Goals

**Goals:**
- 使用 `DWH.DW_PJ_LOT_V` 作為唯一資料來源
- 建立兩種 Dashboard: Overview (高階主管) + Detail (產線)
- 實現無縫自動刷新 (10分鐘間隔，無頁面閃爍)
- 刪除舊的 WIP 報表程式碼

**Non-Goals:**
- 老化分析功能 (AGEBYDAYS) - 不在此次範圍
- 歷史趨勢分析 - 只顯示即時資料
- 匯出功能 - 未來再做
- 多語系支援

## Decisions

### 1. 資料來源: 使用 Schema Prefix

**決定**: 查詢時使用 `DWH.DW_PJ_LOT_V` (含 schema prefix)

**原因**: 直接查詢 `DW_PJ_LOT_V` 會報 ORA-00942，必須加上 owner schema。

**替代方案**: 建立 synonym - 但需要 DBA 權限，不如直接用 prefix 簡單。

### 2. 排序欄位: 使用 View 內建欄位

**決定**:
- WORKCENTER_GROUP 排序用 `WORKCENTERSEQUENCE_GROUP`
- SPECNAME 排序用 `SPECSEQUENCE`

**原因**: View 已預算好這些欄位，不需要維護專案內的 workcenter_groups.py mapping。

**刪除**: `src/mes_dashboard/config/workcenter_groups.py` 不再需要。

### 3. 在機判斷邏輯

**決定**:
- `EQUIPMENTNAME IS NOT NULL` → 在機
- `EQUIPMENTNAME IS NULL` → 待料

**原因**: 經確認這是正確的判斷邏輯。

### 4. 自動刷新架構

**決定**: 純前端輪詢 + 局部 DOM 更新

```
┌─────────────────────────────────────────────────────────┐
│  Frontend Auto-Refresh Architecture                     │
├─────────────────────────────────────────────────────────┤
│                                                         │
│  setInterval(() => {                                    │
│    fetch('/api/wip/...')                               │
│      .then(newData => {                                │
│        diffAndUpdate(currentData, newData);            │
│      });                                               │
│  }, 10 * 60 * 1000);  // 10 minutes                    │
│                                                         │
│  diffAndUpdate():                                       │
│    1. 比對新舊資料                                       │
│    2. 只更新變化的 DOM 元素                              │
│    3. 使用 CSS transition 處理數值變化                   │
│    4. 表格行增刪使用 fade in/out animation              │
│                                                         │
└─────────────────────────────────────────────────────────┘
```

**原因**:
- 不需要 WebSocket (資料更新頻率僅 5 分鐘)
- 純前端輪詢簡單可靠
- 局部更新避免閃爍

**替代方案**:
- Server-Sent Events - 過度設計
- WebSocket - 過度設計
- 整頁 reload - 使用者體驗差

### 5. API 設計

**決定**: RESTful JSON API

```
GET  /api/wip/overview/summary     → KPI 摘要
GET  /api/wip/overview/matrix      → 工站×產品線矩陣
GET  /api/wip/overview/hold        → Hold 摘要
GET  /api/wip/detail/{workcenter}  → 工站細部資料
GET  /api/wip/meta/workcenters     → 工站列表 (用於下拉選單)
GET  /api/wip/meta/packages        → Package 列表
```

**原因**: 分離 API 讓前端可以獨立刷新各區塊。

### 6. 前端框架

**決定**: 純 JavaScript (Vanilla JS) + CSS Transitions

**原因**:
- 現有專案沒有使用 React/Vue
- Dashboard 相對簡單，不需要框架
- 減少依賴和學習成本

### 7. 更新時間顯示

**決定**: 顯示 `SYS_DATE` 欄位的值

**格式**: `最後更新: 2026-01-26 19:18:29`

**原因**: 這是 View 實際的資料更新時間，比顯示「每 5 分鐘更新」更有意義。

## Risks / Trade-offs

| Risk | Mitigation |
|------|------------|
| View 結構變更 | 與 IT 確認欄位穩定性；建立欄位 mapping 層 |
| 大量資料效能 | 使用分頁；只查詢需要的欄位 |
| 前端狀態管理複雜 | 保持簡單的資料結構；避免過度抽象 |
| 舊報表刪除後無法回退 | Git 版本控制；可以 revert |

## File Structure

```
src/mes_dashboard/
├── routes/
│   └── wip.py              # WIP 路由 (新建/重寫)
├── services/
│   └── wip_service.py      # WIP 資料服務 (重寫)
├── templates/
│   ├── wip_overview.html   # 高階主管總覽 (新建)
│   └── wip_detail.html     # 產線細部檢視 (新建)
└── config/
    └── (刪除 workcenter_groups.py)
```
