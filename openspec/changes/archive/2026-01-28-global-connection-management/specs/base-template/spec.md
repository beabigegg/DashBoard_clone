# base-template

Flask Jinja2 base template，強制所有頁面載入核心 JS 模組。

## Requirements

### 目的

透過 Jinja2 template 繼承機制，確保：
1. 所有頁面自動載入 `toast.js` 和 `mes-api.js`
2. 所有頁面都有 Toast 容器 (`#mes-toast-container`)
3. 新開發的頁面只要繼承 `_base.html`，就自動獲得連線管理功能

### Template 結構

```html
<!DOCTYPE html>
<html lang="zh-TW">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{% block title %}MES Dashboard{% endblock %}</title>

    <!-- Toast 樣式 (內嵌) -->
    <style id="mes-core-styles">
        /* Toast CSS */
    </style>

    {% block head_extra %}{% endblock %}
</head>
<body>
    <!-- Toast 容器 -->
    <div id="mes-toast-container"></div>

    {% block content %}{% endblock %}

    <!-- 核心 JS -->
    <script src="{{ url_for('static', filename='js/toast.js') }}"></script>
    <script src="{{ url_for('static', filename='js/mes-api.js') }}"></script>

    {% block scripts %}{% endblock %}
</body>
</html>
```

### Block 定義

| Block | 用途 | 必填 |
|-------|------|------|
| `title` | 頁面標題 | 否 (預設 "MES Dashboard") |
| `head_extra` | 頁面專屬 CSS / meta tags | 否 |
| `content` | 頁面主要內容 | 是 |
| `scripts` | 頁面專屬 JavaScript | 否 |

### 子頁面使用範例

```html
{% extends "_base.html" %}

{% block title %}WIP Detail Dashboard{% endblock %}

{% block head_extra %}
<style>
    .dashboard { max-width: 1900px; }
    /* 頁面專屬樣式 */
</style>
{% endblock %}

{% block content %}
<div class="dashboard">
    <!-- 頁面內容 -->
</div>
{% endblock %}

{% block scripts %}
<script>
    // MesApi 和 Toast 已可用
    async function loadData() {
        const data = await MesApi.get('/api/wip/summary');
        // ...
    }

    loadData();
</script>
{% endblock %}
```

### Toast CSS 樣式規格

內嵌在 `_base.html` 的 Toast 樣式：

```css
/* 容器 */
.mes-toast-container {
    position: fixed;
    top: 20px;
    right: 20px;
    z-index: 9999;
    display: flex;
    flex-direction: column;
    gap: 10px;
    pointer-events: none;
}

/* 單個 Toast */
.mes-toast {
    display: flex;
    align-items: center;
    gap: 10px;
    padding: 12px 16px;
    border-radius: 8px;
    background: white;
    box-shadow: 0 4px 12px rgba(0, 0, 0, 0.15);
    font-size: 14px;
    pointer-events: auto;
    animation: mes-toast-enter 0.3s ease-out;
    max-width: 360px;
}

/* 類型顏色 */
.mes-toast-info { border-left: 4px solid #3b82f6; }
.mes-toast-success { border-left: 4px solid #22c55e; }
.mes-toast-warning { border-left: 4px solid #f59e0b; }
.mes-toast-error { border-left: 4px solid #ef4444; }
.mes-toast-loading { border-left: 4px solid #6b7280; }

/* Icon 顏色 */
.mes-toast-info .mes-toast-icon { color: #3b82f6; }
.mes-toast-success .mes-toast-icon { color: #22c55e; }
.mes-toast-warning .mes-toast-icon { color: #f59e0b; }
.mes-toast-error .mes-toast-icon { color: #ef4444; }
.mes-toast-loading .mes-toast-icon { color: #6b7280; }

/* Loading 旋轉動畫 */
.mes-toast-loading .mes-toast-icon {
    animation: mes-spin 1s linear infinite;
}

/* 按鈕 */
.mes-toast-close, .mes-toast-retry {
    background: none;
    border: none;
    cursor: pointer;
    padding: 4px 8px;
    border-radius: 4px;
}

.mes-toast-close:hover { background: rgba(0,0,0,0.1); }
.mes-toast-retry {
    color: #3b82f6;
    font-weight: 600;
}
.mes-toast-retry:hover { background: rgba(59,130,246,0.1); }

/* 動畫 */
@keyframes mes-toast-enter {
    from { transform: translateX(100%); opacity: 0; }
    to { transform: translateX(0); opacity: 1; }
}

.mes-toast-exit {
    animation: mes-toast-exit 0.3s ease-in forwards;
}

@keyframes mes-toast-exit {
    from { transform: translateX(0); opacity: 1; }
    to { transform: translateX(100%); opacity: 0; }
}

@keyframes mes-spin {
    from { transform: rotate(0deg); }
    to { transform: rotate(360deg); }
}
```

### 需遷移的頁面

以下頁面需改為繼承 `_base.html`：

| 頁面 | 檔案 | 備註 |
|------|------|------|
| Portal | `portal.html` | 首頁，可能不需要 API |
| WIP Detail | `wip_detail.html` | 需移除內嵌 fetchWithTimeout |
| WIP Overview | `wip_overview.html` | 需移除內嵌 fetchWithTimeout |
| Tables | `index.html` | 需加入 MesApi 使用 |
| Resource | `resource_status.html` | 需加入 MesApi 使用 |
| Excel Query | `excel_query.html` | 需加入 MesApi 使用 |

## Acceptance Criteria

- [ ] `_base.html` 包含所有必要的 block 定義
- [ ] Toast 容器 `#mes-toast-container` 存在於 body 內
- [ ] `toast.js` 和 `mes-api.js` 正確載入
- [ ] Toast CSS 樣式正確內嵌
- [ ] 子頁面可透過 `{% extends "_base.html" %}` 繼承
- [ ] 子頁面可使用 `MesApi` 和 `Toast` 全域物件
- [ ] 所有 6 個現有頁面成功遷移

## Dependencies

- `toast.js` (toast-notification capability)
- `mes-api.js` (mes-api-client capability)

## File Location

`src/mes_dashboard/templates/_base.html`
