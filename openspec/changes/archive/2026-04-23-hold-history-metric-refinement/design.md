## Context

Hold History 頁面的指標層累積了三個獨立但互相關聯的問題（詳見 proposal.md）。本次變更在指標層一次處理完，讓後續 UX 大改（today mode）可以建立在穩定可信的指標基礎上。

### 已驗證的前提
- Oracle DB timezone = `+08:00`（DBTIMEZONE / SESSIONTIMEZONE / SYSTIMESTAMP 皆為 +08:00），`SYSDATE` 回傳台灣時間，`HOLD_HOURS` 計算可信
- `HOLD_HOURS` 在 `base_facts.sql` 已為每筆 lot 計算完成：released 用 `(RELEASETXNDATE - HOLDTXNDATE) * 24`（精確到秒），on-hold 用 `(SYSDATE - HOLDTXNDATE) * 24`（spool 建立當下快照）
- 現行 `FUTURE_HOLD_FLAG` 邏輯與 PJMES043 原廠 SQL（`docs/hold_history.md` 2026-02-10 提交）完全等價
- Excel 對比差異源自資料時序（release 清除 FUTUREHOLDCOMMENTS），不是程式 bug
- `RN_FUTURE_REASON`（= 原廠 `RN_CONHOLD`）已在 `base_facts.sql` 計算且寫入 Parquet spool，可直接用於新指標

## Goals / Non-Goals

**Goals:**
- 以真實 `AVG(HOLD_HOURS)` / `MAX(HOLD_HOURS)` 取代 bucket 加權估算
- 以「已解除」vs「持續中」兩組卡片分離語意，沿用既有 `HOLD_HOURS` 的雙重定義（不引入新的時間計算邏輯）
- 新增「品質重複觸發」穩定指標，補足 Future Hold 卡時效衰減的盲點
- 保留 Future Hold 卡片但加上 tooltip，讓使用者理解衰減特性
- Server Oracle SQL / Server DuckDB SQL runtime / Client DuckDB-WASM 三路徑運算結果一致

**Non-Goals:**
- 不動模式切換 / 當日快照 / 篩選條件（屬 `hold-history-today-mode`）
- 不動 Duration bucket 分佈圖、Trend 既有指標、Reason Pareto、Detail List
- 不動 `FUTUREHOLDCOMMENTS` 的填寫或清除邏輯（那是 MES 端業務流程）
- 不追求與 PJMES043 某一次 Excel 快照 100% 一致——對齊的是「原廠 SQL 邏輯」，不是「快照瞬時值」

## Decisions

### Decision 1: AVG/MAX 以 duration API 回傳承載，而非另開 summary API

**選擇**：duration payload 擴充 `{ items, avgReleasedHours, avgOnHoldHours, maxReleasedHours, maxOnHoldHours }`

**替代方案**：新開 `/api/hold-history/summary` API

**理由**：
- Duration 已套用 hold_type / record_type / reason 等篩選，AVG/MAX 要套用同組 filter 才符合語意
- 新增欄位為 additive，前端未更新者忽略即可
- 省一次網路往返與 cache 鍵管理

### Decision 2: 「持續 Hold 均值」直接用 spool 中 `HOLD_HOURS` 快照，不即時重算

**選擇**：`AVG(HOLD_HOURS) WHERE RELEASETXNDATE IS NULL`（spool 建立當下的 SYSDATE 決定值）

**替代方案**：client/server 即時 `(NOW - HOLDTXNDATE)` 重算

**理由**：
- Spool TTL 15 分鐘 → 誤差上限 15 分鐘，對「平均時長」語意可接受
- Client 用瀏覽器時間會與 server 不一致；server 即時重算需要跳過 spool，架構成本高
- 當日模式（`hold-history-today-mode`）會另建立獨立的即時 API，需要即時值的場景由那裡提供

### Decision 3: 「品質重複觸發」指標放在 trend.sql，不放 duration.sql

**選擇**：trend.sql 逐日計算 `repeat_quality_hold_qty`，卡片讀取 trend summary 累加值

**替代方案**：duration.sql 計算單一累計值

**理由**：
- 重複觸發是「事件發生」類指標（和 `newHoldQty` / `releaseQty` 同類），放 trend 讓使用者能看到每日趨勢
- Summary 卡片的值可由 trend 各日累加，和其他「累計」卡片（累計新增 / 累計 Release）一致
- 未來若要加「每日品質重複觸發折線」可直接復用，不用改 API

### Decision 4: 「品質重複觸發」= `RN_FUTURE_REASON > 1 AND hold_type='quality'`，不加 `FUTUREHOLDCOMMENTS` 條件

**選擇**：純歷史重複 + quality filter，不看備註

**替代方案**：照 PJMES043 原廠「`FUTUREHOLD_FLAG = 0`」（需要 FUTUREHOLDCOMMENTS IS NOT NULL）

**理由**：
- 業務目的是監控「品質異常再次發生」，和備註是否填寫無關
- 備註會被 MES 清除，導致指標衰減；歷史 `RN_FUTURE_REASON` 是**只增不減**的穩定值
- Future Hold 卡片仍保留原邏輯（對齊 PJMES043），兩指標並存、語意互補
- `hold_type='quality'` 沿用既有分類（`CommonFilters.get_non_quality_reasons_sql()` 的補集）

### Decision 5: SummaryCards 從 7 格擴充為 10 格

**選擇**：`:columns="10"`

**替代方案**：保留 7 格，某些資訊改用下拉切換

**理由**：
- 10 張卡片在 1920 寬螢幕可呈現；窄螢幕依 `SummaryCardGroup` 既有 grid 自動換行
- 多指標並列比對才能看出「已解除 vs 持續中」「新增 vs 品質重複」的差異
- Dashboard 語意就是「一眼看完」，不應為了排版隱藏指標

**卡片順序（從左至右）：**
1. On Hold 數量
2. 最末日新增 Hold
3. 累計新增 Hold
4. 累計 Release
5. 累計 Future Hold（保留 + tooltip）
6. 品質重複觸發（新）
7. 累計淨變動
8. 已解除平均時長（新）
9. 持續 Hold 平均時長（新）
10. 已解除最長時長 / 持續 Hold 最長時長（新，兩張或合併成一張卡用子標籤切換——待 UI 實作決定）

> 若最長時長合併為一張（左半 released、右半 on-hold），SummaryCardGroup 就是 9 格。最終數量由 UX 實作時決定，spec 只約束兩組值必須可見。

### Decision 6: Future Hold tooltip 文案

**選擇（預設）**：
> 「當下仍標記為 Future Hold 的總量。此指標依 PJMES043 原廠邏輯（同工單同原因的重複 Hold 且有 Future Hold 備註）計算。lot release 後 MES 可能清除備註，導致歷史日期的數值隨時間衰減。若需穩定指標請參考『品質重複觸發』。」

**替代方案**：`?` 圖示點開彈窗（資訊更完整）

**理由**：hover tooltip 成本最低；若文案過長會考慮改 popover

## Risks / Trade-offs

| Risk | Mitigation |
| :--- | :--- |
| 「持續 Hold 均值」在 spool TTL 內不更新（最多 15 分鐘漂移） | 可接受；卡片副標可加「截至查詢當下」 |
| 10 格在 < 1366px 螢幕換行，視覺密度上升 | `SummaryCardGroup` 已有 grid 降級；實測後若不夠再加 breakpoint |
| 前後端運算結果不一致（DuckDB WASM vs Oracle vs DuckDB server） | `test_frontend_hold_history_parity.py` 擴充 AVG/MAX/repeat 三路徑 parity（誤差 < 0.01hr / 整數全等） |
| 舊 cache 中無新欄位導致前端渲染空值 | 部署時 bump spool namespace 強制重建；前端預設值 0，不會崩潰 |
| 「品質重複觸發」定義和業務方原本認知不同 | Tooltip 清楚說明；先和 Peeler（PJMES043 作者）核對一次 |
| `RN_FUTURE_REASON` 的 partition 只看 spool 時間範圍，跨區間的先前 Hold 會被誤判為「首次」 | 這是既有行為（PJMES043 原廠也是）；本次不改，未來若要全歷史 partition 另議 |
| 卡片數量增加可能影響既有 E2E 測試斷言 | 更新 `test_hold_history_e2e.py` 卡片總數與文字斷言 |

## Migration Plan

1. **後端先行**：duration.sql / trend.sql / service / runtime 擴充欄位（additive，舊 client 忽略新欄位無影響）
2. **前端跟進**：同次 PR 更新 DuckDB composable、SummaryCards、App.vue、shared-ui SummaryCard tooltip 支援
3. **Parity 測試**：確保三路徑一致，新增測試綠燈才 merge
4. **部署**：單次部署同版本前後端

**Rollback**：前端 revert 可恢復舊 7 格 + bucket 估算；後端新欄位為 additive，無破壞性。

## Open Questions

- **卡片文案**：「已解除平均時長」vs「已 Release 均值」vs「完成 Hold 均值」——UI 實作時對齊既有 i18n 風格
- **最長時長 UI**：兩張獨立卡 vs 一張卡左右分區——等 UI review
- **空集合處理**：若某組均值分母為 0，顯示 `0` 還是 `—`？建議 `—` 但要和 `SummaryCard` 元件約定格式
- **tooltip 視覺**：確認 `SummaryCard.vue` 需不需要新增 `tooltip` prop，或用 shared-ui 既有 Popover
