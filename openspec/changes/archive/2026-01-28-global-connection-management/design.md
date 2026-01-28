# Technical Design

## Decision: 前端模組架構

**選擇**: 獨立 JS 檔案 + Jinja2 Base Template

**原因**:
- 模組化：各頁面共用同一份程式碼，維護一處即可
- 強制性：透過 Base Template，新頁面自動繼承核心模組
- 現代化：符合業界標準的前端架構模式

**檔案結構**:
```
src/mes_dashboard/
├── static/
│   └── js/
│       ├── mes-api.js      ← 核心 API Client
│       └── toast.js        ← 通知系統
└── templates/
    ├── _base.html          ← Base template (載入核心 JS)
    ├── wip_detail.html     ← {% extends "_base.html" %}
    ├── wip_overview.html   ← {% extends "_base.html" %}
    └── ...
```

---

## Decision: API Client 設計 (mes-api.js)

**選擇**: 全域 `MesApi` 物件，提供統一的 fetch wrapper

**API 設計**:
```javascript
// 基本使用
const data = await MesApi.get('/api/wip/summary');
const data = await MesApi.post('/api/query_table', { table_name: 'xxx' });

// 帶參數
const data = await MesApi.get('/api/wip/detail/ASSY', {
    params: { page: 1, page_size: 100 }
});

// 可取消的請求
const controller = new AbortController();
const data = await MesApi.get('/api/xxx', { signal: controller.signal });
controller.abort();  // 取消

// 自訂選項
const data = await MesApi.get('/api/xxx', {
    timeout: 60000,    // 覆蓋預設 timeout (30s)
    retries: 5,        // 覆蓋預設重試次數 (3)
    silent: true,      // 不顯示 toast
});
```

**內部結構**:
```javascript
const MesApi = {
    // 預設配置
    defaults: {
        timeout: 30000,
        retries: 3,
        retryDelays: [1000, 2000, 4000],  // Exponential backoff
    },

    // GET 請求
    async get(url, options = {}) { ... },

    // POST 請求
    async post(url, data, options = {}) { ... },

    // 內部方法
    _fetch(url, options) { ... },
    _retry(fn, retries, delays) { ... },
    _generateRequestId() { ... },
};
```

---

## Decision: Retry 策略

**選擇**: Exponential Backoff（指數退避）

**來源**: AWS SDK、Google Cloud Client Libraries 標準做法

**配置**:
| 重試次數 | 等待時間 | 累計時間 |
|----------|----------|----------|
| 1st retry | 1000ms | 1s |
| 2nd retry | 2000ms | 3s |
| 3rd retry | 4000ms | 7s |
| Give up | - | - |

**重試條件**:
| 錯誤類型 | 重試 | 原因 |
|----------|------|------|
| Timeout | ✓ | 網路慢或 server 忙 |
| Network Error | ✓ | 暫時性網路問題 |
| 5xx Server Error | ✓ | Server 暫時錯誤 |
| 4xx Client Error | ✗ | 參數錯誤，重試無意義 |
| Aborted | ✗ | 使用者主動取消 |

**實作**:
```javascript
async _fetchWithRetry(url, options, retryCount = 0) {
    try {
        return await this._fetch(url, options);
    } catch (error) {
        // 不重試的情況
        if (error.name === 'AbortError') throw error;
        if (error.status >= 400 && error.status < 500) throw error;

        // 超過重試次數
        if (retryCount >= this.defaults.retries) {
            throw error;
        }

        // 等待後重試
        const delay = this.defaults.retryDelays[retryCount];
        Toast.info(`正在重試 (${retryCount + 1}/${this.defaults.retries})...`);
        await this._sleep(delay);

        return this._fetchWithRetry(url, options, retryCount + 1);
    }
}
```

---

## Decision: Toast 通知系統

**選擇**: 輕量級自建 Toast，不引入外部依賴

**原因**:
- 功能簡單，不需要完整 UI 框架
- 減少依賴，避免版本衝突
- 完全控制樣式與行為

**Toast 類型**:
| Type | 顏色 | Icon | 自動消失 |
|------|------|------|----------|
| info | 藍 | ℹ | 3s |
| success | 綠 | ✓ | 2s |
| warning | 橙 | ⚠ | 5s |
| error | 紅 | ✗ | 不消失 |
| loading | 灰 | ⟳ | 不消失 |

**API 設計**:
```javascript
// 基本使用
Toast.info('訊息已發送');
Toast.success('資料已更新');
Toast.warning('連線不穩定');
Toast.error('載入失敗', { retry: () => loadData() });

// Loading 狀態（可更新/關閉）
const id = Toast.loading('載入中...');
Toast.update(id, { type: 'success', message: '完成' });
// 或
Toast.dismiss(id);
```

**位置**: 畫面右上角，堆疊顯示（最新在上）

---

## Decision: Request Deduplication

**選擇**: 可選功能，預設關閉

**原因**:
- 大多數場景不需要（AbortController 已處理）
- 某些場景需要重複請求（如強制刷新）
- 保持簡單，避免過度設計

**使用方式**:
```javascript
// 啟用 deduplication
const data = await MesApi.get('/api/xxx', { dedupe: true });
```

---

## Decision: Base Template 設計

**選擇**: Jinja2 `{% extends %}` + `{% block %}` 模式

**_base.html 結構**:
```html
<!DOCTYPE html>
<html lang="zh-TW">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{% block title %}MES Dashboard{% endblock %}</title>

    <!-- Toast 樣式 -->
    <style id="mes-core-styles">
        .mes-toast-container { ... }
        .mes-toast { ... }
    </style>

    {% block head_extra %}{% endblock %}
</head>
<body>
    <!-- Toast 容器 (所有頁面都有) -->
    <div id="mes-toast-container"></div>

    {% block content %}{% endblock %}

    <!-- 核心 JS (所有頁面必載) -->
    <script src="{{ url_for('static', filename='js/toast.js') }}"></script>
    <script src="{{ url_for('static', filename='js/mes-api.js') }}"></script>

    {% block scripts %}{% endblock %}
</body>
</html>
```

**子頁面使用**:
```html
{% extends "_base.html" %}

{% block title %}WIP Detail{% endblock %}

{% block head_extra %}
<style>/* 頁面專屬樣式 */</style>
{% endblock %}

{% block content %}
<!-- 頁面內容 -->
{% endblock %}

{% block scripts %}
<script>
    // 使用 MesApi
    async function loadData() {
        const data = await MesApi.get('/api/wip/summary');
        // ...
    }
</script>
{% endblock %}
```

---

## Implementation Approach

### mes-api.js 核心邏輯

```javascript
/**
 * MES Dashboard API Client
 * 提供統一的 API 請求管理，內建 timeout、retry、取消機制
 */
const MesApi = (function() {
    'use strict';

    const defaults = {
        timeout: 30000,           // 30s
        retries: 3,
        retryDelays: [1000, 2000, 4000],
        baseUrl: '',
    };

    // 請求 ID 計數器
    let requestCounter = 0;

    function generateRequestId() {
        return `req_${(++requestCounter).toString(36)}`;
    }

    function buildUrl(url, params) {
        if (!params) return url;
        const searchParams = new URLSearchParams(params);
        return `${url}?${searchParams}`;
    }

    function log(requestId, ...args) {
        console.log(`[MesApi] ${requestId}`, ...args);
    }

    async function fetchWithTimeout(url, options, timeout, signal) {
        const controller = new AbortController();
        const timeoutId = setTimeout(() => controller.abort(), timeout);

        // 合併外部 signal
        if (signal) {
            signal.addEventListener('abort', () => controller.abort());
        }

        try {
            const response = await fetch(url, {
                ...options,
                signal: controller.signal,
            });
            clearTimeout(timeoutId);
            return response;
        } catch (error) {
            clearTimeout(timeoutId);
            throw error;
        }
    }

    async function request(method, url, data, options = {}) {
        const requestId = generateRequestId();
        const timeout = options.timeout ?? defaults.timeout;
        const retries = options.retries ?? defaults.retries;
        const silent = options.silent ?? false;

        const fullUrl = buildUrl(defaults.baseUrl + url, options.params);

        log(requestId, method, fullUrl);

        const fetchOptions = {
            method,
            headers: { 'Content-Type': 'application/json' },
        };

        if (data) {
            fetchOptions.body = JSON.stringify(data);
        }

        let lastError;
        for (let attempt = 0; attempt <= retries; attempt++) {
            try {
                const startTime = Date.now();
                const response = await fetchWithTimeout(
                    fullUrl, fetchOptions, timeout, options.signal
                );
                const elapsed = Date.now() - startTime;

                if (!response.ok) {
                    const error = new Error(`HTTP ${response.status}`);
                    error.status = response.status;
                    error.response = response;
                    throw error;
                }

                const result = await response.json();
                log(requestId, `✓ ${response.status} (${elapsed}ms)`);
                return result;

            } catch (error) {
                lastError = error;

                // Aborted: 不重試，不顯示 toast
                if (error.name === 'AbortError') {
                    log(requestId, '⊘ Aborted');
                    throw error;
                }

                // 4xx: 不重試
                if (error.status >= 400 && error.status < 500) {
                    log(requestId, `✗ ${error.status} (no retry)`);
                    if (!silent) Toast.error(`請求失敗: ${error.message}`);
                    throw error;
                }

                // 最後一次嘗試失敗
                if (attempt === retries) {
                    log(requestId, `✗ Failed after ${retries + 1} attempts`);
                    if (!silent) {
                        Toast.error('連線失敗', {
                            retry: () => request(method, url, data, options)
                        });
                    }
                    throw error;
                }

                // 準備重試
                const delay = defaults.retryDelays[attempt] ?? 4000;
                log(requestId, `✗ Retry ${attempt + 1}/${retries} in ${delay}ms`);
                if (!silent) {
                    Toast.info(`正在重試 (${attempt + 1}/${retries})...`);
                }
                await new Promise(r => setTimeout(r, delay));
            }
        }

        throw lastError;
    }

    return {
        defaults,
        get: (url, options) => request('GET', url, null, options),
        post: (url, data, options) => request('POST', url, data, options),
    };
})();
```

### toast.js 核心邏輯

```javascript
/**
 * MES Dashboard Toast Notification System
 */
const Toast = (function() {
    'use strict';

    const container = document.getElementById('mes-toast-container');
    let toastId = 0;

    const icons = {
        info: 'ℹ',
        success: '✓',
        warning: '⚠',
        error: '✗',
        loading: '⟳',
    };

    const durations = {
        info: 3000,
        success: 2000,
        warning: 5000,
        error: 0,      // 不自動消失
        loading: 0,    // 不自動消失
    };

    function create(type, message, options = {}) {
        const id = `toast-${++toastId}`;
        const toast = document.createElement('div');
        toast.id = id;
        toast.className = `mes-toast mes-toast-${type}`;

        toast.innerHTML = `
            <span class="mes-toast-icon">${icons[type]}</span>
            <span class="mes-toast-message">${message}</span>
            ${options.retry ? '<button class="mes-toast-retry">重試</button>' : ''}
            <button class="mes-toast-close">×</button>
        `;

        // 事件綁定
        toast.querySelector('.mes-toast-close').onclick = () => dismiss(id);
        if (options.retry) {
            toast.querySelector('.mes-toast-retry').onclick = () => {
                dismiss(id);
                options.retry();
            };
        }

        container.prepend(toast);

        // 自動消失
        const duration = options.duration ?? durations[type];
        if (duration > 0) {
            setTimeout(() => dismiss(id), duration);
        }

        return id;
    }

    function dismiss(id) {
        const toast = document.getElementById(id);
        if (toast) {
            toast.classList.add('mes-toast-exit');
            setTimeout(() => toast.remove(), 300);
        }
    }

    function update(id, options) {
        const toast = document.getElementById(id);
        if (toast && options.type) {
            toast.className = `mes-toast mes-toast-${options.type}`;
            toast.querySelector('.mes-toast-icon').textContent = icons[options.type];
        }
        if (toast && options.message) {
            toast.querySelector('.mes-toast-message').textContent = options.message;
        }
        if (options.autoDismiss) {
            setTimeout(() => dismiss(id), options.autoDismiss);
        }
    }

    return {
        info: (msg, opts) => create('info', msg, opts),
        success: (msg, opts) => create('success', msg, opts),
        warning: (msg, opts) => create('warning', msg, opts),
        error: (msg, opts) => create('error', msg, opts),
        loading: (msg, opts) => create('loading', msg, opts),
        dismiss,
        update,
    };
})();
```

---

## Data Flow

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                           Request Lifecycle                                  │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│   Page Code                                                                  │
│   const data = await MesApi.get('/api/wip/summary');                        │
│       │                                                                      │
│       ▼                                                                      │
│   ┌──────────────────────────────────────────────────────────────────────┐  │
│   │ MesApi.request()                                                      │  │
│   │  1. Generate Request ID (req_1a2b3c)                                 │  │
│   │  2. Build full URL with params                                       │  │
│   │  3. Log: [MesApi] req_1a2b3c GET /api/wip/summary                   │  │
│   └──────────────────────────────────────────────────────────────────────┘  │
│       │                                                                      │
│       ▼                                                                      │
│   ┌──────────────────────────────────────────────────────────────────────┐  │
│   │ Attempt 1                                                             │  │
│   │  - Start timeout timer (30s)                                         │  │
│   │  - fetch() with AbortController                                      │  │
│   └──────────────────────────────────────────────────────────────────────┘  │
│       │                                                                      │
│       ├── Success ──► Log: ✓ 200 (234ms) ──► Return data                   │
│       │                                                                      │
│       ├── Timeout/5xx ──► Log: ✗ Retry 1/3 in 1000ms                       │
│       │                   Toast.info("正在重試 (1/3)...")                   │
│       │                   wait(1000ms)                                      │
│       │                       │                                             │
│       │                       ▼                                             │
│       │               ┌─────────────────────────────────────────────────┐  │
│       │               │ Attempt 2                                        │  │
│       │               │  - fetch() again                                 │  │
│       │               └─────────────────────────────────────────────────┘  │
│       │                       │                                             │
│       │               ├── Success ──► Return data                          │
│       │               ├── Failed ──► Retry 2/3 in 2000ms ... (repeat)      │
│       │               └── All retries exhausted                             │
│       │                       │                                             │
│       │                       ▼                                             │
│       │               Toast.error("連線失敗", { retry: fn })                │
│       │               throw Error                                           │
│       │                                                                      │
│       ├── 4xx ──► Log: ✗ 400 (no retry)                                    │
│       │           Toast.error("請求失敗: ...")                              │
│       │           throw Error                                               │
│       │                                                                      │
│       └── Aborted ──► Log: ⊘ Aborted                                       │
│                       throw AbortError (no toast)                           │
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## Testing Strategy

### 1. 手動測試場景

| 場景 | 測試方法 | 預期結果 |
|------|----------|----------|
| 正常請求 | 正常操作 | 無 toast，console 顯示 ✓ |
| Timeout | 後端加 `time.sleep(35)` | 顯示重試 toast，最終失敗 |
| 5xx 錯誤 | 後端回傳 500 | 顯示重試 toast |
| 4xx 錯誤 | 錯誤參數 | 直接顯示錯誤，無重試 |
| 請求取消 | 快速換頁 | 無 toast，console 顯示 ⊘ |
| 手動重試 | 點擊重試按鈕 | 重新發送請求 |

### 2. Console 驗證

```
[MesApi] req_1 GET /api/wip/summary
[MesApi] req_1 ✓ 200 (234ms)

[MesApi] req_2 GET /api/wip/detail/ASSY?page=1
[MesApi] req_2 ⊘ Aborted

[MesApi] req_3 GET /api/wip/detail/ASSY?page=2
[MesApi] req_3 ✗ Retry 1/3 in 1000ms
[MesApi] req_3 ✗ Retry 2/3 in 2000ms
[MesApi] req_3 ✓ 200 (1523ms)
```

---

## Migration Strategy

### Phase 1: 建立基礎設施
1. 建立 `static/js/` 目錄
2. 建立 `toast.js`
3. 建立 `mes-api.js`
4. 建立 `_base.html`

### Phase 2: 遷移 WIP 頁面
1. `wip_detail.html` - 移除 fetchWithTimeout，使用 MesApi
2. `wip_overview.html` - 移除 fetchWithTimeout，使用 MesApi
3. 測試驗證

### Phase 3: 遷移其他頁面
1. `index.html` (Tables)
2. `resource_status.html`
3. `excel_query.html`
4. `portal.html`

### 遷移檢查清單（每頁面）

- [ ] 改用 `{% extends "_base.html" %}`
- [ ] 移除內嵌的 `fetchWithTimeout` 函數
- [ ] 移除內嵌的 `AbortController` 管理邏輯
- [ ] 將 `fetch()` 改為 `MesApi.get()` / `MesApi.post()`
- [ ] 保留 AbortController 用於請求取消（傳入 signal 參數）
- [ ] 移除手動的錯誤 toast 顯示（MesApi 自動處理）
- [ ] 測試正常流程
- [ ] 測試錯誤流程

---

## 風險與緩解

| 風險 | 影響 | 緩解措施 |
|------|------|----------|
| JS 載入失敗 | 頁面無法運作 | 使用 `defer` 確保 DOM 就緒，加入基本 fallback |
| Toast 樣式衝突 | 顯示異常 | 使用 `mes-` 前綴的 class 名稱 |
| 重試風暴 | Server 壓力增加 | Exponential backoff 已內建延遲 |
| 遷移遺漏 | 部分頁面未保護 | 逐頁遷移，完成一個測試一個 |

---

## 額外考量

### URL for Static Files

確保 Flask 正確服務 static 檔案：

```python
# app.py - Flask 預設已支援，確認 static_folder 設定
app = Flask(__name__,
    template_folder="templates",
    static_folder="static"  # 確保有這個
)
```

### Cache Busting（可選）

防止瀏覽器快取舊版 JS：

```html
<!-- _base.html -->
<script src="{{ url_for('static', filename='js/mes-api.js') }}?v=1.0"></script>
```

或使用檔案 hash（進階，暫不實作）。

### CSP 考量

如果未來加入 Content Security Policy，確保允許 inline styles（Toast 需要）：

```html
<meta http-equiv="Content-Security-Policy" content="style-src 'self' 'unsafe-inline';">
```
