## Context

Phase 3 完成後，所有歷史查詢域的 `apply_view()` 路徑已統一：DuckDB 為唯一 view 引擎，spool miss 或 runtime 失敗 → 回傳 `None` → route 回傳 410 `cache_expired`。

但目前 410 在不同域的「前端應對行為」是不同的，且未明確記錄在 spec 層：

| 域 | 主查詢觸發方式 | 410 後前端預期行為 |
|---|---|---|
| resource-history | 同步（直接回傳結果） | 重觸發 sync query |
| hold-history | 同步 | 重觸發 sync query |
| yield-alert | 同步 | 重觸發 sync query |
| production-history | 同步（DuckDB, 已達標） | 重觸發 sync query |
| reject-history | 非同步（RQ job, 回 202） | 發起 async job → polling |
| material-trace | 非同步 | 發起 async job → polling |
| MSD | 非同步 | 發起 async job → polling |

這個分類目前存在於實作中，但沒有任何 spec 正式記錄。Phase 4 的工作是補全這項 governance。

## Goals / Non-Goals

**Goals:**
- 建立 `query-response-semantic-contract` spec，正式定義 Type A / Type B 雙語意查詢模式
- 更新 5 個現有 spec 以明確記錄各域的查詢語意歸屬與 410 後的 client 行為契約
- 確保 `async-query-job-service` spec 明確說明其作為 Type B miss re-dispatch 入口的角色

**Non-Goals:**
- 後端 route 代碼變更（行為已正確，不需要改）
- 前端代碼變更（前端行為已符合預期）
- material-trace / MSD 的 spec 更新（目前這兩個域的 spec 較複雜，留待後續 phase 或獨立 change）
- Phase 5（退休 pandas primary query path）工作

## Decisions

### D1：不修改 route 行為，只補 spec 文件化

Phase 3 後的 route 行為已正確實現 Phase 4 的語意目標：
- Type A：410 → 前端重觸發 sync query（resource/hold/yield-alert 路由已實作）
- Type B：410 → 前端發起 async job（reject route 已有 POST /query → 202 端點）

**決定**：Phase 4 純 spec governance，不含 route 代碼修改。

替代方案考慮：讓 reject view 端點在 spool miss 時自動 dispatch async job（透明化）。
**拒絕原因**：dispatch 需要原始查詢參數（日期、過濾條件），這些參數儲存在 client 端，不在 view 端點的 request context 中。view 端點只接受 `query_id`，無法重建原始查詢——因此 auto-dispatch 在架構上不可行。

### D2：`query-response-semantic-contract` 為跨域 governance spec，不掛在任何單一域

此 spec 描述的是所有歷史查詢域共同遵循的模式，不屬於任何單一 service。放在 `openspec/specs/query-response-semantic-contract/spec.md`。

### D3：Type A 域（resource/hold/yield-alert）的 spec 更新只補語意標籤，不改現有 requirement

這三個 spec 在 Phase 3 已更新了 DuckDB sole engine 的要求。Phase 4 只補充：
- 明確標記此域為 Type A
- 加入「view miss → 410 → 前端 sync re-query」的完整端到端 scenario

### D4：`reject-history-api` spec 更新補充 Type B 端到端契約

補充：view miss → 410 → 前端 POST /query → 202 → polling → view 的完整 scenario，強調 apply_view 不自動 dispatch（職責分離）。

## Risks / Trade-offs

| 風險 | 說明 | 緩解 |
|---|---|---|
| spec 描述與前端實作落差 | 前端實際 410 處理邏輯未做 code review | Phase 4 tasks 包含前端 410 行為確認 task |
| material-trace / MSD 缺席 | 這兩個 Type B 域本次未更新 spec | 加入 Open Questions 標記，留待後續 |
| query-id 重建問題長期存在 | Type B miss re-dispatch 需前端提供原始參數 | 此為已知架構限制，D1 已記錄 |

## Open Questions

1. **material-trace / MSD**：這兩個 Type B 域的 view miss 行為是否與 reject 完全一致？需確認後決定是否補 spec（暫排除本 Phase 範圍）。
2. **前端 410 處理一致性**：各 Type A 頁面的前端 410 處理是否統一？是否有某個域在 410 後行為異常？（建議在 tasks 加一個確認 task）
