# Reject 歷史績效表設計說明

## 目標
使用 `DW_MES_LOTREJECTHISTORY` 為主，輔以其他維度表，建立可直接用於報表的 `reject` 歷史績效表（按日彙總），解決原始資料直接查詢時的績效與一致性問題。

## 使用資料表
- `DWH.DW_MES_LOTREJECTHISTORY`: 不良/報廢事實表（主來源）
- `DWH.DW_MES_CONTAINER`: 補齊 `PJ_TYPE`、`PRODUCTLINENAME`、`MFGORDERNAME`
- `DWH.DW_MES_SPEC_WORKCENTER_V`: 對應 `WORKCENTER_GROUP` 與排序欄位

## 資料評估重點（2026-02-13，近 30 天樣本）
- `DW_MES_LOTREJECTHISTORY` 共 `230,074` 筆；`HISTORYMAINLINEID` 僅 `75,683` 個。
- `HISTORYMAINLINEID` 多筆情況明顯（`30,784` 個主事件，平均每主事件 `6.02` 筆），代表同主事件會拆成多個 `LOSSREASONNAME`。
- 若直接加總 `MOVEINQTY`，分母會被重複計算。近 30 天樣本中：
  - `NAIVE_MOVEIN = 44,836,693,831`
  - `DEDUP_MOVEIN = 35,658,750,247`
  - 膨脹比 `1.2574`（約高估 25.74%）
- 指標定義依業務規則分開處理：
  - `REJECT_TOTAL_QTY = REJECTQTY + STANDBYQTY + QTYTOPROCESS + INPROCESSQTY + PROCESSEDQTY`（扣帳報廢）
  - `DEFECT_QTY = DEFECTQTY`（不扣帳報廢）
- `DW_MES_SPEC_WORKCENTER_V` 若直接以 `WORK_CENTER` join 會放大筆數；需先彙整為唯一 `WORK_CENTER -> GROUP/SEQUENCE` 對照表再 join。

## 績效表欄位與計算邏輯
- 粒度：`日 + 工站群組 + 工站 + 站點規格 + 設備 + 產品維度 + 不良原因`
- 核心指標：
  - `REJECT_EVENT_ROWS`: 原始 reject 紀錄筆數
  - `AFFECTED_LOT_COUNT`: 受影響 lot 數（distinct `CONTAINERID`）
  - `MOVEIN_QTY`: 以 `HISTORYMAINLINEID` 去重後的投入量
  - `REJECT_QTY`: 原始 `REJECTQTY` 加總（五欄之一）
  - `REJECT_TOTAL_QTY`: 五個 reject 相關欄位加總（扣帳報廢）
  - `DEFECT_QTY`: `DEFECTQTY` 加總（不扣帳報廢）
  - `REJECT_RATE_PCT = REJECT_TOTAL_QTY / MOVEIN_QTY * 100`
  - `DEFECT_RATE_PCT = DEFECT_QTY / MOVEIN_QTY * 100`
  - `REJECT_SHARE_PCT = REJECT_TOTAL_QTY / (REJECT_TOTAL_QTY + DEFECT_QTY) * 100`

## 交付檔案
- 建表 + 刷新 SQL：`docs/reject_history_performance.sql`
- 可被應用層直接載入的查詢 SQL：`src/mes_dashboard/sql/reject_history/performance_daily.sql`

## 建議排程
- 每日跑前一日增量：
  - `:start_date = TRUNC(SYSDATE - 1)`
  - `:end_date = TRUNC(SYSDATE - 1)`
- 每月第一天補跑前 31 天，避免補數漏失。
