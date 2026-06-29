# Change Request

## Original Request

mid-section-defect 新增 Type 與 Package 篩選維度，複用 container_filter_cache 快取，後端 Python post-query 過濾，前端 FilterBar 新增兩個跨篩選 MultiSelect。

背景：production-history 已有 container_filter_cache（Redis, 24h TTL）儲存 (PJ_TYPE, PRODUCTLINENAME, PJ_BOP, PJ_FUNCTION) 全量 tuple 集合。mid-section-defect 的 station_detection.sql 輸出已包含 PJ_TYPE 與 PRODUCTLINENAME，但目前沒有對應的篩選入口。期望讓使用者在日期區間查詢時，額外以 Type（PJ_TYPE）與 Package（PRODUCTLINENAME）縮窄分析範圍；篩選選項支援跨篩選聯動（選 Type → Package 自動收窄）。

## Business / User Goal

工程師在分析制程中段缺陷時，目前只能以「日期 + 偵測站 + 不良原因」篩選。若能加入 Type / Package 維度，即可直接聚焦特定產品線的缺陷趨勢，減少人工翻閱的時間。

## Non-goals

- 不新增 PJ_BOP / PJ_FUNCTION 篩選（station_detection.sql 不輸出這兩欄）
- 不修改 Oracle SQL 查詢（過濾在 Python 層執行）
- 不建立獨立的 mid-section-defect 篩選快取；直接複用 container_filter_cache

## Constraints

- 篩選選項 API 必須透過 container_filter_cache.get_filter_options()，不額外打 Oracle
- 過濾邏輯在取出 detection DataFrame 之後執行，不影響現有 Redis 快取 key 結構
- 跨篩選聯動邏輯與 production-history useFirstTierFilters 行為一致

## Known Context

- container_filter_cache: src/mes_dashboard/services/container_filter_cache.py
- station_detection.sql: src/mes_dashboard/sql/mid_section_defect/station_detection.sql（已輸出 PJ_TYPE, PRODUCTLINENAME）
- FilterBar: frontend/src/mid-section-defect/components/FilterBar.vue
- 現有 filter-options endpoint: GET /api/production-history/filter-options

## Open Questions

（無）

## Requested Delivery Date / Priority

盡快
