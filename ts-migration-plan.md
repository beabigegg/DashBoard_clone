# TypeScript 遷移計畫

## 策略摘要

採用**由內向外的分層遷移**，共用基礎層一次到位，feature app 逐一遷移、互不阻塞。
每個 Phase 對應一個獨立的 `/cdd-new` 提案。

### 邊界定義（永久有效）

| 區域 | 語言 | 理由 |
|---|---|---|
| `core/` | **TS**（一次到位） | 所有功能的 API 呼叫與型別契約來源 |
| `shared-composables/` | **TS**（一次到位） | 跨 App 共用，改動影響全局 |
| `shared-ui/` | **TS**（一次到位） | 22 個元件被所有功能依賴 |
| `admin-shared/` `resource-shared/` `wip-shared/` | **TS** | 次級共用層，各自影響 2–3 個 App |
| 各 feature App 目錄 | **TS**（逐步，依優先序） | 各自獨立，一次一個不影響其他 |
| `tables/` `workers/` `styles/` `assets/` | **保留 JS** | 靜態資源或無型別需求 |

### 何謂「真的遷完」

- 該目錄下不存在 `.js` 檔（`index.js` 除外若只做 re-export）
- `tsconfig.json` 的 `include` 涵蓋該目錄且 `strict: true` 通過
- 無 `@ts-ignore` / `any` 的濫用（每個 `any` 必須有 `// TODO:` 說明）

---

## Phase 0 — 工具鏈基礎設定

**CDD 提案：** `/cdd-new add TypeScript toolchain: tsconfig and vite config`

**目標：** 建立 TS 編譯環境，不改任何業務代碼。

**工作項目：**
- 安裝 `typescript` `vue-tsc` `@types/node`
- 新增 `tsconfig.json`（`strict: true`、`allowJs: false`、暫時只 include `core/`）
- `vite.config.js` → `vite.config.ts`（僅改副檔名）
- `package.json` 新增 `type-check` script：`vue-tsc --noEmit`
- CI 加入 `npm run type-check` gate

**估算：** 2–4 h

**成功條件：** `npm run type-check` 可執行，暫時沒有任何 `.ts` 檔所以 0 error。

---

## Phase 1a — `core/` 遷移

**CDD 提案：** `/cdd-new migrate core/ utilities and API layer to TypeScript`

**目標：** 建立 API response interface，讓所有消費端都能拿到型別推導。

**重點說明：**
`endpoint-schemas.js` 已有 runtime 形狀定義（hold-overview、reject-history 等），
直接轉為 TypeScript interface，同時保留 `schema-guard.js` 的 runtime 驗證（兩者互補）。

**涉及檔案（21 個）：**

```
core/api.js                      → api.ts          （ApiResponse<T> 泛型）
core/endpoint-schemas.js         → endpoint-schemas.ts  （runtime schema → TS interface 雙軌）
core/field-contracts.js          → field-contracts.ts
core/schema-guard.js             → schema-guard.ts
core/unwrap-api-result.js        → unwrap-api-result.ts
core/dev-warnings.js             → dev-warnings.ts
core/datetime.js                 → datetime.ts
core/compute.js                  → compute.ts
core/duckdb-client.js            → duckdb-client.ts
core/duckdb-activation-policy.js → duckdb-activation-policy.ts
core/pending-jobs-registry.js    → pending-jobs-registry.ts
core/post-export.js              → post-export.ts
core/shell-navigation.js         → shell-navigation.ts
core/app-version-check.js        → app-version-check.ts
core/autocomplete.js             → autocomplete.ts
core/risk-score.js               → risk-score.ts
core/table-tree.js               → table-tree.ts
core/reject-history-filters.js   → reject-history-filters.ts
core/resource-history-filters.js → resource-history-filters.ts
core/wip-derive.js               → wip-derive.ts
core/wip-navigation-state.js     → wip-navigation-state.ts
```

**估算：** 20–35 h（`api.ts` 的泛型設計是最重要的一步，決定後續品質）

**成功條件：** `tsconfig.json` include `core/`，`vue-tsc --noEmit` 0 error。

---

## Phase 1b — `shared-composables/` 遷移

**CDD 提案：** `/cdd-new migrate shared-composables/ to TypeScript`

**目標：** 為所有 feature app 的 composable 呼叫建立型別契約。

**重點說明：**
`useFilterOrchestrator` 的 config 物件需要泛型設計（`fields` key 是動態的），
建議使用 `Record<string, FieldDef>` + discriminated union for trigger type，
避免過度複雜的 mapped type。

**涉及檔案（13 個）：**

```
shared-composables/useFilterOrchestrator.js  → .ts  （最複雜，優先處理）
shared-composables/useAsyncJobPolling.js     → .ts  （已有 JSDoc，轉換容易）
shared-composables/useTraceProgress.js       → .ts
shared-composables/useRequestGuard.js        → .ts
shared-composables/useUrlSync.js             → .ts
shared-composables/useSortableTable.js       → .ts
shared-composables/usePaginationState.js     → .ts
shared-composables/useQueryState.js          → .ts
shared-composables/useAutoRefresh.js         → .ts
shared-composables/useAutocomplete.js        → .ts
shared-composables/useAiChat.js              → .ts
shared-composables/TraceProgressBar.vue      → lang="ts"
shared-composables/index.js                  → index.ts
```

**估算：** 15–25 h

**成功條件：** `tsconfig.json` include `shared-composables/`，0 error。

---

## Phase 1c — `shared-ui/` 遷移

**CDD 提案：** `/cdd-new migrate shared-ui/ components to TypeScript`

**目標：** 讓 22 個共用元件的 props / emits 有靜態型別，IDE 消費端自動推導。

**重點說明：**
Vue 3.5 的 `defineProps<T>()` 泛型語法讓 props 型別定義比 runtime validator 更簡潔，
遷移時同步移除舊的 `type: Object` 定義，改用 interface。

**涉及檔案：** `shared-ui/components/` 下 22 個 `.vue` 全部加 `lang="ts"`，
`shared-ui/index.js` → `index.ts`。

**估算：** 12–20 h

**成功條件：** `tsconfig.json` include `shared-ui/`，0 error。

---

## Phase 2 — 次級共用層遷移

**CDD 提案（3 個，可平行執行）：**

```
/cdd-new migrate admin-shared/ to TypeScript
/cdd-new migrate resource-shared/ to TypeScript
/cdd-new migrate wip-shared/ to TypeScript
```

**依賴：** 須在 Phase 1a–1c 全部完成後執行（因為這些目錄 import 自 core/ 和 shared-ui/）。

**估算：** 各 5–10 h

---

## Phase 3 — Feature App 逐一遷移

每個 App 一個 CDD 提案，完成一個算一個，未完成的不影響其他 App。

**提案命名格式：** `/cdd-new migrate <app-name>/ feature app to TypeScript`

### 優先序（依業務複雜度與 bug 風險排序）

#### 高優先（DuckDB + 複雜非同步邏輯）

| 順序 | App | 主要複雜點 | 估算 |
|---|---|---|---|
| 1 | `reject-history/` | App.vue 1370 行、DuckDB composable、Pareto 多維度篩選 | 20–30 h |
| 2 | `hold-history/` | DuckDB composable、Future Hold 累計邏輯 | 15–25 h |
| 3 | `resource-history/` | OEE 計算、多資料源合併 | 15–20 h |
| 4 | `job-query/` | main.js 603 行、非同步 job polling | 12–18 h |

#### 中優先（標準報表但業務邏輯複雜）

| 順序 | App | 估算 |
|---|---|---|
| 5 | `portal-shell/` | 路由守衛、權限控制、導覽狀態 | 12–18 h |
| 6 | `wip-overview/` | WIP 衍生計算（wip-derive） | 8–12 h |
| 7 | `wip-detail/` | | 8–12 h |
| 8 | `hold-overview/` | | 6–10 h |
| 9 | `hold-detail/` | | 6–10 h |
| 10 | `material-trace/` | 追溯鏈結結構複雜 | 10–15 h |

#### 一般優先（相對獨立）

| 順序 | App | 估算 |
|---|---|---|
| 11 | `admin-dashboard/` | | 6–10 h |
| 12 | `admin-performance/` | | 6–10 h |
| 13 | `admin-user-usage-kpi/` | | 5–8 h |
| 14 | `anomaly-overview/` | | 5–8 h |
| 15 | `mid-section-defect/` | | 5–8 h |
| 16 | `production-history/` | | 6–10 h |
| 17 | `qc-gate/` | | 5–8 h |
| 18 | `query-tool/` | | 6–10 h |
| 19 | `resource-status/` | | 5–8 h |
| 20 | `yield-alert-center/` | | 5–8 h |
| 21 | `portal/` | | 3–5 h |

---

## 總工時估算

| Phase | 估算 |
|---|---|
| Phase 0（工具鏈） | 2–4 h |
| Phase 1a（core/） | 20–35 h |
| Phase 1b（shared-composables/） | 15–25 h |
| Phase 1c（shared-ui/） | 12–20 h |
| Phase 2（次級共用層） | 15–30 h |
| Phase 3（21 個 feature app） | 150–260 h |
| **合計** | **214–374 h** |

---

## 執行注意事項

1. **Phase 0 → Phase 1a → 1b → 1c 必須依序完成**，因為每層都依賴前一層的型別。
2. **Phase 2 與 Phase 3 可交錯**，只要 Phase 2 的某個共用層完成，對應的 feature app 就可以開始。
3. **`endpoint-schemas.js` 是轉換的起點**：已有 runtime 形狀，直接提升為 TS interface 並加上 `export type`，schema-guard 的 runtime 驗證繼續保留（型別 + 執行期雙重保護）。
4. **每個 App 遷移時，先定義 API response interface，再遷移 composable，最後遷移 components**（由內向外）。
5. **`any` 政策**：暫時性的 `any` 必須標註 `// TODO: type <具體說明>`，禁止靜默使用。
