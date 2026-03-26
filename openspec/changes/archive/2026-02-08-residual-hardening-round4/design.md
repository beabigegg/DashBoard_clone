## Context

round-3 後主流程已穩定，但仍有 3 類技術債：
- Resource 快取在同一 process 內同時保存 DataFrame 與完整 records 複本，導致記憶體放大。
- Resource 與 Realtime Equipment 的 Oracle 查詢存在跨服務重複字串，日後修改容易偏移。
- 部分服務邊界型別註記與魔術數字未系統化，維護成本偏高。

約束條件：
- `resource` / `wip` 維持全表快取策略，不改資料來源與刷新頻率。
- 對外 API 欄位與前端行為不變。
- 保持單一 port 架構與既有運維契約。

## Goals / Non-Goals

**Goals:**
- 降低 Resource 快取在 process 內的重複資料表示，保留查詢輸出相容性。
- 讓跨服務 Oracle 查詢片段由單一來源維護。
- 讓關鍵 service/cache 模組具備一致的型別註記與具名常數。

**Non-Goals:**
- 不改動資料庫 schema 或 SQL 查詢結果欄位。
- 不重寫整體 cache 架構（Redis + process cache 維持）。
- 不引入新基礎設施或外部依賴。

## Decisions

1. Resource derived index 改為「row-position index」而非保存完整 records 複本
- 現況：index 中保留 `records` 與多組 bucket records，與 DataFrame 內容重複。
- 決策：index 只保留 row positions（整數索引）與必要 metadata；需要輸出 dict 時由 DataFrame 按需轉換。
- 取捨：單次輸出會增加少量轉換成本，但可顯著降低常駐記憶體重複。

2. 建立共用 Oracle 查詢常數模組
- 現況：`resource_cache.py`、`realtime_equipment_cache.py` 各自維護 base SQL。
- 決策：抽出 `services/sql_fragments.py`（或等效模組）管理共用 query 文本與 table/view 名稱。
- 取捨：增加一層間接引用，但查詢語意一致性與變更可控性更高。

3. 型別與常數治理採「先核心邊界，後擴散」
- 現況：部分函式已使用 `Optional` / PEP604 混搭，且魔術數字散落於 cache/service。
- 決策：先統一這輪觸及檔案中的型別風格與高頻常數（TTL、size、window、limits）。
- 取捨：不追求一次全專案清零，以避免大範圍 noise；先建立可持續擴展基線。

## Risks / Trade-offs

- [Risk] row-position index 與 DataFrame 版本不同步 → Mitigation：每次 cache invalidate 時同步重建 index，並保留版本檢查。
- [Risk] 惰性轉換導致查詢端 latency 波動 → Mitigation：保留 process cache，並對高頻路徑做小批量輸出優化。
- [Risk] SQL 共用常數抽離造成引用錯誤 → Mitigation：補齊單元測試，驗證 query 文本與既有欄位契約一致。
- [Risk] 型別/常數清理引發行為改變 → Mitigation：僅做等價重構，保留原值並用回歸測試覆蓋。

## Migration Plan

1. 先重構 Resource index 表示，確保 API 輸出不變。
2. 抽離 SQL 共用片段並替換兩個快取服務引用。
3. 清理該範圍型別與常數，補測試。
4. 更新 README / README.mdj 與 OpenSpec tasks，跑 backend/fronted 目標測試集。

Rollback：
- 若出現相容性問題，可回退至原 index records 表示與舊 SQL 內嵌寫法（單檔回退即可）。

## Open Questions

- 是否要在下一輪把相同治理擴展到 `wip_service.py` 的其餘常數與型別（本輪先限定 residual 範圍）。
