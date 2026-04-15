## Context

MES Dashboard 各頁面使用不同層次的請求防護機制：
- 大多數頁面已使用 `useRequestGuard`（stale request ID）或 `useAutoRefresh`（AbortController Map）
- RQ Job 輪詢類頁面（`yield-alert-center`、`reject-history`）自行管理 `_jobAbortController`，但 `onUnmounted` 未呼叫 `.abort()`
- `production-history` 的 `handleQuery()` 無 loading guard，也無 stale check
- `query-tool` 的多標籤 composable 各自獨立，`onBeforeUnmount` 只清理 `popstate` listener

現有工具（皆已在 codebase 中）：
- `shared-composables/useRequestGuard.js` — `nextRequestId` / `isStaleRequest`
- `core/api.js` — `apiPost`/`apiGet` 皆支援 `signal` 參數

## Goals / Non-Goals

**Goals:**
- 元件卸載時，所有進行中的 RQ Job 輪詢必須被 `abort()`
- `production-history` 的查詢在 loading 期間不可重複觸發；回應亂序時舊結果被丟棄
- `query-tool` 標籤切換時，前一標籤的 pending 請求被清理（不更新 DOM）
- 新增 e2e 測試驗證以上三種場景

**Non-Goals:**
- 不修改後端 RQ enqueue 去重（評估後為低優先，前端 loading guard 已足夠防護）
- 不重構現有 composable 架構，只做最小侵入修改
- 不對所有頁面統一到同一種防護模式

## Decisions

### 決策 1：yield-alert-center / reject-history — 在 onUnmounted 加一行 abort

**選擇**：`_jobAbortController?.abort()` 加在 `onUnmounted` 的第一行。

**理由**：變更量最小（各一行），不改變現有的 abort 邏輯（`runQuery()` 開頭已有 abort + replace）。Optional chaining 確保 null-safe。

**替代方案**：將輪詢抽成 composable 統一管理 → 過度工程，不在此次範圍。

### 決策 2：production-history — loading guard + useRequestGuard

**選擇**：
1. `handleQuery()` 開頭加 `if (loading.value) return;`
2. 引入 `useRequestGuard`，在每次非同步回應前加 `if (isStaleRequest(requestId)) return;`

**理由**：與其他頁面（`hold-history`、`hold-detail`）一致的防護模式，開發者熟悉。loading guard 防止重複觸發，stale check 處理偶發的並發回應。

**替代方案**：AbortController 取消前次請求 → 功能等價，但 stale check 更簡單且符合現有慣例。

### 決策 3：query-tool — 讀取各 composable 後決定 cleanup 策略

`query-tool` 有 5+ 個 composable（`useLotResolve`、`useLotDetail`、`useReverseLineage`、`useLotEquipmentQuery` 等）。需先讀取每個 composable 的介面，確認是否暴露 `abort`/`reset`/`cancel` 方法，再決定：
- **Option A**：各 composable 有內部 abort → 在 `onBeforeUnmount` 呼叫
- **Option B**：composable 無 abort → 加入 `useRequestGuard` 的 `nextRequestId()` 使後續回應自動失效

實作時依實際狀況選擇。

### 決策 4：e2e 驗證策略

使用 Playwright 的 `page.on('request')` 計數特定 URL pattern 的請求數：
- 離頁場景：navigate away 後等待 3 秒，計數新增請求數應為 0
- 重複點擊場景：連點 5 次，同時 in-flight 請求應 ≤ 1

測試使用本地服務（`http://127.0.0.1:8080`），conda env `mes-dashboard`，指令：
```bash
./scripts/start_server.sh start
conda run -n mes-dashboard pytest tests/e2e/test_query_race_condition_e2e.py -v -s
```

## Risks / Trade-offs

- **[風險] query-tool composable 可能無 cleanup 介面** → Mitigation：若無，使用 flag 變數（`_isMounted`）讓回調在卸載後不更新 reactive state；此法不取消 HTTP 請求但可防止 UI 錯誤
- **[風險] e2e 測試時序敏感** → Mitigation：使用 `page.wait_for_timeout` 提供足夠緩衝，並設 retry

## Migration Plan

1. 實作前端修改（各頁面獨立，無相依）
2. 撰寫 e2e 測試
3. 啟動本地服務執行 e2e 迴歸 + 新測試
4. 確認通過後 commit

無 API 變更，無需 rollback 計劃。

## Open Questions

- `query-tool` 各 composable 是否暴露 cleanup/abort 介面？（實作時確認）
