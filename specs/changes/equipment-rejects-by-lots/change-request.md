# Change Request

## Original Request

「針對情境B, 應該是找該設備生產過的LOT, 然後顯示LOT的報廢?」

確認：設備頁籤的「報廢」子分頁目前只顯示以該設備名稱登錄的報廢事件（aggregate by EQUIPMENTNAME+LOSSREASONNAME）。應改為：先從 DW_MES_LOTWIPHISTORY 找出在該設備上加工過的所有 CONTAINERID，再到 DW_MES_LOTREJECTHISTORY 查這些批次的所有報廢紀錄（不限報廢事件登錄的設備），以明細列方式顯示。

## Business / User Goal

讓設備報廢子分頁反映「這台設備生產過的批次，最終有哪些報廢」，而非只顯示「報廢事件登錄在這台設備上的資料」。跨站報廢（批次在 A 設備生產，報廢在 QC 站登錄）目前會漏掉。

## Non-goals

- 不修改 LOT 頁籤的 lot_rejects（已正確以 CONTAINERID 查詢）
- 不修改 jobs 子分頁的查詢邏輯
- 不新增欄位到 LOTWIPHISTORY 或 LOTREJECTHISTORY

## Constraints

- LOTREJECTHISTORY 無 EQUIPMENTID 欄位，只有 EQUIPMENTNAME，故必須繞道 LOTWIPHISTORY 取得 CONTAINERID 再查報廢
- 改為明細列後，資料量可能顯著增加（原本是 aggregate），需注意查詢效能
- 前端 EquipmentRejectsTable.vue 的欄位定義需全部重寫

## Known Context

- 現行 equipment_rejects.sql：GROUP BY EQUIPMENTNAME, LOSSREASONNAME，輸出 TOTAL_REJECT_QTY / TOTAL_DEFECT_QTY / AFFECTED_LOT_COUNT
- 現行 get_equipment_rejects() 傳入 equipment_names（List[str]），因為 LOTREJECTHISTORY 只有 EQUIPMENTNAME
- 改版後應改傳 equipment_ids，透過 LOTWIPHISTORY CTE 找 CONTAINERID，再查 LOTREJECTHISTORY
- 同樣的 API endpoint 被 EquipmentView（設備追蹤生產批次）和 LotEquipmentView（批次追蹤生產設備）兩個頁籤共用（equipment-period API, query_type='rejects'）
- LotRejectTable.vue 的欄位可參考作為新明細列欄位的設計基礎

## Open Questions

（無）

## Requested Delivery Date / Priority

正常優先，無截止日
