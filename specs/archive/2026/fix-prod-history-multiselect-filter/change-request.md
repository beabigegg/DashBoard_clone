# Change Request

## Original Request

> Bug 現象：Production History 頁面的「第一階 filter」（type / package / bop / function 共四個）有提供多選 & cross-filter 功能。但目前的情況是：使用者只要在任何一個 filter 內勾選一個 item，filter 就會立刻生效（觸發資料重查/cross-filter 立刻收斂），導致實際上多選功能無法使用（無法在一次互動內勾多個值）。

使用者補充：
- 一階 filter 共四個：**type / package / bop / function**
- 每個 filter 都要支援正常的多選
- 當 A filter 多選設定完成後，cross-filter 應該影響到其他 filter 的可選範圍
- 其他 filter 同樣支援多選

## Business / User Goal

讓 Production History 的一階 filter 多選與 cross-filter 真正可用：工程師能在「同一個 filter dropdown 內勾選多個值」，並在套用後讓其他三個 filter 的選項依勾選結果動態收斂；接著在下一個 filter 同樣多選，整體查詢只在使用者完成意圖（關閉 dropdown）後才觸發。

## Non-goals

- 不變更 filter 的視覺呈現（仍是 dropdown + checkbox 形式），除非為了修正 bug 所必需。
- 不變更後端 API 介面或 SQL 行為。
- 不新增第二階（二階）以下的 filter 結構；本次只處理一階四個 filter。
- 不重做 cross-filter 的 server-side 計算邏輯，只修正「何時送出 cross-filter 請求」的時機。

## Constraints

- Apply trigger 採「dropdown 關閉時（blur / 點外面）」，不新增 Apply 按鈕。
- 多選期間不可觸發 cross-filter 重算或主查詢。
- 必須在所有四個一階 filter 上都呈現一致的多選行為。

## Known Context

- 頁面：Production History（生產歷史，前端 feature app，路由含 production-history）。
- 一階 filter 欄位：type, package, bop, function（屬於 Oracle MES 數據維度）。
- 既有 cross-filter 邏輯：選擇 A filter 的值會收斂 B/C/D 的可選清單。
- 同類多選元件可能在其他報表頁（如 wip, hold-history）已存在，可參考；但本次只修 production-history。

## Open Questions

- 目前 filter dropdown 是「選一個就 emit」還是「change 立刻 emit」？需在 spec 階段確認元件內部觸發點，找出真正關鍵的 emit 來源。
- 既有元件是否已有 v-model:open / visible state 可掛 dropdown 關閉事件？若無需要新增。

## Requested Delivery Date / Priority

優先級：使用者體驗 bug，影響日常查詢效率。無硬性日期；以下一個發布窗為目標。
