# Change Request

## Original Request

新增 EAP ALARM 分析報表頁（新大類「EAP」）：以設備類型+日期做粗粒度 Filter 觸發 RQ async spool（Oracle EAP_EVENT + EAP_EVENT_DETAIL JOIN 寫入 DuckDB parquet），spool 完成後由 DuckDB 推導細粒度 Filter 選項（AlarmText 多選模糊搜索、AlarmCategory 解碼多選、Equipment ID 多選），所有圖表計算（Pareto、趨勢折線、明細表）全在 DuckDB 執行，不二次查 Oracle。

補充說明（對話中確認）：
- 導覽新增「EAP」大類，與現有 WIP/Hold/良率等 MES 大類平行
- Filter 維度：必填（日期範圍、設備類型多選）→ 觸發 spool；可選（設備ID、AlarmText 模糊多選、AlarmCategory 解碼多選）→ DuckDB 計算
- AlarmCategory 需解碼顯示（0=非分類, 1=設備, 2=製程, 3=視覺, 4=機械, 5=電子, 6=通知/供料, 7=品質, 64=繼續錯誤）
- Spool key：date_range + eqp_type_set，細粒度 Filter 改變不重新 spool
- 視圖：摘要卡片、Pareto 圖、趨勢折線（每日/小時堆疊）、明細表（可展開看 DETAIL 參數）
- 資料來源：DWH.EAP_EVENT（索引：LAST_UPDATE_TIME, EQUIPMENT_ID）+ DWH.EAP_EVENT_DETAIL（索引：SEQ_ID）

## Business / User Goal

## Non-goals

## Constraints

## Known Context

## Open Questions

## Requested Delivery Date / Priority
