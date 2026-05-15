# Current Behavior (pre-fix)

## Symptom

Production History 頁面的 4 個一階 filter（type / package / bop / function）宣稱為「多選 + cross-filter」，但實際上：使用者在任一 dropdown 內勾選一個 item，下一個瞬間其他 3 個 filter 的可選範圍就被 cross-filter 收斂掉；下一次勾選又再次觸發收斂，導致無法在「同一次互動」內完成多選。

## Code path

### 1. 4 個 MultiSelect 共用同一個觸發點

[frontend/src/production-history/App.vue:320-364](frontend/src/production-history/App.vue#L320-L364)

```vue
<!-- 一階 filter，4 個 MultiSelect 都這樣 wire -->
<MultiSelect
  :model-value="firstTier.selection.pj_types"
  @update:model-value="firstTier.setSelection('pj_types', $event)"
/>
```

四個一階 filter 都使用同一個 pattern：每次 MultiSelect 內部的 checkbox toggle 都會 emit `update:model-value`，立刻打進 `firstTier.setSelection`。

### 2. setSelection 立刻排程 refresh

[frontend/src/production-history/composables/useFirstTierFilters.ts:210-215](frontend/src/production-history/composables/useFirstTierFilters.ts#L210-L215)

```ts
function setSelection(field: CachedFilterField, values: string[]): void {
  selection[field] = values;
  if (prunedFields.value.length) prunedFields.value = [];
  _scheduleRefresh();   // ← 每次勾選就排程
}
```

### 3. _scheduleRefresh 200ms debounce 後打 API

[frontend/src/production-history/composables/useFirstTierFilters.ts:192-206](frontend/src/production-history/composables/useFirstTierFilters.ts#L192-L206)

```ts
function _scheduleRefresh(): void {
  if (_debounceTimer !== null) clearTimeout(_debounceTimer);
  _debounceTimer = setTimeout(() => {
    _debounceTimer = null;
    void fetchFilterOptions({
      pj_types: selection.pj_types,
      packages: selection.packages,
      bops: selection.bops,
      pj_functions: selection.pj_functions,
    });
  }, debounceMs);
}
```

200ms 的 debounce 在「同一個 dropdown 內連續勾選」場景下會被每次勾選重置，看似可吸收快速連點；但只要使用者「停下來看一下再勾下一個」（超過 200ms），cross-filter 就立刻送出 → 其他 filter 的選項清單被收斂 → 使用者已經沒辦法在原本期望的清單上操作。這就是現象的根因。

### 4. 共用 MultiSelect 元件沒有對外公開「dropdown 關閉」事件

[frontend/src/shared-ui/components/MultiSelect.vue](frontend/src/shared-ui/components/MultiSelect.vue)

- 元件內部已有 `isOpen` ref 與 outside-click 偵測（line 108-111）
- 元件對外**沒有** `v-model:open`、`@close`、`@dropdown-close` 等事件
- 同一個元件目前被 9 個 app 共用：production-history、wip-detail、wip-overview、hold-overview、reject-history、resource-history、resource-status、query-tool、mid-section-defect、yield-alert-center
- 因此本次修正須**向下相容**：新增的事件/prop 必須為 optional，未掛載者維持現行行為

## Why the existing 200ms debounce is not enough

`_scheduleRefresh` 的 debounce 只能吸收「200ms 內的多次 click」。多選使用者不會用 200ms 連點，會看一眼選項再勾下一個，所以 debounce 永遠會 fire。需要的是「dropdown 仍開啟期間完全不 fire」+「dropdown 關閉時 fire 一次」。

## Test coverage today

- `frontend/tests/playwright/production-history-cross-filter.spec.ts` — 測 cross-filter 收斂，但每次勾選後都 `await page.locator('body').click(...)` 關閉 dropdown，等於繞過 bug，沒測到「同一 dropdown 內多選」。
- `frontend/tests/playwright/production-history-filter-options-error.spec.ts` — 錯誤路徑。
- `frontend/tests/playwright/production-history-pruning-feedback.spec.ts` — pruning UX feedback。
- `frontend/tests/legacy/production-history.test.js` — 舊版 smoke。

無任一測試覆蓋「同一 dropdown 內連續多選不觸發網路請求」這條 AC。
