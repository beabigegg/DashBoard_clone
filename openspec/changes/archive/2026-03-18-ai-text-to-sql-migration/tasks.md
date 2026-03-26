## 1. Schema Context 準備

- [x] 1.1 建立 `scripts/extract_sql_schema.py`：掃描 `sql/**/*.sql` 提取每張表被使用的欄位 + 出現次數，交叉比對 `data/table_schema_info.json` 輸出精簡 schema
- [x] 1.2 執行腳本，整理產出結果
- [x] 1.3 建立 `services/ai_schema_context.py`：硬編碼 `TABLE_DOMAINS`（10 個領域分組）、`TABLE_SCHEMAS`（每表 10-20 個常用欄位 + 型別 + 中文註解）、`SQL_EXAMPLES`（每 domain 2-3 個 few-shot 範例）
- [x] 1.4 撰寫 `tests/test_ai_schema_context.py`：驗證所有 22 張授權表都被涵蓋、schema 欄位在 `table_schema_info.json` 中存在、SQL 範例為 SELECT + 含 FETCH FIRST

## 2. Prompt Builders

- [x] 2.1 在 `services/ai_function_registry.py` 新增 `build_stage1_prompt()`：注入 MES 領域知識（ID 格式、站別縮寫對照、資料源判斷規則、日期預設），列出所有 domain + description
- [x] 2.2 在 `services/ai_function_registry.py` 新增 `build_stage2_prompt(domains)`：根據 domains 從 `ai_schema_context` 組裝對應表 schema + SQL 範例 + 生成規則
- [x] 2.3 撰寫 prompt builder 單元測試：驗證 Stage 1 prompt 包含所有 domain 名稱、Stage 2 prompt 根據不同 domain 注入正確的表 schema

## 3. Text-to-SQL Pipeline 核心

- [x] 3.1 在 `services/ai_query_service.py` 新增 `_extract_oracle_error(exc)` helper：從 exception 提取 ORA-xxxxx 錯誤碼 + 訊息
- [x] 3.2 確認既有 `_summarize_dataframe(df, max_chars)` helper 可重用（已存在於 `ai_query_service.py:607`），必要時調整參數
- [x] 3.3 在 `services/ai_query_service.py` 新增 `process_query_text2sql(question)`：實作 Stage 1（分類）→ Stage 2（SQL 生成 + 重試 loop）→ Execute → Stage 3（摘要）完整流程
- [x] 3.4 新增 `AI_MODE` 環境變數支援，修改 `process_query()` 為分流函式，原有邏輯改名為 `process_query_function()`

## 4. Pipeline 測試

- [x] 4.1 撰寫 `test_text2sql_happy_path`：mock LLM 生成合法 SQL → mock `read_sql_df` 回傳 DataFrame → 驗證完整回傳格式
- [x] 4.2 撰寫 `test_text2sql_sql_error_retry_success`：第一次 SQL 失敗 → LLM 修正 → 第二次成功
- [x] 4.3 撰寫 `test_text2sql_all_retries_fail`：3 次全失敗 → 回傳錯誤訊息
- [x] 4.4 撰寫 `test_text2sql_empty_result`：SQL 成功但零行 → 不呼叫 Stage 3
- [x] 4.5 撰寫 `test_text2sql_no_domains`：Stage 1 回傳空 domains → 回傳 thought 作為 answer
- [x] 4.6 撰寫 `test_feature_flag_function_mode`：`AI_MODE=function` 時走舊 pipeline
- [x] 4.7 撰寫 `test_feature_flag_text2sql_mode`：`AI_MODE=text2sql` 時走新 pipeline
- [x] 4.8 撰寫 `test_text2sql_timeout_error`：SQL 執行 timeout → 直接回傳錯誤，不進入重試迴圈（timeout 無法靠修正 SQL 解決）

## 5. 前端 SQL 顯示

- [x] 5.1 修改 `frontend/src/shared-composables/useAiChat.js`：解析 `sql_used` 和 `tool_trace`，附加到 message 物件
- [x] 5.2 修改 `frontend/src/shared-ui/components/AiChatMessage.vue`：新增可折疊 SQL `<details>` 區塊（`sqlUsed` 非 null 時顯示）。注意：樣式須使用 Tailwind utility classes，不新增 feature CSS 檔案（CSS contract Rule 2.2）
- [x] 5.3 修改 `AiChatMessage.vue`：新增可折疊執行步驟 `<details>` 區塊（`toolTrace.length > 1` 時顯示）

## 6. 契約更新與驗證

- [x] 6.1 更新 `contract/api_inventory.md`：AI route 描述加入 `sql_used` 和 `tool_trace` 新欄位
- [x] 6.2 執行完整測試套件 `pytest tests/test_ai_function_registry.py tests/test_ai_query_service.py tests/test_ai_schema_context.py -v`
- [x] 6.3 啟動 server，用 8 個失敗案例手動測試 text2sql 模式驗證改善效果
