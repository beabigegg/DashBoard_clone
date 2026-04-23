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
