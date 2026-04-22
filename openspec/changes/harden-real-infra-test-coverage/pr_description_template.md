# PR Description Template — harden-real-infra-test-coverage

> **用途**：本 change 底下每個 PR（以及後續 follow-up change 的同類 PR，例：Target A 補救）的描述**必附**下列七個欄位。
>
> **語意**：欄位本身是硬性要求；若某欄位在該 PR 不適用（例：純文件 PR 沒有 mutation evidence），寫 `N/A — <reason>`，不要省略整個欄位。
>
> **位置**：此檔與 change 一起 archive；repo 層級的 `.github/PULL_REQUEST_TEMPLATE.md` 刻意不動，避免把規則擴散到此 change 範圍以外的 PR。

---

## 1. Scope

- **本 PR 做了什麼**：一段話，動詞開頭。例：「加 weekly soak workflow + dispatch override」
- **勾到的 OpenSpec tasks**：列 task 編號（例：`3.7`、`3.9`、`6.1` 部分項）
- **刻意不碰**：若有相關 task 被拆到後續 PR，列出並說明為何分開（避免 review 誤以為遺漏）

## 2. Scenario 對照

- 列出本 PR 觸及的 spec Scenario（`specs/<capability>/spec.md` 內條目）
- 每條對應到測試檔：`<test_file>::<test_function>` 或 `<test_file>:<line>`
- 若該批純 infra（workflow / docs），改列「對應 task + 驗收條件」並說明為何無 Scenario 關聯

## 3. Verification

### Local
- 指令（完整、可直接貼）：`conda run -n mes-dashboard pytest <path> -v` 之類
- 結果：pass / fail / skipped 數 + 耗時
- Env 覆寫：若設了環境變數（例：`CIRCUIT_BREAKER_ENABLED=true`、`SOAK_INTERVAL_SECONDS=10`），逐一列出原因

### CI
- Workflow 名稱 + run id + conclusion
- URL：`https://github.com/<owner>/<repo>/actions/runs/<id>`
- 若是 `workflow_dispatch` smoke：標明 input 覆寫值（例：`duration_seconds=300`）
- 若刻意沒跑某個 workflow（例：`nightly-integration-real` 只在排程跑）：說明

## 4. Mutation evidence

> task 6.2 硬性要求。純文件或 infra-only PR 寫 `N/A — docs/infra only, no behaviour change`。

- **Mutation 位置**：`<file>:<line-range>` + 一句話說明改了什麼（例：「移除 `finally: conn.close()`」、「`state` property 每次 read 強制輪轉」）
- **對應失敗的 checker / test**：名字 + 斷言訊息一句話摘要（例：「`[circuit_breaker_transitions] observed 20 state transitions (threshold = 3)`」）
- **Fail artifact**：路徑（例：`artifacts/mutation-B/mutated-v3/soak-metrics-1776814608.json`）
- **Revert 指令**：`git restore --source=HEAD -- <file>`
  - **禁用** `git checkout -- <file>`（可能誤動其他未提交變更）
- **Revert-pass 證據**：artifact 路徑 + 簡短結論（例：「六條性質全 PASS、post-warmup transitions = 0」）

## 5. Artifacts & Workflow links

- CI artifact 下載連結（若有）
- 本地 artifact 相對路徑（從 repo root 起算）
- 若本 PR 依賴先前一次 workflow run（例：「合併前 nightly run `#<id>` 已 green」），列 run id + URL

## 6. Known limitations

- 本 PR 範圍內**無法驗到**的盲點（例：「CI runner 上無 Oracle → pool / duckdb / circuit_breaker checker 在 CI 為 trivial signal」）
- 已開但延後處理的 task（例：「3.8 Target A documented blind spot，另開 follow-up change」）
- 引用具體位置：tasks.md 的 task 編號 / 測試檔 docstring 段落 / 文件章節

## 7. Follow-ups

> 本批若發現 CODE_BUG，**必附** follow-up change 連結。無發現寫 `None`。

- Follow-up change 路徑：`openspec/changes/fix-<slug>/`（或新 issue / PR URL）
- 每條列出觸發原因：「哪個測試失敗」或「哪個 mutation check 暴露了什麼」
- 引用 `triage.md` 條目（若已登記）

---

## 快速檢查表（PR 送出前對自己跑一遍）

- [ ] 欄位 1–7 全部填過，不適用者明寫 `N/A — <reason>`
- [ ] 所有 artifact 路徑實際存在（`ls` 過）
- [ ] 所有外部連結（workflow run、follow-up change）點得開
- [ ] tasks.md 同步更新：本 PR 勾到的 task 都已加 `[x]` 或 `[~]` + 收斂說明
- [ ] Mutation 相關變更**已 revert**，`git status` 乾淨
- [ ] 若動到 API / CSS，`contract/api_inventory.md` 或 `contract/css_inventory.md` 同批更新
