## Context

現有 AI 查詢系統（`ai_query_service.py:589-742`）為 3-round Function Call pipeline：

```
Round1: LLM 從 55 個函式中選 1 個（build_round1_prompt）
Round2: LLM 為該函式填參數（build_round2_prompt）
Service dispatch: 呼叫對應 service function
Round3: LLM 摘要結果（build_round3_prompt）
```

每輪為獨立 LLM call（gpt-oss:120b, 16K context, OpenAI-compatible API），不帶歷史。DB 為 Oracle 19c DWH，22 張表/view（`docs/Oracle_Authorized_Objects.md`），帳號為 read-only（SELECT only）。SQL 執行透過 `core/database.py` 的 `read_sql_df()`（55s timeout + circuit breaker）。

**限制**：內部 LLM 無 token 費用。每輪獨立使用 16K context，不存在跨輪 token 共用問題。

## Goals / Non-Goals

**Goals:**
- 讓 AI 能回答任意 MES 資料查詢，不受預定義函式限制
- 注入 MES 領域知識（ID 格式、站別縮寫、資料源判斷邏輯）到 LLM prompt
- SQL 執行失敗時自動重試（回饋 Oracle 錯誤讓 LLM 修正）
- 前端透明化顯示 AI 生成的 SQL
- 保留 Function Call pipeline 作為 fallback

**Non-Goals:**
- 不做 SQL 安全閘門（DB 帳號已是 read-only）
- 不做 token 用量優化（內部 LLM 無費用）
- 不做對話歷史 / 多輪追問（維持現有 stateless 設計）
- 不移除現有 function registry 及相關檔案
- 不改動 API route 或 rate limiting

## Decisions

### D1: 3-Stage Pipeline 架構

```
使用者問題
    ↓
[Stage 1] LLM 分類問題領域 + 選擇相關表
    ↓
[Stage 2] 注入相關表 schema + few-shot SQL → LLM 生成 SQL
    ↓ ← 執行失敗時帶 Oracle 錯誤回饋 LLM 重試（最多 2 次）
[Execute] read_sql_df(sql, params)
    ↓
[Stage 3] LLM 摘要結果
    ↓
回傳 {answer, chart_data, sql_used, tool_trace}
```

**為什麼分 Stage 1 + Stage 2**：不是為了省 token（每輪有獨立 16K），而是為了精準度。一次送 22 張表 schema 會讓 LLM 選擇困難；先縮小到 2-4 張相關表，再深入注入欄位 + 範例，SQL 品質更高。

**替代方案**：單輪直接送全部 schema → LLM 容易選錯表、JOIN 錯誤，實測品質差。

### D2: Schema Context 來源 — SQL 模板反推

從 `data/table_schema_info.json`（22 張表完整欄位）+ `sql/**/*.sql`（89 個模板）交叉比對，只保留實際被使用的 10-20 個欄位/表。

**為什麼不直接用 `docs/MES_Database_Reference.md`**：該文件每張表 30-80 欄位，多數從未被查詢使用，會干擾 LLM 選擇。SQL 模板反推出的欄位才是真正有業務意義的。

**實作方式**：開發時執行 `scripts/extract_sql_schema.py` 掃描一次，結果硬編碼進 `ai_schema_context.py`。不是 runtime 動態掃描。

### D3: 領域知識注入位置 — Stage 1 System Prompt

將 MES 領域知識（ID 格式、站別縮寫、資料源判斷規則）放在 Stage 1 的 system prompt 中，而非分散在多處。

**包含內容**：
- ID 格式辨識：設備（GWBK-xxxx）、工單（GA/GC 開頭）、Lot ID（含連字號）
- 站別對照：DB=焊接_DB, WB=焊接_WB, MOLD=成型, TMTT=測試 等
- 資料源判斷：「現在/目前」→ WIP 即時表，「歷史/趨勢」→ 歷史表
- 日期預設：未指定時預設近 7 天

**Domain 表分配（涵蓋全部 22 個授權物件）**：
- `wip_realtime`：DW_MES_LOT_V, DW_MES_EQUIPMENTSTATUS_WIP_V
- `lot_history`：DW_MES_CONTAINER, DW_MES_LOTWIPHISTORY
- `reject`：DW_MES_LOTREJECTHISTORY, ERP_WIP_MOVETXN, ERP_WIP_MOVETXN_DETAIL, ERP_PJ_WIP_SCRAP_REASONS_EXCLUDE
- `hold`：DW_MES_HOLDRELEASEHISTORY
- `equipment`：DW_MES_RESOURCE, DW_MES_RESOURCESTATUS, DW_MES_RESOURCESTATUS_SHIFT, DW_MES_SPEC_WORKCENTER_V
- `material`：DW_MES_LOTMATERIALSHISTORY
- `job`：DW_MES_JOB, DW_MES_JOBTXNHISTORY, DW_MES_MAINTENANCE, DW_MES_PARTREQUESTORDER
- `genealogy`：DW_MES_HM_LOTMOVEOUT, DW_MES_PJ_COMBINEDASSYLOTS
- `yield`：DW_MES_LOTREJECTHISTORY, DW_MES_LOTWIPHISTORY（交叉計算良率）
- `wip_data`：DW_MES_LOTWIPDATAHISTORY, DW_MES_WIP

### D4: SQL 執行失敗重試

LLM 生成的 SQL 可能語法錯、欄位名錯。重試機制：

```
生成 SQL → 執行 → 成功 → 繼續
                → 失敗（ORA-xxxxx）
                    → 將錯誤回饋給 LLM（帶歷史：上次 SQL + 錯誤訊息）
                    → LLM 修正 SQL → 重新執行
                    → 最多重試 2 次（共 3 次機會）
                    → 全部失敗 → 回傳錯誤給使用者
```

這是唯一會帶對話歷史的情境（Stage 2 內部的重試 loop）。

### D5: Feature Flag 分流

```python
AI_MODE = os.getenv("AI_MODE", "text2sql")  # "function" | "text2sql"
```

`process_query()` 根據 flag 分流到 `process_query_text2sql()` 或 `process_query_function()`（原有邏輯改名）。

### D6: 前端 SQL 顯示 — 可折疊 details

在 `AiChatMessage.vue` 中新增可折疊的 `<details>` 區塊顯示 SQL 和執行步驟。單步查詢（Stage 2 一次成功）不顯示步驟區，只顯示 SQL。

## Risks / Trade-offs

**[Risk] LLM 生成的 SQL 品質不穩定** → 重試機制（D4）+ few-shot 範例引導 + Stage 1 縮小表範圍降低複雜度。上線初期用 `AI_MODE=function` 觀察，逐步切換。

**[Risk] 大表全表掃描** → Stage 2 prompt 明確規定「大表必須有日期或 ID 條件」+ 既有 `read_sql_df()` 55s timeout + circuit breaker 保護。

**[Risk] Schema context 過時** → `ai_schema_context.py` 為硬編碼，表結構變動時需手動更新。設計 `scripts/extract_sql_schema.py` 可快速重新掃描。

**[Trade-off] 維護兩套 pipeline** → Function Call 作為 fallback 增加維護成本，但提供安全回退路徑。計畫穩定 1-2 個月後評估移除。

**[Trade-off] 3 次 LLM call vs 現有 3 次** → 延遲相當（每次 2.5-4s），但 SQL 失敗重試最多加 2 輪，worst case ~5 次 LLM call（~15-20s）。可接受，因為失敗重試不常見。
