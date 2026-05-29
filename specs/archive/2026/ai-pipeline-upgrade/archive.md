# Archive — ai-pipeline-upgrade

## Change Summary

升級 MES Dashboard AI 查詢 pipeline 的三項改動：(1) 將 function mode 的 R1（意圖選擇）和 R2（參數填入）合併為單次 combined LLM call，節省約 5 秒延遲；(2) 在 `_SESSION_STORE` 中加入跨問題對話歷史 `chat_history`（8 對 FIFO cap，注入 combined call 和 text2sql Stage 1），使 AI 能在同一 session 中參考前幾輪問答；(3) 在 `ai_functions.yaml` 新增三個可呼叫的 AI function（`production_history_query`、`resource_history_summary`、`qc_gate_status`，共計 41 個）。

## Final Behavior

- **Function mode**: `process_query_function()` 發出一次 combined LLM call（system prompt 含全部 41 個 function 名稱+描述），輸出 `{"function","params","explanation"}`。Null/malformed output → 現有 null-intent path（無 exception）。
- **Chat history**: `_SESSION_STORE[conversation_id]["chat_history"]` 儲存最近 N 輪對話；每次成功回答後 append（含空結果），exception path 不 append；`advance_query_state` 的 slot-filling pop 不再清除 chat_history（R3 bug 修正）。
- **Text2sql**: Stage 1 domain classification 注入 chat_history；Stage 2 SQL generation 不注入（設計決策 D2）。
- **New functions**: `production_history_query`（raw_params dispatch adapter）、`resource_history_summary`（kwargs dispatch）、`qc_gate_status`（無 params，normalize → stations list）。

## Final Contracts Updated

| 合約檔案 | 版本 | 變動 |
|---|---|---|
| `contracts/api/api-contract.md` | 1.11.0 → 1.12.0 | §10 相容性說明：combined-call 行為、chat_history session extension |
| `contracts/api/api-inventory.md` | 1.1.10 → 1.1.11 | ai_routes.py row 更新描述 |
| `contracts/business/business-rules.md` | 1.10.0 → 1.11.0 | 新增 AI-04 ~ AI-09（combined-prompt schema、malformed fallback、chat_history append/cap/eviction/injection policy、三個新 function 行為合約） |
| `contracts/data/data-shape-contract.md` | 1.10.0 → 1.11.0 | 新增 §2.9（session store shape + chat_history 欄位）、三個新 function param schema、normalize_chart_data 輸出形狀 |
| `contracts/CHANGELOG.md` | — | 補上所有版本條目 |

Evidence: `agent-log/contract-reviewer.yml`, `agent-log/backend-engineer.yml`

## Final Tests Added / Updated

28 個新測試（全部 Tier 0/1 pre-merge）：

**`tests/test_ai_query_understanding.py`** — `TestChatHistoryAppendOnSuccess`, `TestChatHistoryNoAppendOnFailure`, `TestChatHistoryAppendOnEmptyResult`, `TestChatHistoryCapEnforcement`, `TestChatHistoryCapExactBoundary`, `TestHistorySurvivesAdvanceQueryStatePop`

**`tests/test_ai_query_service.py`** — `TestCombinedCallOneCallOnly`, `TestCombinedCallOutputSchema`, `TestCombinedCallNullIntent`, `TestCombinedCallMalformedJson`, `TestCombinedCallPartialJson`, `TestHistoryInjectedIntoCombinedCall`, `TestProductionHistoryQueryDispatchAdapter`, `TestNormalizeChartDataNewFunctions`

**`tests/test_ai_function_registry.py`** — `TestCombinedPromptContainsAll41Functions`, `TestCombinedPromptTokenBudget`, `TestProductionHistoryQueryFunctionEntry`, `TestResourceHistorySummaryFunctionEntry`, `TestQcGateStatusFunctionEntry`, `TestQcGateStatusNoParams`, `TestProductionHistoryQueryParamSchema`, `TestResourceHistorySummaryParamSchema`, `TestYamlLoadingExtended`

Full suite: 4179 passed, 550 skipped. Evidence: `agent-log/backend-engineer.yml`

## Final CI/CD Gates

Tier 1 pre-merge（現有 CI 工作流程已覆蓋）：
1. `pytest tests/test_ai_query_service.py tests/test_ai_function_registry.py tests/test_ai_query_understanding.py`
2. `pytest tests/ --ignore=tests/integration_real`
3. `ruff check src/mes_dashboard/services/`
4. `cdd-kit validate`
5. `cdd-kit gate ai-pipeline-upgrade`

無新 CI workflow 檔案。Evidence: `ci-gates.md`

## Production Reality Findings

- **`production_history_query` 潛在延遲**：`query_production_history(raw_params)` 觸發完整 Oracle → spool → DuckDB pipeline，可能在 `AI_REQUEST_TIMEOUT`（60s）內超時。已記錄於 business-rules AI-09、design.md R2；設計決策為接受此風險（synchronous 呼叫），建議使用者在 YAML 描述中限制查詢範圍（7 天預設提示）。
- **API 不破壞相容**：公開 API surface（路由、回應 envelope 欄位）完全不變，`chat_history` 為純 server-side state。
- **QA minor finding**：`TestChatHistoryNoAppendOnFailure` 測試名稱與其實際驗證行為（回傳 copy 而非 reference）不符。已記錄為 non-blocking follow-up。

## Lessons Promoted to Standards

| Lesson | 目標 | 位置 | 證據 |
|---|---|---|---|
| L1 — `contracts/CHANGELOG.md` 是 validator 唯一掃描位置 | CLAUDE.md | `## CDD Kit Commands` 段末 | backend-engineer.yml; gate failure log |
| L2 — `raw_params` dispatch adapter 必須設 `dispatch: raw_params` | CLAUDE.md | `## AI Pipeline Architecture Notes`（新段） | design.md §D3; TestProductionHistoryQueryDispatchAdapter |
| L3 — `advance_query_state` pop 會清除整個 session dict | CLAUDE.md | `## AI Pipeline Architecture Notes`（新段） | ai_query_understanding.py:258-264; TestHistorySurvivesAdvanceQueryStatePop |

L4（combined-prompt 設計）和 L5（CHANGELOG 格式）不推廣：L4 是 model/scale 特定的架構取捨（已記錄於 design.md），L5 與 L1 重複。

## Follow-up Work

- `TestChatHistoryNoAppendOnFailure` 可重命名並補充 exception-path 直接斷言（non-blocking，QA reviewer 建議）
- `production_history_query` 未來可考慮 async/background job 模式以避免同步延遲
- `resource_history_summary` 的 `families`/`resource_ids` 等技術性參數若有 NL 使用場景可再開放

## Cold Data Warning

This archive is historical evidence. Current requirements live in `contracts/` and active project guidance (`CLAUDE.md`).
