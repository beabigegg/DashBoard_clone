## Context

設備歷史績效頁面已實作 OU%（Overall Utilization）指標，計算公式為 `PRD / (PRD + SBY + UDT + SDT + EGT)`。現有架構包含：

- **後端**: `resource_history_service.py` 提供 `query_summary()` 函數，回傳 KPI、趨勢、熱力圖等資料
- **API**: `/api/resource/history/summary` 回傳 JSON 包含 `kpi.ou_pct` 與 `trend[].ou_pct`
- **前端**: `resource_history.html` 使用 Chart.js 繪製 OU% 趨勢圖

現有 SQL 查詢已包含 `PRD_HOURS`, `SBY_HOURS`, `UDT_HOURS`, `SDT_HOURS`, `EGT_HOURS`, `NST_HOURS` 六種狀態時數，無需修改查詢。

## Goals / Non-Goals

**Goals:**
- 在 KPI 區新增 Availability% 卡片
- 在趨勢圖區新增 Availability% 趨勢線
- 公式: `Availability% = (PRD + SBY + EGT) / (PRD + SBY + EGT + SDT + UDT + NST)`
- 維持 API 向下相容

**Non-Goals:**
- 不修改現有 SQL 查詢（資料已足夠）
- 不新增獨立 API 端點
- 不改變現有 OU% 計算邏輯

## Decisions

### 1. Availability% 計算位置

**選擇**: 在後端 Python 計算

**理由**:
- 與 OU% 計算位置一致（`_build_kpi_from_df`, `_build_trend_from_df`）
- 避免前端重複計算
- 確保 API 回應可直接使用

**替代方案**: 前端計算
- 缺點: 增加前端複雜度，每次渲染都要計算

### 2. API 回應結構擴展

**選擇**: 新增 `availability_pct` 欄位至現有結構

```python
# KPI
{
    'ou_pct': 85.5,
    'availability_pct': 92.3,  # 新增
    'prd_hours': 1000,
    ...
}

# Trend
[
    {
        'date': '2026-01-01',
        'ou_pct': 85.5,
        'availability_pct': 92.3,  # 新增
        ...
    }
]
```

**理由**: 向下相容，現有前端不會因新欄位而出錯

### 3. 前端呈現方式

**選擇**: 在現有趨勢圖新增第二條線（雙 Y 軸或同一 Y 軸）

**理由**:
- 方便比較 OU% 與 Availability% 的變化趨勢
- 使用不同顏色區分（OU%: 藍色, Availability%: 綠色）

## Risks / Trade-offs

| 風險 | 影響 | 緩解措施 |
|------|------|----------|
| 分母為零時除法錯誤 | 計算失敗 | 分母為零時回傳 0 或 None |
| 趨勢圖過於複雜 | 可讀性下降 | 提供切換選項，可單獨顯示 |
| NST 資料缺失 | 計算不準確 | 現有查詢已包含 NST，無此風險 |
