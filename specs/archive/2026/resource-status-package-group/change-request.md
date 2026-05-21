# Change Request

## Original Request

設備及時概況（/portal-shell/resource）頁面，當中的 filter / 矩陣 / 設備清單卡片中，需要加入「設備設定的 package」資訊。
資料來源是結合目前使用的資料（DW_MES_EQUIPMENTSTATUS_WIP_V）表中的 RESOURCEID 欄位，查找 DW_MES_RESOURCE 表中的 PACKAGEGROUPID，然後再去查找 DW_MES_RESOURCE_PACKAGEGROUP 中的 PACKAGEGROUPNAME 回傳設定的 PACKAGE 資訊。

補充說明：
- lookup dict（DW_MES_RESOURCE_PACKAGEGROUP，46 筆）是活資料，建議每週更新一次（TTL = 7 天）。
- PACKAGEGROUPID 已在 resource_cache SELECT * 快取中，只需補 PACKAGEGROUPNAME 反查 dict。
- EquipmentCard 顯示方式：與 workcenter / family 並列文字行（NULL 時隱藏）。
- MatrixSection：加入 Package 作為可展開維度。
- FilterBar：新增 Package Group MultiSelect 篩選器。

## Business / User Goal

讓工程師在及時概況頁面直接看到每台設備所屬的封裝規格（Package Group），無需另開設備主檔查詢，加速異常排查與排程決策。

## Non-goals

- 不修改 DW_MES_RESOURCE_PACKAGEGROUP 的內容或維護介面
- 不在其他報表頁面（resource-history、dashboard 等）同步加入 package 欄位
- 不新增 package 相關的 KPI 計算（OU%、AVAIL% 不納入 package 維度）

## Constraints

- lookup dict TTL = 7 天（每週刷新），獨立於 DW_MES_RESOURCE 的 24h 週期
- DW_MES_RESOURCE_PACKAGEGROUP 僅 46 筆，可全量放入 in-process dict，不需要額外 Redis key
- PACKAGEGROUPID 為 CHAR 型別，join key 比對需型別一致
- 91% 設備 PACKAGEGROUPID 為 NULL，前端顯示需正確處理空值

## Known Context

- `resource_cache.py` 使用 SELECT * FROM DWH.DW_MES_RESOURCE，PACKAGEGROUPID 已隨全表快取載入
- `resource_service.py::get_merged_resource_status()` 是合併三層快取的核心函式（line 359）
- `query_resource_filter_options()` 負責提供前端篩選器選項（line 280）
- 前端入口：`frontend/src/resource-status/`；FilterBar、EquipmentCard、MatrixSection 各自獨立元件

## Open Questions

（無）

## Requested Delivery Date / Priority

Normal priority.
