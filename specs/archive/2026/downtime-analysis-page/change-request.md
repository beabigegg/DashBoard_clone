# Change Request

## Original Request

新增設備停機與維修分析頁面 — 以 DW_MES_RESOURCESTATUS_SHIFT E10 狀態時數為主軸，顯示每日停機時數(UDT/SDT/EGT)、停機原因(OLDREASONNAME)、大類(維修/保養/換型等)，並透過 JOBID 優先 + 時間重疊 fallback 橋接 DW_MES_JOB 工單，呈現症狀/原因細項/維修動作/處理人/等待工時。單頁兼具主管總覽與設備人員明細兩種視角。

## Business / User Goal

- 設備主管：一眼看每天停機多少、是維修還是保養換型、哪台機最常壞、哪個症狀最多
- 設備人員：每筆停機事件對應的工單詳情（症狀/原因/維修動作/等待工時/實際維修工時/處理人）

## Non-goals

- 狀態持續時間 vs JOB 持續時間落差分析（KEY IN / 切換狀態不確實偵測）— 列為 TBD，本次不做
- OEE 計算（已在 resource-history 頁面）

## Constraints

- 停機時數以 DW_MES_RESOURCESTATUS_SHIFT.OLDSTATUSNAME IN ('UDT','SDT','EGT') + HOURS 為唯一事實來源
- 停機原因使用 OLDREASONNAME（近期 100% 有值，已驗證）
- SHIFT.JOBID 自 2025-09 起幾乎全空；採「JOBID 優先 + RESOURCEID+時間重疊 fallback」混合橋接策略
- 明細列無 JOB 對應時仍顯示（對到率約 50% UDT、86% PM），JOB 欄顯示「—」
- 班別跨界切段的同一停機事件在 SHIFT 表會有多筆，後端需合併為單一事件
- 沿用既有 resource_history 的 cache/spool/DuckDB 架構與篩選維度（站別/機種/機台）
- 下週確認 IT 能否補填 JOBID，補填後 spool 需版本鍵失效重建

## Known Context

- 資料來源：DWH.DW_MES_RESOURCESTATUS_SHIFT（E10 狀態時數）、DWH.DW_MES_JOB（維修工單）
- SHIFT.HISTORYID = JOB.RESOURCEID（已驗證 100% 一致）
- 大類映射：維修(EE Repair / EAP Minor stoppage)、保養(EE_PM / MF_PM / PD_PM)、換型換線(Change Type / Change Package / Re Layout / Change Marking Code / Change Model)、換刀清模(Change Tool/Consumables / Clean Mold)、檢查(Prod_QC_Inspection / Prod_PD_inspection / TMTT_*)、待料待指示(Wait For Instructions / No Operator / No Raw Material)、工程(EGT 全部)、其他/未分類(*_NULL 等)
- 參考架構：resource_history 功能（routes/resource_history_routes.py、services/resource_history_service.py、sql/resource_history/*.sql）

## Open Questions

- IT 能否補填 2025-09 起的 SHIFT.JOBID（下週確認）
- 班別跨界合併的 KEY 定義：HISTORYID + OLDSTATUSNAME + OLDREASONNAME + OLDLASTSTATUSCHANGEDATE（最早片段起點）

## Requested Delivery Date / Priority

中優先，等 IT JOBID 確認後啟動實作（預計 2026 年 W24 起）
