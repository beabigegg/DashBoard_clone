# Reject 歷史績效表設計說明

## 目標
使用 `DW_MES_LOTREJECTHISTORY` 為主，輔以其他維度表，建立可直接用於報表的 `reject` 歷史績效表（按日彙總），解決原始資料直接查詢時的績效與一致性問題。

## 使用資料表
- `DWH.DW_MES_LOTREJECTHISTORY`: 不良/報廢事實表（主來源）
- `DWH.DW_MES_CONTAINER`: 補齊 `PJ_TYPE`、`PRODUCTLINENAME`、`MFGORDERNAME`
- `DWH.DW_MES_SPEC_WORKCENTER_V`: 對應 `WORKCENTER_GROUP` 與排序欄位
- `DWH.ERP_PJ_WIP_SCRAP_REASONS_EXCLUDE`: 良率排除政策表（`ENABLE_FLAG='Y'` 代表不納入良率計算）

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

## 排除政策與前端開關
- 預設模式：排除 `ERP_PJ_WIP_SCRAP_REASONS_EXCLUDE` 中 `ENABLE_FLAG='Y'` 的報廢原因。
- 可切換模式：提供 `include_excluded_scrap=true|false` 讓使用者決定是否納入。
- 前端頁面提供「納入不計良率報廢」開關，並同步影響 summary/trend/pareto/list/export。
- 排除原因清單採全表快取，預設每日刷新一次（Redis 優先、記憶體 fallback）。

## API 與欄位契約
- `GET /api/reject-history/options`
  - 回傳 `workcenter_groups`、`reasons` 與政策 `meta`
- `GET /api/reject-history/summary`
  - 回傳 `MOVEIN_QTY`、`REJECT_TOTAL_QTY`、`DEFECT_QTY`、`REJECT_RATE_PCT`、`DEFECT_RATE_PCT`、`REJECT_SHARE_PCT`、`AFFECTED_LOT_COUNT`、`AFFECTED_WORKORDER_COUNT`
- `GET /api/reject-history/trend`
  - 回傳趨勢 `items[]`，每筆含 `bucket_date`、`REJECT_TOTAL_QTY`、`DEFECT_QTY`、`REJECT_RATE_PCT`、`DEFECT_RATE_PCT`
- `GET /api/reject-history/reason-pareto`
  - 支援 `metric_mode=reject_total|defect`
  - 支援 `pareto_scope=top80|all`（預設 `top80`）
- `GET /api/reject-history/list`
  - 分頁回傳 `items[]` 與 `pagination`
  - 明細保留五個 reject 欄位（`REJECT_QTY`、`STANDBY_QTY`、`QTYTOPROCESS_QTY`、`INPROCESS_QTY`、`PROCESSED_QTY`）與 `DEFECT_QTY`
- `GET /api/reject-history/export`
  - CSV 欄位與 list 語義一致，含 `REJECT_TOTAL_QTY` 與 `DEFECT_QTY`

## 前端視覺與互動
- 主要區塊：
  - Header（語義 badge + 更新時間）
  - 篩選區（時間、原因、`WORKCENTER_GROUP`、政策開關、Pareto 前 80% 開關）
  - KPI（8 張卡，Reject 暖色語義 / Defect 冷色語義）
  - 趨勢圖（報廢量與報廢率分圖）
  - Pareto（柱狀 + 累積線）與明細表
- 互動規則：
  - Pareto 點選原因後，會套用為 active filter chip 並重查
  - 再次點選同原因會取消篩選
  - 預設僅顯示累計前 80%，可切換顯示完整 Pareto
  - 匯出 CSV 使用目前畫面相同篩選條件

## 交付檔案
- 建表 + 刷新 SQL：`docs/reject_history_performance.sql`
- 可被應用層直接載入的查詢 SQL：`src/mes_dashboard/sql/reject_history/performance_daily.sql`

## 上線與回滾策略
- 上線策略：
  - 先維持 `data/page_status.json` 中 `/reject-history` 為 `dev`
  - 完成 UAT 後再改為 `released`
- 回滾策略：
  - 將 `/reject-history` 狀態切回 `dev` 或移除導航入口
  - 保留 API 與既有頁面，不影響既有報表
- 快取策略：
  - 排除政策表每日全表刷新（預設 86400 秒）
  - Redis 異常時退回記憶體快取，不阻斷查詢

## 驗證紀錄（2026-02-13）
- 後端/整合測試：
  - `pytest -q tests/test_reject_history_service.py tests/test_scrap_reason_exclusion_cache.py tests/test_reject_history_routes.py tests/test_reject_history_shell_coverage.py tests/test_portal_shell_wave_b_native_smoke.py::test_reject_history_native_smoke_query_sections_and_export tests/test_app_factory.py::AppFactoryTests::test_routes_registered`
  - 結果：`22 passed`
- 前端建置：
  - `cd frontend && npm run build`
  - 結果：成功產出 `reject-history.html/js/css`，並完成 dist 複製流程

## 建議排程
- 每日跑前一日增量：
  - `:start_date = TRUNC(SYSDATE - 1)`
  - `:end_date = TRUNC(SYSDATE - 1)`
- 每月第一天補跑前 31 天，避免補數漏失。

## 已知環境備註
- `tests/test_navigation_contract.py` 需要 `docs/migration/portal-no-iframe/baseline_drawer_visibility.json`。目前工作區缺少此 baseline 檔案，屬既有環境缺口，與本次 reject-history 開發內容無直接耦合。
