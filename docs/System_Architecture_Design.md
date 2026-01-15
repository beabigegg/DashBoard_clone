# MES 報表查詢系統 - 系統架構設計文檔

**專案名稱**: MES Dashboard & Report System
**技術棧**: Vite + React (Frontend) + Python FastAPI (Backend) + Oracle 19c (Database)
**文檔版本**: 1.0
**建立日期**: 2026-01-14
**架構師**: Claude (AI System Architect)

---

## 目錄

1. [專案概述](#專案概述)
2. [需求分析](#需求分析)
3. [系統架構設計](#系統架構設計)
4. [技術選型](#技術選型)
5. [數據庫設計](#數據庫設計)
6. [API 設計](#api-設計)
7. [前端設計](#前端設計)
8. [性能優化策略](#性能優化策略)
9. [項目結構](#項目結構)
10. [開發計劃](#開發計劃)
11. [部署方案](#部署方案)

---

## 專案概述

### 業務背景
本系統旨在為製造執行系統 (MES) 提供一個高效的報表查詢與數據可視化平台，用於監控生產過程、設備狀態、在制品管理等核心業務指標。

### 核心目標
- 提供類似 Power BI 的儀表板展示功能
- 支援多維度報表查詢
- 查詢響應時間 < 10 秒
- 支援 Excel 報表匯出
- 簡潔易用的用戶界面

### 數據規模
- **數據庫**: Oracle 19c Enterprise Edition
- **數據總量**: 約 4.98 億行 (16 張核心業務表)
- **主機地址**: 10.1.1.58:1521
- **數據庫名**: DWDB
- **用戶**: MBU1_R (只讀權限)

---

## 需求分析

### 功能需求

#### 1. 儀表板 (Dashboard)
- 實時顯示關鍵生產指標
- 多圖表組合展示 (折線圖、柱狀圖、餅圖、儀表盤)
- 時間範圍篩選 (今日、本週、本月、自定義)
- 自動刷新功能

#### 2. 報表查詢模塊
待確認的報表類型：
- [ ] 在制品 (WIP) 報表
- [ ] 維修工單 (Job) 完成情況報表
- [ ] 設備 (Equipment) 狀態與稼動率報表
- [ ] 批次 (Lot) 追蹤報表
- [ ] 物料消耗統計報表
- [ ] 其他 (待 Power BI 截圖確認)

#### 3. 數據匯出
- Excel 格式匯出 (.xlsx)
- 支援匯出當前查詢結果
- 支援大數據量異步匯出 (>10000 行)

#### 4. 用戶權限
- **當前階段**: 單一角色，所有用戶看相同數據
- **未來擴展**: 預留權限控制接口 (RBAC)

### 非功能需求

#### 1. 性能要求
- **查詢響應**: < 10 秒
- **頁面加載**: < 3 秒
- **並發用戶**: 支援 20-50 個並發用戶
- **數據刷新**: 儀表板每 5 分鐘自動刷新

#### 2. 可用性要求
- 系統可用性 > 99%
- 支援 Chrome、Edge、Firefox 最新版本
- 響應式設計 (支援 1920x1080 及以上解析度)

#### 3. 安全性要求
- 數據庫連接使用只讀帳號
- API 請求參數化查詢 (防止 SQL 注入)
- 敏感配置使用環境變量

---

## 系統架構設計

### 整體架構圖

```
┌─────────────────────────────────────────────────────────────────┐
│                     客戶端瀏覽器 (Browser)                        │
│                                                                 │
│  ┌──────────────────────────────────────────────────────────┐  │
│  │          前端應用 (Vite + React + TypeScript)             │  │
│  │                                                            │  │
│  │  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐      │  │
│  │  │  Dashboard  │  │   Report    │  │   Export    │      │  │
│  │  │   儀表板     │  │   報表查詢   │  │   匯出功能   │      │  │
│  │  └─────────────┘  └─────────────┘  └─────────────┘      │  │
│  │                                                            │  │
│  │  ┌──────────────────────────────────────────────┐        │  │
│  │  │  ECharts / Ant Design Charts (圖表組件)       │        │  │
│  │  └──────────────────────────────────────────────┘        │  │
│  │                                                            │  │
│  │  ┌──────────────────────────────────────────────┐        │  │
│  │  │  React Query (數據獲取與緩存)                  │        │  │
│  │  └──────────────────────────────────────────────┘        │  │
│  └──────────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────────┘
                               ↕ HTTP/REST API (JSON)
┌─────────────────────────────────────────────────────────────────┐
│                  應用服務器 (Python FastAPI)                      │
│                                                                 │
│  ┌──────────────────────────────────────────────────────────┐  │
│  │  API 路由層 (Routers)                                     │  │
│  │  ├─ /api/dashboard/*     (儀表板數據)                    │  │
│  │  ├─ /api/reports/*       (報表查詢)                      │  │
│  │  └─ /api/export/*        (數據匯出)                      │  │
│  └──────────────────────────────────────────────────────────┘  │
│                               ↕                                │
│  ┌──────────────────────────────────────────────────────────┐  │
│  │  業務邏輯層 (Services)                                     │  │
│  │  ├─ dashboard_service.py  (儀表板業務邏輯)               │  │
│  │  ├─ report_service.py     (報表業務邏輯)                 │  │
│  │  └─ export_service.py     (匯出業務邏輯)                 │  │
│  └──────────────────────────────────────────────────────────┘  │
│                               ↕                                │
│  ┌──────────────────────────────────────────────────────────┐  │
│  │  緩存層 (Cache Layer) - 可選                              │  │
│  │  └─ Redis / In-Memory Cache (查詢結果緩存 5-10 分鐘)    │  │
│  └──────────────────────────────────────────────────────────┘  │
│                               ↕                                │
│  ┌──────────────────────────────────────────────────────────┐  │
│  │  數據訪問層 (Data Access Layer)                           │  │
│  │  ├─ oracledb (Oracle 數據庫驅動)                         │  │
│  │  ├─ 連接池管理                                            │  │
│  │  └─ 參數化查詢 (SQL Injection 防護)                      │  │
│  └──────────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────────┘
                               ↕ SQL Query
┌─────────────────────────────────────────────────────────────────┐
│           Oracle Database 19c (10.1.1.58:1521/DWDB)            │
│                                                                 │
│  主要數據表 (16 張):                                             │
│  ├─ DW_MES_WIP               (在制品 - 7747萬行)              │
│  ├─ DW_MES_LOTWIPHISTORY     (批次歷史 - 5308萬行)            │
│  ├─ DW_MES_RESOURCESTATUS    (設備狀態 - 6513萬行)            │
│  ├─ DW_MES_JOB               (設備維修工單 - 123萬行)                 │
│  └─ ... (其他 12 張表)                                         │
└─────────────────────────────────────────────────────────────────┘
```

### 架構特點

1. **前後端分離**: 前端與後端獨立開發、部署
2. **RESTful API**: 標準化的 API 接口設計
3. **緩存策略**: 減少數據庫壓力，提升響應速度
4. **連接池**: 高效管理數據庫連接
5. **可擴展性**: 預留權限控制、多租戶等擴展空間

---

## 技術選型

### 前端技術棧

| 技術 | 版本 | 用途 | 選型理由 |
|------|------|------|----------|
| **React** | 18.x | UI 框架 | 生態豐富、組件化開發、社區活躍 |
| **TypeScript** | 5.x | 開發語言 | 類型安全、提升代碼質量 |
| **Vite** | 5.x | 構建工具 | 快速冷啟動、HMR 熱更新 |
| **Ant Design** | 5.x | UI 組件庫 | 企業級組件、接近 Power BI 風格 |
| **ECharts** | 5.x | 圖表庫 | 功能強大、圖表類型豐富 |
| **React Query** | 5.x | 數據管理 | 自動緩存、請求去重、後台刷新 |
| **Zustand** | 4.x | 狀態管理 | 輕量、簡單易用 |
| **React Router** | 6.x | 路由管理 | React 官方推薦路由方案 |
| **Axios** | 1.x | HTTP 客戶端 | 請求攔截、錯誤處理 |
| **Day.js** | 1.x | 日期處理 | 輕量、API 友好 |
| **SheetJS (xlsx)** | 0.18.x | Excel 匯出 | 瀏覽器端 Excel 生成 |
| **TailwindCSS** | 3.x | CSS 框架 | 快速樣式開發 (可選) |

### 後端技術棧

| 技術 | 版本 | 用途 | 選型理由 |
|------|------|------|----------|
| **Python** | 3.11+ | 開發語言 | 豐富的數據處理庫 |
| **FastAPI** | 0.109+ | Web 框架 | 高性能、自動生成 API 文檔、類型驗證 |
| **oracledb** | 2.x | Oracle 驅動 | Oracle 官方推薦的 Python 驅動 |
| **Pandas** | 2.x | 數據處理 | 強大的數據分析與轉換能力 |
| **Pydantic** | 2.x | 數據驗證 | FastAPI 內建，自動驗證請求參數 |
| **Uvicorn** | 0.27+ | ASGI 服務器 | 高性能異步服務器 |
| **Redis** | 7.x | 緩存 | 查詢結果緩存 (可選) |
| **python-dotenv** | 1.x | 環境變量 | 管理配置文件 |
| **openpyxl** | 3.x | Excel 生成 | 後端大數據量 Excel 生成 |

### 開發工具

| 工具 | 用途 |
|------|------|
| **VS Code** | 開發 IDE |
| **Postman / Bruno** | API 測試 |
| **Git** | 版本控制 |
| **Oracle SQL Developer** | 數據庫查詢工具 |

---

## 數據庫設計

> **詳細表結構分析**: 請參考 [MES_Core_Tables_Analysis_Report.md](MES_Core_Tables_Analysis_Report.md)

### 表性質分類（重要！）

#### 現況快照表（4張）- 數據會被更新或覆蓋
| 表名 | 數據量 | 用途 | 關鍵時間欄位 |
|------|--------|------|-------------|
| **DW_MES_WIP** | 77,470,834 | 當前在制品狀態 | MOVEINTIMESTAMP, TXNDATE |
| **DW_MES_RESOURCE** | 90,620 | 資源主檔（設備） | - |
| **DW_MES_CONTAINER** | 5,185,532 | 容器當前狀態 | LASTMOVEOUTTIMESTAMP, MOVEINTIMESTAMP |
| **DW_MES_JOB** | 1,239,659 | 設備維修工單當前狀態 | CREATEDATE, COMPLETEDATE |

#### 歷史累積表（10張）- 只新增不修改
| 表名 | 數據量 | 用途 | 關鍵時間欄位 |
|------|--------|------|-------------|
| **DW_MES_RESOURCESTATUS** ⭐ | 65,139,825 | 資源狀態變更歷史 | OLDLASTSTATUSCHANGEDATE, LASTSTATUSCHANGEDATE |
| **DW_MES_RESOURCESTATUS_SHIFT** | 74,155,046 | 資源班次狀態 | SHIFTDATE |
| **DW_MES_LOTWIPHISTORY** ⭐ | 53,085,425 | 批次流轉歷史 | MOVEINTIMESTAMP, TRACKINTIMESTAMP |
| **DW_MES_LOTWIPDATAHISTORY** | 77,168,503 | 批次數據採集歷史 | TXNTIMESTAMP |
| **DW_MES_HM_LOTMOVEOUT** | 48,374,309 | 批次移出事件 | TXNDATE |
| **DW_MES_JOBTXNHISTORY** | 9,488,096 | 維修工單交易歷史 | TXNDATE |
| **DW_MES_LOTREJECTHISTORY** | 15,678,513 | 批次拒絕歷史 | CREATEDATE |
| **DW_MES_LOTMATERIALSHISTORY** | 17,702,828 | 物料消耗歷史 | CREATEDATE |
| **DW_MES_HOLDRELEASEHISTORY** | 310,033 | Hold/Release歷史 | HOLDTXNDATE, RELEASETXNDATE |
| **DW_MES_MAINTENANCE** | 50,954,850 | 設備維護歷史 | CREATEDATE |

### 核心表詳細說明

#### 1. DW_MES_WIP (在制品表) ⭐⭐⭐

**表性質**: 現況快照表（但數據量 7700 萬，包含歷史累積）

**業務定義**: 存儲當前所有在制品的實時狀態

**關鍵時間欄位**:
- `MOVEINTIMESTAMP`: 批次移入當前工序時間（用於計算在站時間）
- `ORIGINALSTARTDATE`: 批次原始開始生產日期
- `TXNDATE`: 資料最後更新時間（**必須用於查詢過濾**）
- `HOLDTIME`: Hold 時間
- `EXPECTEDENDDATE`: 預期完成日期

**關鍵業務欄位**:
- 數量: `QTY`, `MOVEINQTY`, `ORIGINALQTY`, `WOQTY`
- 狀態: `STATUS`, `CURRENTHOLDCOUNT`, `HOLDREASONNAME`
- 位置: `LOCATIONNAME`, `WORKFLOWSTEPNAME`, `WORKCENTERNAME`
- 識別: `CONTAINERNAME` (批次號), `MFGORDERNAME` (工單號), `PRODUCTNAME`

**查詢策略**:
```sql
-- 必須加入時間範圍限制！
WHERE TXNDATE >= TRUNC(SYSDATE) - 7
  AND STATUS NOT IN (8, 128)  -- 排除已完成/取消
```

#### 2. DW_MES_RESOURCESTATUS (資源狀態表) ⭐⭐⭐

**表性質**: 歷史累積表（記錄設備狀態每次變更）

**業務定義**: 用於計算設備稼動率、停機時間等關鍵指標

**關鍵時間欄位**:
- `OLDLASTSTATUSCHANGEDATE`: 上一個狀態開始時間（**計算起點**）
- `LASTSTATUSCHANGEDATE`: 新狀態開始時間（**計算終點**）
- 狀態持續時間 = `(LASTSTATUSCHANGEDATE - OLDLASTSTATUSCHANGEDATE) * 24` 小時

**關鍵業務欄位**:
- 狀態變更: `OLDSTATUSNAME` → `NEWSTATUSNAME`
- 可用性標記 (`AVAILABILITY`):
  - `1`: Productive (生產中)
  - `2`: Standby (待機)
  - `4`: Unscheduled Down (非計劃停機)
  - `5`: Scheduled Down (計劃停機)
- 資源信息: `HISTORYID` (= RESOURCEID), `WORKCENTERNAME`, `VENDORNAME`

**查詢策略**:
```sql
-- 計算設備稼動率
SELECT
    HISTORYID,
    TRUNC(OLDLASTSTATUSCHANGEDATE) as DATE_KEY,
    SUM(CASE WHEN AVAILABILITY = 1
        THEN (LASTSTATUSCHANGEDATE - OLDLASTSTATUSCHANGEDATE) * 24
        ELSE 0 END) as PRODUCTIVE_HOURS
FROM DW_MES_RESOURCESTATUS
WHERE OLDLASTSTATUSCHANGEDATE >= TRUNC(SYSDATE) - 7  -- 必須！
GROUP BY HISTORYID, TRUNC(OLDLASTSTATUSCHANGEDATE)
```

#### 3. DW_MES_LOTWIPHISTORY (批次在制品歷史表) ⭐⭐⭐

**表性質**: 歷史累積表（記錄批次完整流轉過程）

**業務定義**: 記錄批次從 MoveIn → TrackIn → TrackOut → MoveOut 的完整歷史

**關鍵時間欄位**:
- `MOVEINTIMESTAMP` / `MOVEOUTTIMESTAMP`: 進站/出站時間
- `TRACKINTIMESTAMP` / `TRACKOUTTIMESTAMP`: 上機/下機時間
- 加工時間 = `TRACKOUTTIMESTAMP - TRACKINTIMESTAMP`
- 等待時間 = `TRACKINTIMESTAMP - MOVEINTIMESTAMP`

**關鍵業務欄位**:
- 批次: `CONTAINERID`, `PJ_WORKORDER`
- 工序: `WORKCENTERNAME`, `SPECNAME`, `EQUIPMENTNAME`
- 數量: `MOVEINQTY`, `MOVEOUTQTY`, `TRACKINQTY`, `TRACKOUTQTY`
- 人員: `TRACKINEMPLOYEENAME`, `TRACKOUTEMPLOYEENAME`

**查詢策略**:
```sql
-- Cycle Time 分析
SELECT
    WORKCENTERNAME,
    SPECNAME,
    AVG((TRACKOUTTIMESTAMP - TRACKINTIMESTAMP) * 24) as AVG_CT_HOURS
FROM DW_MES_LOTWIPHISTORY
WHERE TRACKINTIMESTAMP >= TRUNC(SYSDATE) - 7  -- 必須！
GROUP BY WORKCENTERNAME, SPECNAME
```

#### 4. DW_MES_JOB (工單表)

**表性質**: 現況快照表（維修工單當前狀態）

**關鍵欄位**:
- `JOBID`, `JOBSTATUS`, `RESOURCEID` (關聯設備)
- `CREATEDATE`, `COMPLETEDATE`, `SYMPTOMCODENAME`, `CAUSECODENAME`

### 表間關聯關係

```
1. 在制品流轉主線
   DW_MES_WIP (現況) → CONTAINERID → DW_MES_CONTAINER → DW_MES_LOTWIPHISTORY

2. 設備狀態主線
   DW_MES_RESOURCE → RESOURCEID → DW_MES_RESOURCESTATUS → DW_MES_RESOURCESTATUS_SHIFT

3. 工單維修主線
   DW_MES_JOB → JOBID → DW_MES_JOBTXNHISTORY
   DW_MES_JOB → RESOURCEID → DW_MES_RESOURCE

4. 批次異常主線
   DW_MES_WIP/CONTAINER → CONTAINERID → DW_MES_HOLDRELEASEHISTORY
   DW_MES_LOTWIPHISTORY → DW_MES_LOTREJECTHISTORY
```

### 查詢優化建議（關鍵！）

#### 1. 大表查詢原則 ⚠️

**必須加時間範圍的表**（數據量 > 1000萬）:
```sql
-- DW_MES_WIP (7700萬行)
WHERE TXNDATE >= TRUNC(SYSDATE) - 7

-- DW_MES_RESOURCESTATUS (6500萬行)
WHERE OLDLASTSTATUSCHANGEDATE >= TRUNC(SYSDATE) - 7

-- DW_MES_RESOURCESTATUS_SHIFT (7400萬行)
WHERE SHIFTDATE >= TRUNC(SYSDATE) - 30

-- DW_MES_LOTWIPHISTORY (5300萬行)
WHERE TRACKINTIMESTAMP >= TRUNC(SYSDATE) - 7

-- DW_MES_LOTWIPDATAHISTORY (7700萬行)
WHERE TXNTIMESTAMP >= TRUNC(SYSDATE) - 7

-- DW_MES_HM_LOTMOVEOUT (4800萬行)
WHERE TXNDATE >= TRUNC(SYSDATE) - 7

-- DW_MES_MAINTENANCE (5000萬行)
WHERE CREATEDATE >= TRUNC(SYSDATE) - 30

-- DW_MES_LOTREJECTHISTORY (1500萬行)
WHERE CREATEDATE >= TRUNC(SYSDATE) - 30

-- DW_MES_LOTMATERIALSHISTORY (1700萬行)
WHERE CREATEDATE >= TRUNC(SYSDATE) - 30
```

**建議時間範圍**:
- 儀表板查詢: 最近 7 天
- 報表查詢: 最多 30 天
- 歷史趨勢分析: 最多 90 天

#### 2. 索引使用策略

**優先使用索引欄位**:
- `DW_MES_WIP`: `CONTAINERNAME`, `TXNDATE`
- `DW_MES_LOTWIPHISTORY`: `CONTAINERID`, `TRACKINTIMESTAMP`, `MOVEINTIMESTAMP`, `PJ_WORKORDER`
- `DW_MES_RESOURCESTATUS`: 無直接索引，必須用時間範圍減少掃描

#### 3. JOIN 優化

```sql
-- ✅ 好的寫法：先過濾再 JOIN
SELECT w.*, c.CURRENTSTATUSID
FROM (
  SELECT * FROM DW_MES_WIP
  WHERE TXNDATE >= TRUNC(SYSDATE) - 7
) w
LEFT JOIN DW_MES_CONTAINER c ON w.CONTAINERID = c.CONTAINERID

-- ❌ 不好的寫法：先 JOIN 再過濾
SELECT w.*, c.CURRENTSTATUSID
FROM DW_MES_WIP w
LEFT JOIN DW_MES_CONTAINER c ON w.CONTAINERID = c.CONTAINERID
WHERE w.TXNDATE >= TRUNC(SYSDATE) - 7
```

#### 4. 聚合查詢優化

```sql
-- ✅ 在數據庫層完成聚合
SELECT
  TRUNC(TXNDATE) as date,
  COUNT(*) as count,
  SUM(QTY) as total_qty
FROM DW_MES_WIP
WHERE TXNDATE >= TRUNC(SYSDATE) - 7
GROUP BY TRUNC(TXNDATE)

-- 避免取出大量原始數據後在 Python 層聚合
```

#### 5. 分頁查詢

```sql
-- Oracle 12c+ 使用 OFFSET FETCH
SELECT *
FROM DW_MES_WIP
WHERE TXNDATE >= TRUNC(SYSDATE) - 7
ORDER BY TXNDATE DESC
OFFSET 50 ROWS FETCH NEXT 50 ROWS ONLY;

-- Oracle 11g 使用 ROWNUM
SELECT * FROM (
  SELECT a.*, ROWNUM rnum FROM (
    SELECT * FROM DW_MES_WIP
    WHERE TXNDATE >= TRUNC(SYSDATE) - 7
    ORDER BY TXNDATE DESC
  ) a WHERE ROWNUM <= 100
) WHERE rnum > 50;
```

---

## API 設計

### API 路由規劃

#### 1. 儀表板 API

```
GET /api/dashboard/summary
描述: 獲取儀表板概覽數據
參數:
  - date_range: string (today|week|month|custom)
  - start_date: string (可選，YYYY-MM-DD)
  - end_date: string (可選，YYYY-MM-DD)

響應示例:
{
  "success": true,
  "data": {
    "wip_total": 125000,
    "job_completed": 850,
    "equipment_utilization": 78.5,
    "defect_rate": 2.3,
    "production_trend": [
      {"date": "2026-01-08", "quantity": 12500},
      {"date": "2026-01-09", "quantity": 13200}
    ],
    "equipment_status": {
      "running": 45,
      "idle": 8,
      "maintenance": 3,
      "error": 2
    }
  }
}
```

```
GET /api/dashboard/production-trend
描述: 獲取生產趨勢數據 (折線圖)
參數:
  - days: integer (7, 30, 90)

響應: 時間序列數據
```

```
GET /api/dashboard/equipment-status
描述: 獲取設備狀態分布 (餅圖)
參數:
  - date_range: string

響應: 設備狀態統計
```

#### 2. 報表查詢 API

```
GET /api/reports/wip
描述: 查詢在制品報表
參數:
  - start_date: string (必填)
  - end_date: string (必填)
  - lot: string (可選，批次號篩選)
  - operation: string (可選，工序篩選)
  - page: integer (默認 1)
  - page_size: integer (默認 50)
  - sort_by: string (默認 createtime)
  - sort_order: string (asc|desc，默認 desc)

響應示例:
{
  "success": true,
  "data": {
    "total": 15000,
    "page": 1,
    "page_size": 50,
    "records": [
      {
        "lot": "LOT12345",
        "quantity": 500,
        "operation": "SMT",
        "resource": "LINE-01",
        "create_time": "2026-01-14 08:30:00"
      }
    ]
  }
}
```

```
GET /api/reports/job
描述: 查詢維修工單報表
參數: (類似 WIP 報表)
```

```
GET /api/reports/equipment
描述: 查詢設備稼動率報表
參數: (類似 WIP 報表)
```

#### 3. 匯出 API

```
POST /api/export/excel
描述: 匯出報表為 Excel
參數:
  - report_type: string (wip|job|equipment)
  - filters: object (查詢條件)

響應:
  - Content-Type: application/vnd.openxmlformats-officedocument.spreadsheetml.sheet
  - Content-Disposition: attachment; filename="report_20260114.xlsx"
```

```
GET /api/export/status/{task_id}
描述: 查詢異步匯出任務狀態
響應:
{
  "task_id": "uuid",
  "status": "pending|processing|completed|failed",
  "progress": 75,
  "download_url": "/api/export/download/uuid"
}
```

### API 規範

1. **統一響應格式**
```json
{
  "success": true|false,
  "data": {},
  "message": "成功" | "錯誤訊息",
  "timestamp": "2026-01-14T12:00:00Z"
}
```

2. **錯誤處理**
```json
{
  "success": false,
  "error": {
    "code": "INVALID_DATE_RANGE",
    "message": "日期範圍不能超過 90 天"
  }
}
```

3. **HTTP 狀態碼**
- 200: 成功
- 400: 請求參數錯誤
- 404: 資源不存在
- 500: 服務器錯誤

---

## 前端設計

### 頁面結構

```
Layout (共用佈局)
├─ Header (頂部導航欄)
│  ├─ Logo
│  ├─ 系統名稱
│  └─ 用戶信息 (可選)
│
├─ Sidebar (左側菜單)
│  ├─ 儀表板
│  ├─ 報表查詢
│  │  ├─ 在制品報表
│  │  ├─ 維修工單報表
│  │  └─ 設備報表
│  └─ 系統設定 (預留)
│
└─ Content (主內容區)
   └─ 動態路由頁面
```

### 核心頁面設計

#### 1. Dashboard (儀表板頁面)

```
┌────────────────────────────────────────────────────────┐
│  時間範圍選擇: [今日] [本週] [本月] [自定義範圍▼]       │
│  最後更新: 2026-01-14 12:00:00  [🔄 刷新]              │
├────────────────────────────────────────────────────────┤
│  ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐ │
│  │ 在制品    │ │ 完成工單  │ │ 設備稼動率│ │ 良率     │ │
│  │ 125,000  │ │   850    │ │  78.5%   │ │  97.7%  │ │
│  │ ↑ 5.2%   │ │ ↑ 12    │ │ ↓ 2.1%   │ │ ↑ 0.3%  │ │
│  └──────────┘ └──────────┘ └──────────┘ └──────────┘ │
├────────────────────────────────────────────────────────┤
│  ┌────────────────────────┐ ┌──────────────────────┐  │
│  │  生產數量趨勢 (折線圖)  │ │  設備狀態 (餅圖)      │  │
│  │                        │ │                      │  │
│  │  [圖表區域]            │ │  [圖表區域]          │  │
│  │                        │ │                      │  │
│  └────────────────────────┘ └──────────────────────┘  │
├────────────────────────────────────────────────────────┤
│  ┌────────────────────────┐ ┌──────────────────────┐  │
│  │  維修工單完成率 (柱狀圖)    │ │  異常分布 (柱狀圖)    │  │
│  │                        │ │                      │  │
│  │  [圖表區域]            │ │  [圖表區域]          │  │
│  │                        │ │                      │  │
│  └────────────────────────┘ └──────────────────────┘  │
└────────────────────────────────────────────────────────┘
```

#### 2. 報表查詢頁面 (以 WIP 報表為例)

```
┌────────────────────────────────────────────────────────┐
│  篩選條件:                                              │
│  日期範圍: [2026-01-07] 至 [2026-01-14]               │
│  批次號: [________]  工序: [全部▼]  產線: [全部▼]     │
│  [🔍 查詢] [🔄 重置] [📥 匯出 Excel]                   │
├────────────────────────────────────────────────────────┤
│  查詢結果: 共 15,000 筆                                │
│                                                        │
│  ┌──────────────────────────────────────────────────┐ │
│  │ 批次號   │數量 │工序 │產線   │創建時間      │操作 │ │
│  ├──────────────────────────────────────────────────┤ │
│  │ LOT12345 │500  │SMT  │LINE-01│2026-01-14...│詳情│ │
│  │ LOT12346 │450  │AOI  │LINE-02│2026-01-14...│詳情│ │
│  │ ...      │     │     │       │             │    │ │
│  └──────────────────────────────────────────────────┘ │
│                                                        │
│  [◀ 上一頁]  1 / 300  [下一頁 ▶]  每頁: [50▼] 筆     │
└────────────────────────────────────────────────────────┘
```

### 組件設計

#### 核心可復用組件

1. **DateRangePicker** - 日期範圍選擇器
2. **DataTable** - 數據表格 (支援排序、分頁)
3. **LineChart** - 折線圖組件
4. **PieChart** - 餅圖組件
5. **BarChart** - 柱狀圖組件
6. **GaugeChart** - 儀表盤組件
7. **StatCard** - 統計卡片組件
8. **ExportButton** - 匯出按鈕組件

---

## 性能優化策略

### 1. 數據庫查詢優化

#### 策略 A: 強制使用時間範圍
```python
# 所有查詢必須包含時間範圍限制
def validate_date_range(start_date, end_date):
    if (end_date - start_date).days > 90:
        raise ValueError("日期範圍不能超過 90 天")
```

#### 策略 B: 使用索引
```sql
-- 確保查詢條件使用索引欄位
WHERE CREATETIME >= :start_date
  AND CREATETIME < :end_date
  AND LOT = :lot  -- LOT 欄位有索引
```

#### 策略 C: 查詢結果限制
```python
# 默認限制返回行數
DEFAULT_PAGE_SIZE = 50
MAX_PAGE_SIZE = 500
```

### 2. 緩存策略

#### 前端緩存 (React Query)
```typescript
// 查詢結果緩存 5 分鐘
const { data } = useQuery({
  queryKey: ['dashboard', dateRange],
  queryFn: fetchDashboardData,
  staleTime: 5 * 60 * 1000,  // 5 分鐘
  cacheTime: 10 * 60 * 1000  // 10 分鐘
});
```

#### 後端緩存 (Redis - 可選)
```python
# 儀表板數據緩存 10 分鐘
@cache(ttl=600, key_prefix="dashboard")
async def get_dashboard_summary(date_range: str):
    # 查詢數據庫
    pass
```

### 3. 數據聚合優化

#### 在數據庫層進行聚合
```sql
-- 優先在數據庫層完成聚合計算
SELECT
  TRUNC(CREATETIME) as date,
  COUNT(*) as total,
  SUM(LOTQUANTITY) as quantity
FROM DW_MES_WIP
WHERE CREATETIME >= :start_date
GROUP BY TRUNC(CREATETIME)
```

#### 使用 Pandas 進行二次處理
```python
import pandas as pd

# 對查詢結果進行轉換和聚合
df = pd.DataFrame(results)
summary = df.groupby('date').agg({
    'quantity': 'sum',
    'lot': 'count'
})
```

### 4. 前端性能優化

#### 虛擬滾動 (大數據表格)
```typescript
// 使用 react-window 或 react-virtualized
import { FixedSizeList } from 'react-window';
```

#### 圖表數據採樣
```typescript
// 超過 1000 個數據點時進行採樣
if (dataPoints.length > 1000) {
  dataPoints = sampleData(dataPoints, 1000);
}
```

#### 懶加載與代碼分割
```typescript
// 路由級別的代碼分割
const Dashboard = lazy(() => import('./pages/Dashboard'));
const WIPReport = lazy(() => import('./pages/WIPReport'));
```

### 5. 異步處理

#### 大數據量匯出
```python
# 超過 10000 行的匯出使用異步處理
if row_count > 10000:
    task_id = create_export_task(query_params)
    return {"task_id": task_id, "status": "processing"}
else:
    # 同步返回 Excel 文件
    return generate_excel(data)
```

### 性能目標

| 操作 | 目標時間 | 優化手段 |
|------|----------|----------|
| 儀表板加載 | < 3 秒 | 緩存、數據聚合 |
| 報表查詢 (1000 行內) | < 5 秒 | 索引、分頁 |
| 報表查詢 (10000 行內) | < 10 秒 | 索引、分頁、限制範圍 |
| Excel 匯出 (1000 行內) | < 5 秒 | 同步生成 |
| Excel 匯出 (10000+ 行) | 異步處理 | 後台任務隊列 |

---

## 項目結構

### 完整目錄結構

```
DashBoard/
├── README.md                           # 專案說明
├── docs/                               # 文檔
│   ├── System_Architecture_Design.md   # 本文檔
│   ├── MES_Database_Reference.md       # 數據庫參考文檔
│   └── MES_Core_Tables_Analysis_Report.md  # 核心表分析報告
├── apps/                               # 可執行應用
│   └── templates/                      # Web UI 模板
├── scripts/                            # 啟動腳本
├── tools/                              # 工具腳本
├── data/                               # 產出資料
│
├── backend/                            # Python 後端
│   ├── .env.example                    # 環境變量範例
│   ├── .env                            # 環境變量 (不納入版本控制)
│   ├── requirements.txt                # Python 依賴
│   ├── main.py                         # 應用入口 (開發用)
│   │
│   └── app/
│       ├── __init__.py
│       ├── main.py                     # FastAPI 應用實例
│       ├── config.py                   # 配置管理
│       ├── database.py                 # 數據庫連接與連接池
│       │
│       ├── models/                     # 數據模型
│       │   ├── __init__.py
│       │   ├── schemas.py              # Pydantic 數據模型
│       │   └── queries.py              # SQL 查詢定義
│       │
│       ├── routers/                    # API 路由
│       │   ├── __init__.py
│       │   ├── dashboard.py            # 儀表板 API
│       │   ├── reports.py              # 報表查詢 API
│       │   │   ├── wip.py              # 在制品報表
│       │   │   ├── job.py              # 維修工單報表
│       │   │   └── equipment.py        # 設備報表
│       │   └── export.py               # 匯出功能 API
│       │
│       ├── services/                   # 業務邏輯層
│       │   ├── __init__.py
│       │   ├── dashboard_service.py    # 儀表板業務邏輯
│       │   ├── report_service.py       # 報表業務邏輯
│       │   ├── export_service.py       # 匯出業務邏輯
│       │   └── cache_service.py        # 緩存服務 (可選)
│       │
│       ├── utils/                      # 工具函數
│       │   ├── __init__.py
│       │   ├── query_builder.py        # SQL 查詢構建器
│       │   ├── excel_generator.py      # Excel 生成器
│       │   ├── date_utils.py           # 日期處理工具
│       │   └── validators.py           # 數據驗證工具
│       │
│       └── middleware/                 # 中間件 (可選)
│           ├── __init__.py
│           └── error_handler.py        # 錯誤處理中間件
│
├── frontend/                           # React 前端
│   ├── .env.example                    # 環境變量範例
│   ├── .env.development                # 開發環境變量
│   ├── .env.production                 # 生產環境變量
│   ├── package.json                    # NPM 依賴
│   ├── tsconfig.json                   # TypeScript 配置
│   ├── vite.config.ts                  # Vite 配置
│   ├── index.html                      # HTML 模板
│   │
│   ├── public/                         # 靜態資源
│   │   └── logo.png
│   │
│   └── src/
│       ├── main.tsx                    # 應用入口
│       ├── App.tsx                     # 根組件
│       ├── vite-env.d.ts              # Vite 類型定義
│       │
│       ├── pages/                      # 頁面組件
│       │   ├── Dashboard/              # 儀表板頁面
│       │   │   ├── index.tsx
│       │   │   ├── Dashboard.module.css
│       │   │   └── components/
│       │   │       ├── StatCards.tsx
│       │   │       ├── ProductionTrend.tsx
│       │   │       └── EquipmentStatus.tsx
│       │   │
│       │   ├── Reports/                # 報表頁面
│       │   │   ├── WIPReport/
│       │   │   │   ├── index.tsx
│       │   │   │   └── WIPReport.module.css
│       │   │   ├── JobReport/
│       │   │   │   └── index.tsx
│       │   │   └── EquipmentReport/
│       │   │       └── index.tsx
│       │   │
│       │   └── NotFound/               # 404 頁面
│       │       └── index.tsx
│       │
│       ├── components/                 # 可復用組件
│       │   ├── Layout/                 # 佈局組件
│       │   │   ├── Layout.tsx
│       │   │   ├── Header.tsx
│       │   │   ├── Sidebar.tsx
│       │   │   └── Content.tsx
│       │   │
│       │   ├── charts/                 # 圖表組件
│       │   │   ├── LineChart.tsx
│       │   │   ├── PieChart.tsx
│       │   │   ├── BarChart.tsx
│       │   │   └── GaugeChart.tsx
│       │   │
│       │   ├── filters/                # 篩選器組件
│       │   │   ├── DateRangePicker.tsx
│       │   │   └── FilterPanel.tsx
│       │   │
│       │   ├── tables/                 # 表格組件
│       │   │   ├── DataTable.tsx
│       │   │   └── Pagination.tsx
│       │   │
│       │   └── common/                 # 通用組件
│       │       ├── Loading.tsx
│       │       ├── ErrorBoundary.tsx
│       │       └── ExportButton.tsx
│       │
│       ├── services/                   # API 服務
│       │   ├── api.ts                  # Axios 實例配置
│       │   ├── dashboardApi.ts         # 儀表板 API
│       │   ├── reportApi.ts            # 報表 API
│       │   └── exportApi.ts            # 匯出 API
│       │
│       ├── hooks/                      # 自定義 Hooks
│       │   ├── useDashboard.ts         # 儀表板數據 Hook
│       │   ├── useReport.ts            # 報表數據 Hook
│       │   └── useExport.ts            # 匯出功能 Hook
│       │
│       ├── store/                      # 狀態管理
│       │   └── useStore.ts             # Zustand Store
│       │
│       ├── types/                      # TypeScript 類型定義
│       │   ├── index.ts
│       │   ├── dashboard.ts
│       │   ├── report.ts
│       │   └── api.ts
│       │
│       ├── utils/                      # 工具函數
│       │   ├── formatters.ts           # 格式化函數
│       │   ├── validators.ts           # 驗證函數
│       │   ├── exportExcel.ts          # Excel 匯出
│       │   └── constants.ts            # 常量定義
│       │
│       ├── styles/                     # 全局樣式
│       │   ├── index.css               # 全局 CSS
│       │   └── variables.css           # CSS 變量
│       │
│       └── router/                     # 路由配置
│           └── index.tsx               # 路由定義
│
├── docs/                               # 開發文檔
│   ├── API.md                          # API 接口文檔
│   ├── DEPLOYMENT.md                   # 部署文檔
│   └── DEVELOPMENT.md                  # 開發指南
│
└── scripts/                            # 工具腳本
    ├── generate_documentation.py       # 生成數據庫文檔
    └── test_oracle_connection.py       # 測試數據庫連接
```

---

## 開發計劃

### Phase 1: 環境搭建與基礎架構 (預計 2-3 天)

**目標**: 建立完整的開發環境和項目骨架

#### 後端任務
- [ ] 初始化 FastAPI 項目
- [ ] 配置 Oracle 數據庫連接
- [ ] 實現連接池管理
- [ ] 建立基礎 API 結構 (routers, services, models)
- [ ] 實現統一錯誤處理
- [ ] 撰寫第一個測試 API (`/api/health`)

#### 前端任務
- [ ] 使用 Vite 初始化 React + TypeScript 項目
- [ ] 安裝並配置 Ant Design
- [ ] 安裝並配置 ECharts
- [ ] 建立基礎佈局結構 (Layout, Header, Sidebar)
- [ ] 配置路由 (React Router)
- [ ] 配置 Axios 和 React Query
- [ ] 建立開發環境配置

#### 驗收標準
- ✅ 後端 API 能成功連接 Oracle 數據庫
- ✅ 前端能成功調用後端 `/api/health` 接口
- ✅ 基礎佈局能正常顯示

---

### Phase 2: 儀表板開發 (預計 5-7 天)

**目標**: 實現儀表板頁面，展示關鍵業務指標

#### 後端任務
- [ ] 實現 `/api/dashboard/summary` API
  - 在制品總數
  - 完成維修工單數
  - 設備稼動率
  - 良率統計
- [ ] 實現 `/api/dashboard/production-trend` API (生產趨勢數據)
- [ ] 實現 `/api/dashboard/equipment-status` API (設備狀態分布)
- [ ] 實現 `/api/dashboard/job-completion` API (維修工單完成統計)
- [ ] 加入查詢結果緩存 (內存緩存或 Redis)
- [ ] 性能測試與優化 (確保 < 3 秒響應)

#### 前端任務
- [ ] 開發儀表板頁面佈局
- [ ] 實現 StatCard 組件 (統計卡片)
- [ ] 實現 LineChart 組件 (生產趨勢折線圖)
- [ ] 實現 PieChart 組件 (設備狀態餅圖)
- [ ] 實現 BarChart 組件 (工單完成柱狀圖)
- [ ] 實現日期範圍選擇器
- [ ] 整合 React Query 進行數據獲取
- [ ] 實現自動刷新功能 (每 5 分鐘)

#### 驗收標準
- ✅ 儀表板能正確顯示所有關鍵指標
- ✅ 圖表數據能正確渲染
- ✅ 日期篩選功能正常
- ✅ 頁面加載時間 < 3 秒

---

### Phase 3: 報表查詢模塊開發 (預計 7-10 天)

**目標**: 實現核心報表查詢功能

**等待 Power BI 截圖確認具體報表類型後開始**

#### 預計報表類型 (待確認)
1. **在制品 (WIP) 報表**
2. **工單 (Job) 報表**
3. **設備稼動率報表**
4. **批次追蹤報表**
5. **物料消耗報表**

#### 後端任務 (以 WIP 報表為例)
- [ ] 實現 `/api/reports/wip` API
- [ ] 實現篩選條件驗證 (日期範圍、批次號等)
- [ ] 實現分頁查詢
- [ ] 實現排序功能
- [ ] 實現多條件組合查詢
- [ ] 性能優化 (確保 < 10 秒響應)

#### 前端任務
- [ ] 開發報表查詢頁面框架
- [ ] 實現 FilterPanel 組件 (篩選面板)
- [ ] 實現 DataTable 組件 (數據表格，支援排序、分頁)
- [ ] 實現 Pagination 組件
- [ ] 整合 API 調用
- [ ] 實現查詢條件保存 (localStorage)

#### 每個報表重複以上步驟

#### 驗收標準
- ✅ 所有報表查詢功能正常
- ✅ 篩選、排序、分頁功能正常
- ✅ 查詢響應時間 < 10 秒
- ✅ 大數據量表格渲染流暢

---

### Phase 4: 匯出功能開發 (預計 3-4 天)

**目標**: 實現 Excel 報表匯出

#### 後端任務
- [ ] 實現 `/api/export/excel` API (同步匯出)
- [ ] 實現 `/api/export/excel-async` API (異步匯出)
- [ ] 實現 `/api/export/status/{task_id}` API (查詢進度)
- [ ] 實現 Excel 生成邏輯 (openpyxl)
- [ ] 實現異步任務隊列 (可選，使用 Celery 或簡單的線程池)
- [ ] 實現文件清理機制 (定期刪除過期文件)

#### 前端任務
- [ ] 實現 ExportButton 組件
- [ ] 實現匯出進度顯示 (Progress Bar)
- [ ] 實現文件下載邏輯
- [ ] 實現異步匯出的輪詢機制
- [ ] 錯誤處理與用戶提示

#### 驗收標準
- ✅ 小數據量 (< 1000 行) 能同步匯出
- ✅ 大數據量 (> 10000 行) 能異步匯出
- ✅ Excel 格式正確，包含標題、數據、樣式
- ✅ 匯出進度正常顯示

---

### Phase 5: 優化與測試 (預計 3-5 天)

**目標**: 性能優化、測試、bug 修復

#### 優化任務
- [ ] 數據庫查詢性能測試
- [ ] API 響應時間測試
- [ ] 前端頁面加載速度優化
- [ ] 內存使用優化
- [ ] 緩存策略調整

#### 測試任務
- [ ] 單元測試 (後端核心邏輯)
- [ ] 集成測試 (API 端到端測試)
- [ ] 前端組件測試
- [ ] 瀏覽器兼容性測試 (Chrome, Edge, Firefox)
- [ ] 響應式測試 (不同解析度)

#### 文檔任務
- [ ] 完善 API 文檔
- [ ] 撰寫部署文檔
- [ ] 撰寫用戶手冊

#### 驗收標準
- ✅ 所有性能指標達標
- ✅ 無嚴重 bug
- ✅ 文檔完整

---

### Phase 6: 部署上線 (預計 2-3 天)

**目標**: 部署到測試/生產環境

#### 部署任務
- [ ] 準備生產環境配置
- [ ] 後端部署 (建議使用 Docker)
- [ ] 前端打包與部署
- [ ] 數據庫連接測試
- [ ] 性能監控設置
- [ ] 日誌系統配置

#### 驗收標準
- ✅ 系統能在生產環境正常運行
- ✅ 所有功能測試通過
- ✅ 監控與日誌正常

---

## 部署方案

### 部署架構

```
生產環境:
┌──────────────────────────────────────────────┐
│  Web Server (Nginx)                          │
│  - 靜態文件服務 (React 打包產物)              │
│  - 反向代理 (FastAPI)                        │
│  - SSL 證書                                  │
└──────────────────────────────────────────────┘
                    ↓
┌──────────────────────────────────────────────┐
│  Application Server (FastAPI + Uvicorn)      │
│  - 運行在 Gunicorn + Uvicorn Workers         │
│  - 環境變量配置                               │
└──────────────────────────────────────────────┘
                    ↓
┌──────────────────────────────────────────────┐
│  Oracle Database (外部)                      │
│  - 10.1.1.58:1521                           │
└──────────────────────────────────────────────┘
```

### 部署方式選項

#### 選項 A: Docker 容器化部署 (推薦)

**優點**: 環境一致性、易於遷移、資源隔離

```yaml
# docker-compose.yml
version: '3.8'

services:
  backend:
    build: ./backend
    ports:
      - "8000:8000"
    environment:
      - DB_HOST=10.1.1.58
      - DB_PORT=1521
      - DB_SERVICE=DWDB
      - DB_USER=MBU1_R
      - DB_PASSWORD=${DB_PASSWORD}
    restart: unless-stopped

  frontend:
    build: ./frontend
    ports:
      - "80:80"
    depends_on:
      - backend
    restart: unless-stopped

  redis:  # 可選
    image: redis:7-alpine
    ports:
      - "6379:6379"
    restart: unless-stopped
```

#### 選項 B: 傳統部署

**後端部署**:
```bash
# 安裝依賴
pip install -r requirements.txt

# 使用 Gunicorn + Uvicorn 運行
gunicorn app.main:app \
  --workers 4 \
  --worker-class uvicorn.workers.UvicornWorker \
  --bind 0.0.0.0:8000
```

**前端部署**:
```bash
# 打包
npm run build

# 將 dist/ 目錄部署到 Nginx
cp -r dist/* /var/www/html/
```

### Nginx 配置範例

```nginx
server {
    listen 80;
    server_name your-domain.com;

    # 前端靜態文件
    location / {
        root /var/www/html;
        index index.html;
        try_files $uri $uri/ /index.html;
    }

    # API 反向代理
    location /api {
        proxy_pass http://localhost:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }

    # 增加超時時間 (處理大數據查詢)
    proxy_connect_timeout 300s;
    proxy_send_timeout 300s;
    proxy_read_timeout 300s;
}
```

### 環境變量配置

**後端 .env**
```ini
# 數據庫配置
DB_HOST=10.1.1.58
DB_PORT=1521
DB_SERVICE=DWDB
DB_USER=MBU1_R
DB_PASSWORD=Pj2481mbu1

# 應用配置
APP_ENV=production
DEBUG=False
LOG_LEVEL=INFO

# 緩存配置 (可選)
REDIS_HOST=localhost
REDIS_PORT=6379
CACHE_TTL=600

# CORS 配置
CORS_ORIGINS=["https://your-domain.com"]
```

**前端 .env.production**
```ini
VITE_API_BASE_URL=https://your-domain.com/api
VITE_APP_TITLE=MES 報表系統
```

### 監控與日誌

#### 應用監控
- 使用 FastAPI 內建的 `/docs` 端點監控 API
- 可選: Prometheus + Grafana

#### 日誌管理
```python
# 後端日誌配置
import logging

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('app.log'),
        logging.StreamHandler()
    ]
)
```

---

## 附錄

### A. 待確認事項清單

1. **Power BI 報表截圖** - 用於前端 UI 設計參考
2. **具體報表類型** - 需要開發哪些報表
3. **部署環境** - 是否有專用服務器，是否使用 Docker
4. **用戶數量** - 預計並發用戶數
5. **數據更新頻率** - MES 數據多久更新一次
6. **是否需要登入功能** - 當前設計為無登入，是否需要調整

### B. 技術風險評估

| 風險項 | 影響程度 | 應對策略 |
|--------|----------|----------|
| Oracle 數據庫性能瓶頸 | 高 | 強制時間範圍限制、緩存、分頁 |
| 大數據量查詢超時 | 中 | 異步處理、查詢優化 |
| 前端圖表渲染性能 | 中 | 數據採樣、虛擬滾動 |
| 並發用戶過多 | 低 | 連接池、負載均衡 |

### C. 後續擴展計劃

**Phase 7 及以後 (可選)**
- [ ] 用戶登入與權限管理
- [ ] 數據權限控制 (按產線、部門)
- [ ] 報表自定義功能 (用戶自行配置查詢條件)
- [ ] 報表訂閱與郵件推送
- [ ] 移動端適配
- [ ] 實時數據推送 (WebSocket)
- [ ] 數據分析與預測功能 (Machine Learning)

### D. 相關文檔索引

- **[MES_Database_Reference.md](MES_Database_Reference.md)** - 數據庫完整結構參考（16張表詳細說明）
- **[MES_Core_Tables_Analysis_Report.md](MES_Core_Tables_Analysis_Report.md)** - 核心表深度分析報告（表性質、關鍵欄位、查詢策略）⭐
- API 文檔 - 待開發後生成 (FastAPI 自動生成 `/docs`)
- 部署文檔 - 待開發 (docs/DEPLOYMENT.md)
- 開發指南 - 待開發 (docs/DEVELOPMENT.md)

### E. 關鍵發現總結

#### 1. 表性質分類（重要！）
經過深入分析，16 張表分為兩大類：
- **現況快照表（4張）**: WIP, RESOURCE, CONTAINER, JOB - 數據會被更新
- **歷史累積表（10張）**: RESOURCESTATUS, LOTWIPHISTORY 等 - 只新增不修改

**影響**：
- DW_MES_WIP 雖然名為"在制品表"，但實際包含 7700 萬行歷史數據
- 所有大表（>1000萬行）查詢時**必須**加入時間範圍限制
- RESOURCESTATUS 表記錄狀態變更，需用 `OLDLASTSTATUSCHANGEDATE` 和 `LASTSTATUSCHANGEDATE` 計算狀態持續時間

#### 2. 關鍵時間欄位對照

| 表名 | 關鍵時間欄位 | 用途 |
|------|-------------|------|
| DW_MES_WIP | TXNDATE | 查詢過濾用 |
| DW_MES_RESOURCESTATUS | OLDLASTSTATUSCHANGEDATE, LASTSTATUSCHANGEDATE | 計算狀態持續時間 |
| DW_MES_LOTWIPHISTORY | TRACKINTIMESTAMP, MOVEINTIMESTAMP | 計算 Cycle Time |
| DW_MES_RESOURCESTATUS_SHIFT | SHIFTDATE | 班次查詢 |

#### 3. 核心業務場景

基於表分析，系統應重點支援以下業務場景：
1. **在制品（WIP）看板** - 使用 DW_MES_WIP
2. **設備稼動率（OEE）報表** - 使用 DW_MES_RESOURCESTATUS ⭐
3. **批次生產履歷追溯** - 使用 DW_MES_LOTWIPHISTORY
4. **工序 Cycle Time 分析** - 使用 DW_MES_LOTWIPHISTORY
5. **設備產出與效率分析** - 使用 DW_MES_HM_LOTMOVEOUT
6. **Hold 批次分析** - 使用 DW_MES_WIP + DW_MES_HOLDRELEASEHISTORY
7. **設備維修工單進度追蹤** - 使用 DW_MES_JOB
8. **良率分析** - 使用 DW_MES_LOTREJECTHISTORY

---

## 文檔變更記錄

| 版本 | 日期 | 變更內容 | 作者 |
|------|------|----------|------|
| 1.0 | 2026-01-14 | 初始版本建立 | Claude (AI Architect) |
| 1.1 | 2026-01-14 | 更新數據庫設計章節，新增表性質分類、關鍵欄位分析、查詢優化建議 | Claude (AI Architect) |

---

## 聯系方式

如有技術問題或需求變更，請及時更新本文檔。

**文檔結束**


