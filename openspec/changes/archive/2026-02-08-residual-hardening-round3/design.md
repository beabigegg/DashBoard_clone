## Context

目前系統已完成 Vite 單一 port 架構與主要 P0/P1/P2 硬化，但殘餘風險集中在「快取慢路徑鎖競爭 + health 熱點查詢 + API 邊界治理」。這些問題多屬中高流量下才明顯，若不在此階段收斂，後續排障成本會高。

## Goals / Non-Goals

**Goals:**
- 在不改變頁面操作語意與單一 port 架構前提下，完成殘餘穩定性與安全性修補。
- 讓 cache/health 路徑在高併發下更可預期，並降低 log 資安風險。
- 透過測試覆蓋確保修補不造成功能回歸。

**Non-Goals:**
- 不重寫主要查詢流程或移除 `resource/wip` 全表快取策略。
- 不引入重量級 distributed rate-limit 基礎設施。
- 不改動前端 drill-down 與報表功能語意。

## Decisions

1. **Cache 發布一致性優先於局部最佳化**
- 使用 staging key + 原子 rename/pipeline 發布資料與 metadata，確保 publish 失敗不影響舊資料可讀性。

2. **解析移至鎖外，鎖內僅做快取一致性檢查/寫入**
- WIP process cache 慢路徑改為鎖外 parse，再鎖內 double-check+commit，降低持鎖時間。

3. **Process cache 策略一致化**
- realtime equipment cache 補齊 max_size + LRU，與既有 WIP/Resource 一致。

4. **Health 內部短快取僅在非測試環境啟用**
- TTL=5 秒，降低高頻 probe 對 DB/Redis 的重複壓力；測試模式維持即時計算避免互相污染。

5. **高成本 API 採輕量 in-memory 速率限制**
- 以 IP+route window 限流，參數化可調，不引入新外部依賴。

## Risks / Trade-offs

- [Risk] 快取發布改造引入 key 切換邏輯複雜度 → Mitigation: 補上 publish 失敗/成功測試。
- [Risk] health 快取造成短時間觀測延遲 → Mitigation: TTL 限制 5 秒，並於 testing 禁用。
- [Risk] in-memory rate limit 在多 worker 下非全域一致 → Mitigation: 先作保護閥，後續可升級 Redis-based limiter。

## Migration Plan

1. 先完成 cache 與 health 核心修補（不影響 API contract）。
2. 再導入 API 邊界/限流與共用工具抽離。
3. 補單元與整合測試，執行 benchmark smoke。
4. 更新 README 文件與環境變數說明。

## Open Questions

- 高成本 API 的預設限流門檻是否要按端點細分（WIP vs Resource）？
- 後續是否要升級為 Redis 分散式限流以覆蓋多 worker 全域一致性？
