# Change Classification

## Change Types
- primary: feature-add (new EAP ALARM report page + new "EAP" navigation category), api-change (new endpoints), data-shape-change (new spool/parquet contract)
- secondary: ui-change, env-change (new RQ worker queue + spool namespace), ci-change (new worker deploy unit + playwright spec registration)

## Risk Level
- high

## Impact Radius
- cross-module

## Tier
- 1

## Architecture Review Required
- yes
- reason: New top-level navigation category ("EAP") plus a new RQ-async + DuckDB spool-read pipeline against two new Oracle tables (DWH.EAP_EVENT JOIN DWH.EAP_EVENT_DETAIL). Non-obvious design decisions: spool-key granularity, mandatory LAST_UPDATE_TIME index filter (anti-full-scan), fine-filter derivation boundary (no Oracle re-query), parquet schema + _SCHEMA_VERSION and rollback runbook, namespace registration in _ALLOWED_NAMESPACES, worker fork-safety. The reject-history spool pattern is the reference, but JOIN-with-DETAIL + AlarmCategory decode is a new shape requiring a recorded design decision.

## Required Artifacts
Always required: change-request.md, change-classification.md, implementation-plan.md, test-plan.md, ci-gates.md, tasks.yml, context-manifest.md

## Optional Artifacts (default: no — set yes only with explicit reason)
| artifact | create? | reason |
|---|---|---|
| current-behavior.md | no | Net-new page; no existing behavior to baseline |
| proposal.md | no | Scope confirmed in change-request; no product investigation needed |
| spec.md | no | Behavior decisions fit in design.md + implementation-plan.md |
| design.md | yes | Architecture Review Required = yes; records spool-key granularity, Oracle-index mandate, JOIN/decode data shape, parquet schema version + rollback |
| qa-report.md | no | Routine evidence goes to agent-log/qa-reviewer.yml |
| regression-report.md | no | Net-new page; existing behavior unchanged |
| visual-review-report.md | no | Visual evidence in agent-log/visual-reviewer.yml |
| monkey-test-report.md | no | Not required at Tier 1 for read-only report page |
| stress-soak-report.md | no | Spool load follows proven pattern; capture in agent-log if degradation observed |

## Required Contracts
- API: contracts/api/api-contract.md (new EAP endpoints: spool trigger/status, fine-filter options, Pareto/trend/detail views), contracts/api/api-inventory.md, contracts/api/openapi.json (regenerate)
- CSS/UI: contracts/css/css-contract.md (new .theme-eap-alarm scope), contracts/css/css-inventory.md (new authored CSS source)
- Env: contracts/env/env-contract.md (new EAP RQ worker queue / spool namespace / concurrency vars)
- Data shape: contracts/data/data-shape-contract.md (EAP spool parquet schema + AlarmCategory decode map + DETAIL parameter expansion shape)
- Business logic: contracts/business/business-rules.md (AlarmCategory decode table 0/1/2/3/4/5/6/7/64; mandatory LAST_UPDATE_TIME filter rule; spool-key composition rule)
- CI/CD: contracts/ci/ci-gate-contract.md (new worker deploy unit + playwright spec registration)

## Required Tests
- unit: backend spool-key hashing + AlarmCategory decode + Oracle SQL builder (LAST_UPDATE_TIME mandatory-filter guard); frontend filter composable (_lastCommitted re-sync) + DuckDB-derived fine-filter options
- contract: response-sample capture for every new EAP endpoint; schema coverage; openapi resolution
- integration: EAP RQ async spool job (Oracle JOIN → parquet write → namespace registration), mirroring tests/integration/test_reject_history_rq_async style
- E2E: tests/e2e/test_eap_alarm_e2e.py + frontend playwright spec (coarse-filter submit → spool → fine filters → Pareto/trend/detail render)
- visual: Pareto chart, trend line, summary cards, detail-table expand under .theme-eap-alarm
- data-boundary: malformed/empty alarm rows, unknown AlarmCategory code, null DETAIL parameters, large-text AlarmText fuzzy match
- resilience: Oracle failure / Redis failure during spool; spool-miss fallback; in-flight abort on unload
- fuzz/monkey: not required (read-only report page at Tier 1)
- stress: spool 385K-row build + DuckDB compute under concurrent users; evidence in agent-log
- soak: not required pre-merge (weekly soak lane if degradation observed)

## Required Agents
1. contract-reviewer
2. test-strategist
3. spec-architect (design.md required)
4. ci-cd-gatekeeper
5. implementation-planner
6. backend-engineer
7. frontend-engineer
8. e2e-resilience-engineer (data-boundary + resilience + E2E coverage)
9. ui-ux-reviewer
10. visual-reviewer
11. qa-reviewer

## Inferred Acceptance Criteria
- AC-1: 導覽新增頂層「EAP」類別，路由至 EAP ALARM 分析頁，與 WIP/Hold/良率等並列。
- AC-2: 提交粗粒度 Filter（日期範圍 + 設備類型多選 {GDBA,GCBA,GWBA,GWBK,GPRA,GTMH,GWMT,GDSD,GWAC,GPTA}）觸發 RQ async spool，以 date_range + sorted(eqp_type_set) hash 為 key；相同粗粒度查詢重用已有 parquet，不重複查 Oracle。
- AC-3: Oracle spool 查詢必須以 LAST_UPDATE_TIME 為必填範圍過濾（走索引），JOIN DWH.EAP_EVENT 與 DWH.EAP_EVENT_DETAIL，7 天/~385K 筆寫入 parquet（<20MB）。
- AC-4: Spool 完成後，細粒度 Filter 選項（AlarmText 模糊多選、AlarmCategory 解碼多選、Equipment ID 多選）全從 DuckDB 推導；改變細粒度 Filter 重算視圖，不重新 spool，不查 Oracle。
- AC-5: AlarmCategory 依固定對照表解碼顯示（0=非分類, 1=設備, 2=製程, 3=視覺, 4=機械, 5=電子, 6=通知/供料, 7=品質, 64=繼續錯誤）；未知 code 顯示安全 fallback，不崩潰。
- AC-6: 摘要卡片（總ALARM數、受影響機台數、受影響LOT數、最多ALARM機台）、Pareto 圖（依 AlarmText）、趨勢折線（每日/每小時依設備類型堆疊）、明細表，全在 DuckDB 計算並反映當前細粒度 Filter。
- AC-7: 明細表列可展開顯示 ALARM DETAIL 參數，資料來源為 spool 中已 JOIN 的 DETAIL 欄位，不發額外 Oracle 查詢。
- AC-8: 所有 EAP 功能 CSS 限制在 .theme-eap-alarm 範圍內，通過 npm run css:check（Rule 6，無未 scope 滲漏）。

## Tasks Not Applicable
- not-applicable: 3.5 (soak tests not pre-merge for this pattern)

## Clarifications or Assumptions
- LOT_ID 直接在 EAP_EVENT 表，不需額外 JOIN MES lot 資料表。
- 新增獨立 RQ worker 及 deploy unit（eap-alarm-worker），遵循現有 per-feature worker pattern。
- Modernization policy: page_status.json、asset_readiness_manifest.json、route_scope_matrix.json 須在同一 PR 更新（frontend-engineer 負責）。
- _ALLOWED_NAMESPACES 新增 eap-alarm namespace 及對應 parametrized test 須在同一 PR 完成。
- AlarmCategory decode table 及 LAST_UPDATE_TIME mandatory filter 規則歸入 business-rules.md。
