# Change Request

## Original Request

Query-tool 分頁切換效能優化：目前 query-tool 頁面裡「批次追蹤生產設備」(`useLotEquipmentQuery.ts`) 跟「設備生產批次追蹤」(`useEquipmentQuery.ts`) 兩個 composable 的 `setActiveSubTab()`，每次切換子分頁（生產紀錄/維修紀錄/報廢紀錄）都會無條件重新對 Oracle 發查詢，即使該分頁先前已經查詢過且篩選條件（equipment_ids/container_ids/workcenter_groups/date range）完全沒變也一樣重查。這些查詢本身偏慢（觀測到 equipment_lots 查詢 17 秒起跳），部分還會走非同步 RQ job（排隊+輪詢延遲疊加），來回切換分頁的使用體驗因此變差。

Desired behavior change: `setActiveSubTab()` 在切換到一個「已經查過、且目前的篩選條件與上次查詢時相同」的子分頁時，應該直接沿用已快取的結果，不重新發查詢；只有在篩選條件真的改變（例如換了設備清單、批次清單、站點群組、日期範圍）或使用者明確要求重新整理時才重新查詢。程式碼裡已經有 `queried.lots`/`queried.jobs`/`queried.rejects` 這幾個 boolean flag，但目前完全沒被 `setActiveSubTab()`/`queryActiveSubTab()` 用來做判斷——需要補上這個判斷邏輯，並且要正確處理「篩選條件改變時要讓快取失效」的情況（否則會顯示過期資料）。

Success criterion: 使用者在同一組篩選條件下，來回切換生產紀錄/維修紀錄/報廢紀錄三個子分頁，每個分頁只在第一次切換進去時查詢一次 Oracle；重複切換回同一分頁不會觸發新的 HTTP 請求或 RQ job；但只要調整了設備/批次/站點群組/日期範圍任一篩選條件後重新查詢，所有分頁的快取都要正確失效並在下次切入時重新查詢，不能顯示舊資料。這個變更會影響 `frontend/src/query-tool/composables/useLotEquipmentQuery.ts` 跟 `frontend/src/query-tool/composables/useEquipmentQuery.ts` 兩個 composable（可能也牽涉 `frontend/src/query-tool/composables/useLotDetail.ts` 的類似 `setActiveSubTab` 模式，需一併檢查是否有相同問題）。純前端變更，不涉及後端/API/合約修改，風險等級低。

This was discovered as a follow-on observation while verifying the real-world fix for [[fix-equipment-lots-trim]] (the same query-tool page) — not a regression introduced by that change, but a pre-existing UX/performance issue across the page's sub-tab-switching pattern.

## Business / User Goal

## Non-goals

## Constraints

## Known Context

## Open Questions

## Requested Delivery Date / Priority
