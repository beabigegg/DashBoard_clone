# toast-notification

前端通知系統，顯示 info/success/warning/error/loading 狀態訊息。

## Requirements

### Toast 類型

| Type | 顏色 | Icon | 自動消失 | 用途 |
|------|------|------|----------|------|
| info | 藍色 (#3b82f6) | ℹ | 3 秒 | 一般資訊 |
| success | 綠色 (#22c55e) | ✓ | 2 秒 | 操作成功 |
| warning | 橙色 (#f59e0b) | ⚠ | 5 秒 | 警告訊息 |
| error | 紅色 (#ef4444) | ✗ | 不自動消失 | 錯誤訊息 |
| loading | 灰色 (#6b7280) | ⟳ (動畫) | 不自動消失 | 載入中 |

### API 設計

```javascript
// 基本使用
Toast.info('訊息內容');
Toast.success('操作成功');
Toast.warning('請注意');
Toast.error('發生錯誤');

// Error 附帶重試按鈕
Toast.error('連線失敗', { retry: () => loadData() });

// Loading 狀態
const id = Toast.loading('載入中...');

// 更新 Toast
Toast.update(id, { type: 'success', message: '完成!' });

// 手動關閉
Toast.dismiss(id);
```

### 顯示位置與行為

1. **位置**: 畫面右上角，距離頂部 20px，距離右側 20px
2. **堆疊**: 多個 Toast 垂直堆疊，最新的在最上方
3. **最大數量**: 同時最多顯示 5 個，超過時移除最舊的
4. **動畫**:
   - 進入: 從右側滑入 (0.3s ease-out)
   - 離開: 向右滑出並淡出 (0.3s ease-in)

### UI 元素

每個 Toast 包含：
1. **Icon**: 對應類型的圖示
2. **Message**: 訊息文字
3. **Close Button**: 右側 × 按鈕，點擊關閉
4. **Retry Button** (可選): 僅 error 類型，點擊觸發 retry callback

### CSS Class 命名

使用 `mes-` 前綴避免衝突：
- `.mes-toast-container` - 容器
- `.mes-toast` - 單個 Toast
- `.mes-toast-info` / `.mes-toast-success` / ... - 類型樣式
- `.mes-toast-icon` - 圖示
- `.mes-toast-message` - 訊息
- `.mes-toast-close` - 關閉按鈕
- `.mes-toast-retry` - 重試按鈕
- `.mes-toast-exit` - 離開動畫

### Loading Icon 動畫

```css
.mes-toast-loading .mes-toast-icon {
    animation: mes-spin 1s linear infinite;
}

@keyframes mes-spin {
    from { transform: rotate(0deg); }
    to { transform: rotate(360deg); }
}
```

## Acceptance Criteria

- [ ] `Toast.info()` 顯示藍色 Toast，3 秒後自動消失
- [ ] `Toast.success()` 顯示綠色 Toast，2 秒後自動消失
- [ ] `Toast.warning()` 顯示橙色 Toast，5 秒後自動消失
- [ ] `Toast.error()` 顯示紅色 Toast，不自動消失
- [ ] `Toast.error(msg, { retry: fn })` 顯示重試按鈕，點擊觸發 fn
- [ ] `Toast.loading()` 顯示帶旋轉動畫的 Toast
- [ ] `Toast.update()` 可更新現有 Toast 的類型和訊息
- [ ] `Toast.dismiss()` 可手動關閉 Toast
- [ ] 點擊 × 按鈕可關閉 Toast
- [ ] Toast 有進入/離開動畫
- [ ] 同時最多顯示 5 個 Toast

## Dependencies

無（獨立模組）

## File Location

`src/mes_dashboard/static/js/toast.js`

## 樣式內嵌於 `_base.html`

Toast 的 CSS 樣式將內嵌在 `_base.html` 的 `<style>` 區塊中，確保所有頁面都有樣式定義。
