# Hold History — Technical Notes

## Future Hold 時效衰減行為

### 現象說明

「累計 Future Hold」指標依 PJMES043 原廠 SQL 邏輯計算（`FUTUREHOLDCOMMENTS IS NOT NULL AND RN_FUTURE_REASON > 1`）。

實際觀察到的衰減行為：
- 當 lot 尚在 hold 狀態時，`FUTUREHOLDCOMMENTS` 有值 → `futureHoldQty` 計入
- 當 lot 被 MES release 後，MES 可能**清除 `FUTUREHOLDCOMMENTS` 欄位**
- 再次查詢時，該 lot 不再符合條件 → **歷史日期的 `futureHoldQty` 數值減少**

結論：`futureHoldQty` 具時效衰減性，不是單調遞增指標，不適合用於長期趨勢追蹤。

### 與 PJMES043 Excel 快照的差異

PJMES043 Excel 為某一時刻的快照，與動態查詢結果在 release 後可能不一致。這不是程式 bug，而是 MES 端清除備註的預期行為。

### 穩定替代指標

`repeatQualityHoldQty`：同工單同原因的 quality Hold 再次發生總量

- 計算邏輯：`SUM(QTY) WHERE RN_FUTURE_REASON > 1 AND HOLD_TYPE = 'quality'`
- 不依賴 `FUTUREHOLDCOMMENTS` 欄位
- 值為**只增不減**的穩定歷史指標
- 卡片定位：品質異常再次發生的穩定監控指標，補足 Future Hold 衰減的盲點

## PJMES043 原廠 SQL（ground truth）

原廠 `RN_CONHOLD`（= 本系統 `RN_FUTURE_REASON`）分區鍵：`PARTITION BY CONTAINERID, HOLDREASONID ORDER BY HOLDTXNDATE`

`FUTURE_HOLD_FLAG = 0`（即計入 futureHoldQty）的條件：`FUTUREHOLDCOMMENTS IS NOT NULL AND RN_CONHOLD > 1`

本系統 `base_facts.sql` 的等價實現：
- `IS_FUTURE_HOLD = 1`（FUTUREHOLDCOMMENTS IS NOT NULL）
- `FUTURE_HOLD_FLAG = CASE WHEN IS_FUTURE_HOLD = 1 AND RN_FUTURE_REASON <> 1 THEN 0 ELSE 1 END`
- 計入 futureHoldQty 的條件：`IS_FUTURE_HOLD = 1 AND FUTURE_HOLD_FLAG = 1`

等價性已驗證（2026-02-10）。

## Duration 指標計算

`HOLD_HOURS` 在 `base_facts.sql` 中計算：
- Released：`(RELEASETXNDATE - HOLDTXNDATE) * 24`（精確到秒）
- On-hold：`(SYSDATE - HOLDTXNDATE) * 24`（spool 建立當下快照，TTL 15 分鐘）

Oracle DB timezone 已驗證為 `+08:00`，SYSDATE 回傳台灣時間，HOLD_HOURS 計算可信。

「持續 Hold 平均時長」使用 spool 快照值，最大誤差 = spool TTL（15 分鐘），對均值語意可接受。

## 當日模式（Today Mode）

當日模式透過 `POST /api/hold-history/today-snapshot` 提供即時快照，與區間模式的兩段式查詢完全獨立。

### 資料邊界

當日模式的 WHERE 子句聯集三個條件：

1. **現況 on hold**：`RELEASETXNDATE IS NULL`（不限 hold_day）
2. **今日 release**：`release_day = today`
3. **今日新增**：`hold_day = today`

任何滿足其一的 lot 都會被拉入快照，再依 `record_type` 在 Python 端做二次過濾。

### SYSDATE 與 07:30 班別分界

「today」由 server `SYSDATE` 推算，邏輯與 `base_facts.sql` 相同：

```
today_date =
  CASE WHEN TO_CHAR(SYSDATE, 'HH24MI') >= '0730' THEN TRUNC(SYSDATE)
       ELSE TRUNC(SYSDATE) - 1
  END
```

- 07:15 呼叫 → `today_date = TRUNC(SYSDATE) - 1`（看前一個生產日）
- 07:30 呼叫 → `today_date = TRUNC(SYSDATE)`（看當天）

**不使用 client-side 日期**，所有時區計算依賴 Oracle DB timezone `+08:00`（已驗證）。

### Record Type 語意（今日模式）

| record_type | 篩選條件 | 說明 |
| :--- | :--- | :--- |
| `on_hold` | `RELEASETXNDATE IS NULL` | 當下仍在 hold 的所有 lot，不限 hold_day |
| `new` | `hold_day = today` | 今日新增 hold |
| `release` | `release_day = today` | 今日 release |

多值可 CSV 組合（OR 邏輯），作用於 reason_pareto、duration、list。

### Summary 卡片說明

| 欄位 | 計算邏輯 |
| :--- | :--- |
| `onHoldTotalCount` | `RELEASETXNDATE IS NULL` 的 CONTAINERID 去重計數（不限 hold_day） |
| `onHoldTotalQty` | 同母集的 QTY 加總 |
| `todayNewQty` | `hold_day = today` 的 QTY 加總 |
| `todayReleaseQty` | `release_day = today` 的 QTY 加總 |
| `todayFutureHoldQty` | `hold_day = today AND FUTUREHOLDCOMMENTS IS NOT NULL` 的 QTY 加總（選項 a：直覺定義） |
| `onHoldAvgHours` | `RELEASETXNDATE IS NULL` 集合的 `AVG(HOLD_HOURS)`（SYSDATE 快照值） |
| `onHoldMaxHours` | 同母集的 `MAX(HOLD_HOURS)` |

Summary 計算在 hold_type 過濾後、record_type 過濾前執行，反映全體當日狀態。

### 資料量上限

後端強制 `FETCH FIRST (HOLD_TODAY_MAX_SNAPSHOT_ROWS + 1) ROWS ONLY`（預設 10001），若超量：
- 回傳截斷後的 10000 筆資料
- 回應中附加 `_meta: { truncated: true, total_before_limit: N, limit_applied: 10000 }`
- 前端應顯示警示

### Auto-refresh

前端計時器每 `HOLD_TODAY_AUTO_REFRESH_SECONDS`（預設 60 秒）自動重打 today-snapshot API：
- 頁面 hidden（`visibilityState === 'hidden'`）時暫停
- 切回 visible 時立即補打一次再恢復計時
- 失敗時保留上次快照並顯示 stale indicator

### 快取

- namespace：`hold_today:*`
- TTL：`HOLD_TODAY_CACHE_TTL_SECONDS`（預設 60 秒）
- 多人同時段打同一 hold_type+filter 組合共享同一快取鍵
- DB 不可用（circuit open / pool exhausted）且快取為空時回傳 HTTP 503 `service_unavailable`
