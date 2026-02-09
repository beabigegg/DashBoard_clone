## Context

目前系統有 11 個頁面，全部使用 Jinja2 shell + Vite JS 混合模式。前端無 UI 框架（純 vanilla JS），ECharts 以靜態 minified 檔案引入（非 npm）。WIP 資料透過 Redis 快取，每 10 分鐘從 Oracle DWH.DW_MES_LOT_V 同步。

QC-GATE 頁面將是第一個採用 Vue 3 + Vite 純前端架構的頁面，建立後續遷移模式。

## Goals / Non-Goals

**Goals:**
- 提供 QC-GATE 站點即時 LOT 狀態報表（條圖 + 篩選清單）
- 建立純 Vue 3 + Vite 頁面架構模式（不依賴 Jinja2）
- 與現有 portal iframe 機制無縫整合
- 複用現有 WIP Redis 快取，不增加 Oracle 查詢負擔

**Non-Goals:**
- 不遷移現有頁面到 Vue 3（本次僅建立模式）
- 不引入 Vue Router 或 Pinia（單頁報表不需要）
- 不修改現有 CSP 或安全策略
- 不改動 WIP 快取更新機制

## Decisions

### D1: UI 框架選型 — Vue 3

**選擇**: Vue 3 (Composition API + SFC)
**替代方案**: React (JSX 轉換成本較高), Svelte (生態系較小)
**理由**: Vite 原生支援、template 語法接近 Jinja 降低遷移門檻、vue-echarts 整合成熟、支持漸進式頁面遷移

### D2: 頁面服務方式 — Vite MPA HTML entry + Flask 靜態服務

**選擇**: Vite build 產出完整 HTML (`frontend/src/qc-gate/index.html`)，Flask 以 `send_from_directory` 服務
**替代方案**: 最小 Jinja shell（仍有 Jinja 依賴）
**理由**:
- 完全脫離 Jinja2，建立乾淨的遷移模式
- 此頁面為唯讀報表，只有 GET 請求，不需要 CSRF token 注入
- Toast 功能由 Vue component 自行實作（不依賴 `_base.html` 的全域 toast）
- Vite config 已有 `manualChunks` 設定，只需新增 HTML entry

### D3: ECharts 引入方式 — npm + tree-shaking

**選擇**: `npm install echarts vue-echarts`，使用 tree-shaking 只引入 bar chart 相關模組
**替代方案**: 繼續使用靜態 minified 檔案（無法 tree-shake，~1MB）
**理由**: 既有 Vite config 已有 `vendor-echarts` chunk split 邏輯；npm 引入後可 tree-shake 到只需 bar chart 模組（~200KB gzipped）

### D4: API 設計 — 新增 `/api/qc-gate/summary` 端點

**選擇**: 新建 `qc_gate_routes.py` blueprint + `qc_gate_service.py` 服務
**替代方案**: 擴展現有 wip_routes（不符合 SRP）
**理由**:
- 從 WIP Redis 快取中讀取，篩選 `SPECNAME LIKE '%QC%GATE%'`
- 使用 `DW_MES_SPEC_WORKCENTER_V`（已在 filter_cache.py 中快取）取得站點排序
- 在後端完成 6HR 分級計算，前端只負責渲染
- 回傳結構包含 summary（條圖資料）和 lots（清單資料）

### D5: QC-GATE 站點識別與排序

**選擇**: 從 WIP 快取篩選 `SPECNAME` 包含 "QC" 和 "GATE" 的 LOT，站點排序從 `DW_MES_SPEC_WORKCENTER_V` 的 `SPEC` 欄位匹配取得 `SPEC_ORDER`
**理由**: SPECNAME 是 LOT 層級的製程步驟名稱，DW_MES_SPEC_WORKCENTER_V 是維度主表提供排序資訊

### D6: 等待時間分級

**選擇**: 四級分組
- `< 6hr` — 正常（綠色）
- `6-12hr` — 注意（黃色）
- `12-24hr` — 警告（橙色）
- `> 24hr` — 超時（紅色）

**計算**: `wait_hours = (SYS_DATE - MOVEINTIMESTAMP)` 以小時為單位，在後端計算

### D7: 自動刷新 — 複用 wip-overview 模式

**選擇**: 10 分鐘 `setInterval` + `visibilitychange` 即時刷新
**理由**: 與 WIP 快取同步週期一致，避免無效請求；tab 隱藏時跳過刷新

## Architecture

```
┌─ Vite Build ──────────────────────────────┐
│ frontend/src/qc-gate/                     │
│   index.html       ← HTML entry (no Jinja)│
│   main.js          ← createApp, mount     │
│   App.vue          ← root layout          │
│   components/                             │
│     QcGateChart.vue  ← ECharts stacked bar│
│     LotTable.vue     ← filterable table   │
│   composables/                            │
│     useQcGateData.js ← fetch + transform  │
│     useAutoRefresh.js← 10min refresh logic│
│   style.css        ← page styles          │
│                                           │
│ Build output → static/dist/qc-gate.html   │
│                static/dist/qc-gate.js     │
│                static/dist/qc-gate.css    │
└───────────────────────────────────────────┘

┌─ Flask Backend ───────────────────────────┐
│ routes/qc_gate_routes.py                  │
│   GET /api/qc-gate/summary               │
│                                           │
│ services/qc_gate_service.py               │
│   get_qc_gate_summary()                   │
│     ├─ get_cached_wip_data()  (Redis)     │
│     ├─ filter SPECNAME %QC%GATE%          │
│     ├─ compute wait_hours per LOT         │
│     └─ group by SPECNAME + bucket         │
│                                           │
│ app.py                                    │
│   GET /qc-gate → send_from_directory()    │
└───────────────────────────────────────────┘
```

## API Response Shape

```json
{
  "cache_time": "2026-02-09T14:30:00",
  "stations": [
    {
      "specname": "QC-GATE-DB",
      "spec_order": "030",
      "buckets": {
        "lt_6h": 12,
        "6h_12h": 5,
        "12h_24h": 3,
        "gt_24h": 1
      },
      "total": 21,
      "lots": [
        {
          "lot_id": "L001",
          "container_id": "C001",
          "product": "PKG-A",
          "qty": 5000,
          "step": "QC-GATE-DB",
          "workorder": "WO123",
          "move_in_time": "2026-02-09T08:30:00",
          "wait_hours": 6.0,
          "bucket": "6h_12h",
          "status": "QUEUE",
          "equipment": null
        }
      ]
    }
  ]
}
```

## Vite Config Changes

```js
// vite.config.js additions
import vue from '@vitejs/plugin-vue';

export default defineConfig({
  plugins: [vue()],
  build: {
    rollupOptions: {
      input: {
        // ... existing entries ...
        'qc-gate': resolve(__dirname, 'src/qc-gate/index.html')  // HTML entry
      },
      output: {
        manualChunks(id) {
          if (!id.includes('node_modules')) return;
          if (id.includes('echarts')) return 'vendor-echarts';
          if (id.includes('vue')) return 'vendor-vue';  // 新增 Vue chunk
          return 'vendor';
        }
      }
    }
  }
});
```

## Risks / Trade-offs

- **[Vue plugin 影響既有 build]** → `@vitejs/plugin-vue` 只處理 `.vue` 檔案，不影響現有 `.js` entry points。已驗證 Vite plugin 系統為 additive。
- **[ECharts npm vs 靜態檔案共存]** → 新頁面用 npm echarts，舊頁面繼續用靜態檔案。`vendor-echarts` chunk 只被 qc-gate 引用，不影響舊頁面 bundle size。
- **[SPECNAME pattern 可能變動]** → 篩選邏輯集中在 `qc_gate_service.py` 單一位置，易於調整。
- **[純靜態 HTML 無法使用 Flask template context]** → 此頁面為唯讀報表，不需要 CSRF、不需要 session 資料。認證由 portal iframe 外層處理。
