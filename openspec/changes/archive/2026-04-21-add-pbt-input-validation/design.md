## Context

專案目前的 fuzz 測試 [tests/routes/test_fuzz_routes.py](tests/routes/test_fuzz_routes.py) 採取「列舉式 payload」做法：每個 route 帶入一組預先準備好的惡意輸入。這種方式的優點是「可重現、CI 快」，缺點是覆蓋面取決於開發者「想得到」的輸入。

`core/request_validation.py` 是所有 routes 的入口防線（Pydantic-style 驗證 + URL state 解碼）。其輸入空間（query string、JSON body、headers）的笛卡兒積極大，列舉式 fuzz 必然漏掉組合情境。Property-based testing (PBT) 透過策略 (`hypothesis.strategies`) 自動生成，能系統性地探索邊界，並在發現失敗時自動 shrink 至最小可重現案例。

本次變更不修改 production 程式碼；目標是把「我們相信 validation 對任意輸入都安全」這個不變式，從「人工審視 + 列舉樣本」升級為「機器系統性檢驗」。

## Goals / Non-Goals

**Goals:**
- 為 `core/request_validation.py` 與 URL state codec 建立可重現的 PBT 套件
- 為查詢過濾器的合併與正規化建立屬性測試（normalize 後語意應為輸入子集）
- 為分頁/排序參數建立屬性測試（任意整數輸入應安全降級至預設值）
- pytest 整合：以 `@pytest.mark.property` 標記、CI 中以獨立 step 執行
- 不阻塞既有測試流程：PBT 失敗時 shrink case 應寫入 artifact 供 debug

**Non-Goals:**
- 不對 service / DB 層做 PBT（DB-bound 邏輯邊際效益低、會放慢 CI）
- 不取代既有 [test_fuzz_routes.py](tests/routes/test_fuzz_routes.py)（保留作為已知攻擊樣本回歸）
- 不對前端 JS 做 PBT（JS 端有自己的測試體系，不在本變更範圍）
- 不導入 statefulRule / Bundle 等進階 hypothesis 功能（首版聚焦純函式 property）

## Decisions

### 1. 採用 hypothesis 而非 schemathesis / atheris
- **選擇 hypothesis**：成熟、Python 社群標準、支援 shrink、與 pytest 整合佳
- **不選 schemathesis**：依賴 OpenAPI spec，本專案無此 spec
- **不選 atheris (libFuzzer)**：偏向 binary-level fuzz、需要編譯 instrumentation、過度

### 2. 測試目錄獨立於 `tests/routes/`：放 `tests/property/`
- **理由**：PBT 執行時間較長、有 `--hypothesis-seed` 等專屬參數；獨立目錄方便 CI 以 `-m property` 隔離
- **替代方案考慮**：放 `tests/routes/property_*.py` → 與既有 fuzz 混雜，CI 過濾不便

### 3. CI 策略：每次 PR 跑 100 examples，nightly 跑 1000
- **理由**：PBT 樣本數越多越可能發現問題，但時間成本線性增加；分層執行兼顧 PR feedback 速度與漏網率
- **實作**：`@settings(max_examples=...)` + 環境變數 `HYPOTHESIS_PROFILE=ci|nightly` 切換 profile

### 4. 不變式 (invariants) 設計原則
對每個 PBT 目標明確列出三類屬性：
- **不應 raise**：對任意輸入，validation 不得拋出未預期例外（只能 raise 已宣告的 ValidationError 系列）
- **冪等性 / round-trip**：encode → decode 應還原原值；normalize 兩次結果相同
- **語意子集**：filter normalize 後查到的資料 ⊆ 輸入 filter 對應的資料（不會「擴大」結果集）

### 5. 失敗案例持久化：`.hypothesis/examples/` 入 git
- **理由**：hypothesis 的 example database 記錄發現過的失敗，下次跑會優先重試。入 git 讓 CI 與本地共享記憶
- **替代方案**：不入 git → 每次 CI 從零開始，失敗難以重現；採用本方案

## Risks / Trade-offs

- **PBT 慢於單元測試** → 用 marker 隔離；PR 跑短，nightly 跑長
- **hypothesis 學習曲線** → 在 `tests/property/README.md` 寫 30 行入門範例與 strategy 索引
- **Flaky 風險（shrink 對 timing-sensitive code 失效）** → 本變更只測純函式（validation / codec），無 timing 相依
- **example database 入 git 可能膨脹** → 設定 `.gitignore` 規則：只保留 fail samples、限制大小

## Migration Plan

1. 加 `hypothesis` 至 `environment.yml`（dev section）與 `requirements-dev.txt`
2. 建 `tests/property/` 目錄、`conftest.py` 註冊 hypothesis profile
3. 為每個目標模組逐一建檔（validation → URL state → filters → pagination）
4. 配置 `pytest.ini` 註冊 `property` marker
5. CI workflow 加 `pytest -m property` step（失敗不阻塞 PR 首版，stabilize 後改為阻塞）
6. 寫 `tests/property/README.md` 說明執行方式與新增測試慣例

**Rollback**：移除 `tests/property/` 目錄、卸載 `hypothesis`、移除 CI step。無 production 影響。

## Open Questions

- CI runner 是否支援 nightly schedule？若無，先以 PR 跑 200 examples 折衷
- 是否需要把 hypothesis example database 改放 S3/共用 cache？首版先用 git，觀察體積成長
