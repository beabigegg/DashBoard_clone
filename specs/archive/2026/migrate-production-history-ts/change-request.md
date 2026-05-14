# Change Request

## Original Request

將 `frontend/src/production-history/` 從 JavaScript 完整遷移到 TypeScript（Phase 3 per-app migration）。

範圍：
- `main.js` → `main.ts`
- `App.vue` 改 `lang="ts"`
- `composables/useProductionHistory.js` → `useProductionHistory.ts`
- `components/ProductionMatrix.vue` 與 `ProductionDetailTable.vue` 改 `lang="ts"`

**零行為變化**：不動 backend、不動 API contract、不動 cache、不動 SQL、不動 spool schema。

需遵循 CLAUDE.md 中既有的 TS Migration Rules：
- echarts callback callback parameters 加 `// TODO: type echarts callback` 註解
- index.html 保持 `./main.js` 不動（Vite 會自動 resolve）
- Python parity/safety tests 路徑審查（`tests/test_*_parity.py`、`test_*_safety.py`）
- Vitest `require()` 改 static `import`
- 對未遷移的 .js 來源使用 declared-interface + `@ts-expect-error` + cast pattern

## Business / User Goal

技術債清理：消除 production-history 模組混用 JS/TS 的狀態，提升型別覆蓋率與 IDE 補全/refactor 安全性。

## Non-goals

- 不修改任何業務邏輯
- 不調整 detail-table 計算邏輯（GROUP BY、MIN/MAX/SUM 等都保持原樣 — 那是 Change 2 的範圍）
- 不調整 filter 架構（一階/二階保持原樣 — 那是 Change 3 的範圍）
- 不調整 backend Python 程式碼（除非 parity/safety test 路徑必須改 .js → .ts）

## Constraints

- 必須使用 conda env `mes-dashboard`
- `npm run type-check`、`npm run build`、`npm run test`、`pytest` 全部必須通過
- 不可破壞 Python parity/safety tests（必須審 `tests/test_frontend_*_parity.py`、`test_*_safety.py` 是否有寫死 `.js` 路徑）

## Known Context

- Production-history 採用 Oracle → spool (Parquet) → DuckDB 三段架構
- 使用 echarts（matrix 沒有 chart，但需留意）— 經查 production-history 沒有用 echarts
- App.vue 使用 `useProductionHistory` composable 與 `useRequestGuard`（shared）；後者已是 TS
- Components 使用 `MultiSelect`, `ErrorBanner`, `LoadingOverlay`, `PageHeader`（shared-ui，已是 TS）

## Open Questions

無 — TS Migration Rules 已涵蓋所有已知 edge cases。

## Requested Delivery Date / Priority

優先：高（為 Change 2/3 解鎖）
