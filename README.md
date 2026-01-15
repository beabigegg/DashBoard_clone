# MES 報表查詢系統

基於 Vite/React + Python FastAPI 的 MES 數據報表查詢與可視化系統

---

## 專案狀態

- ✅ 數據庫分析完成
- ✅ 系統架構設計完成
- ✅ 數據查詢工具完成
- ⏳ 待提供 Power BI 報表設計參考
- ⏳ 系統開發進行中

---

## 快速開始

### 1. WIP 在制品報表（當前可用）⭐

查詢當前在制品的數量統計，支援按工序、工作中心、產品線分組查看。

```bash
# 雙擊運行
scripts\啟動Dashboard.bat
```

然後訪問: **http://localhost:5000**
入口頁面可用上方 Tab 切換「WIP 報表 / 數據表查詢工具」。

**功能**:
- 📊 總覽統計（總 LOT 數、總數量、總片數）
- 🔍 按 SPEC 和 WORKCENTER 統計
- 📈 按產品線統計（匯總 + 明細）
- ⏱️ 可選時間範圍（1-30 天）
- 🎨 美觀的 Web UI

詳細說明: [WIP報表說明.md](docs/WIP報表說明.md)

---

### 2. 查看數據表內容（當前可用）

#### 方法 A: 自動初始化（推薦，首次使用）

```bash
# 步驟 1: 初始化環境（只需執行一次）
雙擊運行: scripts\0_初始化環境.bat

# 步驟 2: 啟動服務器
雙擊運行: scripts\啟動Dashboard.bat
```

#### 方法 B: 使用 Python 直接啟動

```bash
# 如果您的環境已安裝 Flask, Pandas, oracledb
python apps\快速啟動.py
```

#### 方法 C: 手動啟動

```bash
# 1. 創建虛擬環境（首次）
python -m venv venv

# 2. 安裝依賴（首次）
venv\Scripts\pip.exe install -r requirements.txt

# 3. 啟動服務器
venv\Scripts\python.exe apps\portal.py
```

然後訪問: **http://localhost:5000**

**功能**:
- 📊 按表性質分類（現況表/歷史表/輔助表）
- 🔍 查看各表最後 1000 筆資料
- ⏱️ 大表自動按時間欄位排序
- 📋 顯示欄位列表和數據樣本

---

## 文檔結構

### 核心文檔

| 文檔 | 用途 | 適用對象 |
|------|------|---------|
| **[System_Architecture_Design.md](docs/System_Architecture_Design.md)** | 系統架構設計完整文檔 | 架構師、開發者 |
| **[MES_Core_Tables_Analysis_Report.md](docs/MES_Core_Tables_Analysis_Report.md)** | 核心表深度分析報告 ⭐ | 開發者、數據分析師 |
| **[MES_Database_Reference.md](docs/MES_Database_Reference.md)** | 數據庫完整結構參考 | 開發者 |

### 文檔關係

```
docs/System_Architecture_Design.md (系統設計總覽)
    ↓ 引用
docs/MES_Core_Tables_Analysis_Report.md (表詳細分析)
    ↓ 引用
docs/MES_Database_Reference.md (表結構參考)
```

---

## 關鍵發現總結

### 1. 表性質分類

經過深入分析，16 張核心表分為：

- **現況快照表（4張）**: WIP, RESOURCE, CONTAINER, JOB
- **歷史累積表（10張）**: RESOURCESTATUS, LOTWIPHISTORY 等
- **輔助表（2張）**: PARTREQUESTORDER, PJ_COMBINEDASSYLOTS

### 2. 重要認知更新

⚠️ **DW_MES_WIP** 雖名為"在制品表"，但實際包含 **7700 萬行歷史累積數據**

⚠️ **DW_MES_RESOURCESTATUS** 記錄設備狀態每次變更，需用兩個時間欄位計算持續時間：
```sql
狀態持續時間 = (LASTSTATUSCHANGEDATE - OLDLASTSTATUSCHANGEDATE) * 24 小時
```

### 3. 查詢優化鐵律

**所有超過 1000 萬行的表，查詢時必須加入時間範圍限制！**

```sql
-- DW_MES_WIP (7700萬行)
WHERE TXNDATE >= TRUNC(SYSDATE) - 7

-- DW_MES_RESOURCESTATUS (6500萬行)
WHERE OLDLASTSTATUSCHANGEDATE >= TRUNC(SYSDATE) - 7

-- DW_MES_LOTWIPHISTORY (5300萬行)
WHERE TRACKINTIMESTAMP >= TRUNC(SYSDATE) - 7
```

**建議時間範圍**:
- 儀表板查詢: 最近 **7 天**
- 報表查詢: 最多 **30 天**
- 歷史趨勢: 最多 **90 天**

---

## 核心業務場景

基於表分析，系統應重點支援：

1. ✅ **在制品（WIP）看板** - 使用 DW_MES_WIP
2. ⭐ **設備稼動率（OEE）報表** - 使用 DW_MES_RESOURCESTATUS
3. ✅ **批次生產履歷追溯** - 使用 DW_MES_LOTWIPHISTORY
4. ✅ **工序 Cycle Time 分析** - 使用 DW_MES_LOTWIPHISTORY
5. ✅ **設備產出與效率分析** - 使用 DW_MES_HM_LOTMOVEOUT
6. ✅ **Hold 批次分析** - 使用 DW_MES_WIP + DW_MES_HOLDRELEASEHISTORY
7. ✅ **設備維修工單進度追蹤** - 使用 DW_MES_JOB
8. ✅ **良率分析** - 使用 DW_MES_LOTREJECTHISTORY

---

## 技術架構

### 前端技術棧
- React 18 + TypeScript
- Vite 5.x (構建工具)
- Ant Design 5.x (UI 組件庫)
- ECharts 5.x (圖表庫)
- React Query 5.x (數據管理)

### 後端技術棧
- Python 3.11+
- FastAPI (Web 框架)
- oracledb 2.x (Oracle 驅動)
- Pandas 2.x (數據處理)

### 數據庫
- Oracle Database 19c Enterprise Edition
- 主機: 10.1.1.58:1521
- 服務名: DWDB
- 用戶: MBU1_R (只讀)

---

## 開發計劃

### Phase 1: 環境搭建與基礎架構 ⏳
- [ ] 初始化 FastAPI 項目
- [ ] 初始化 Vite + React 項目
- [ ] 建立數據庫連接池
- [ ] 實現基礎 API 結構

### Phase 2: 儀表板開發 ⏳
- [ ] 實現儀表板 API
- [ ] 開發儀表板前端頁面
- [ ] 實現圖表組件

### Phase 3: 報表查詢模塊開發 ⏳
待 Power BI 截圖確認

### Phase 4: 匯出功能開發 ⏳
- [ ] 實現 Excel 匯出
- [ ] 實現異步匯出

### Phase 5: 優化與測試 ⏳
- [ ] 性能優化
- [ ] 測試

### Phase 6: 部署上線 ⏳
- [ ] 準備部署環境
- [ ] 部署

---

## 專案文件

```
DashBoard/
├── README.md                           # 本文件
├── docs/                               # 專案文檔
├── scripts/                            # 啟動腳本
├── apps/                               # 可執行應用
│   └── templates/                      # Web UI 模板
├── tools/                              # 工具腳本
├── data/                               # 產出資料
├── requirements.txt                    # Python 依賴
├── venv/                               # Python 虛擬環境
│
├── backend/                            # 後端（待開發）
└── frontend/                           # 前端（待開發）
```

---

## 待確認事項

1. ⏳ **Power BI 報表截圖** - 用於前端 UI 設計參考
2. ⏳ **具體報表類型** - 從 8 個業務場景中選擇優先開發的 3-5 個
3. ⏳ **部署環境** - 是否有專用服務器，是否使用 Docker
4. ⏳ **並發用戶數** - 預計同時使用的用戶數量

---

## 聯絡方式

如有技術問題或需求變更，請及時更新相關文檔。

---

**文檔版本**: 1.0
**最後更新**: 2026-01-14


