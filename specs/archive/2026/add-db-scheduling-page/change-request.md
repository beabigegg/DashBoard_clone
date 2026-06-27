# Change Request

## Original Request

新增「生產輔助」抽屜與「DB生產排程助手」頁面：從D/B-START站依WORKFLOWNAME找對應製程站設備，BOP第一碼做fallback，按PACKAGE_LEF→PJ_TYPE→WAFERLOT→UTS排序輸出推薦清單

## Business / User Goal

工廠排程員需要一個頁面，快速查看目前在 D/B-START 等待的 lot 應該分配到哪台設備。
規則：
1. 找 SPECNAME='D/B-START' 的 lot
2. 用相同 WORKFLOWNAME 找封裝站（DB 製程 SPEC）中 STATUS='ACTIVE' 且有設備的 lot → 取得推薦設備
3. 若無匹配，用 BOP 第一碼 fallback：U→Eutectic/1DB/2DB群，E→Epoxy D/B，P→Solder/DBCB/錫膏網印群
4. 按 PACKAGE_LEF → PJ_TYPE → WAFERLOT → UTS 優先順序排序
5. 一個 lot 可對應多台設備（全部列出）

## Non-goals

- DW 站排程（先只做 DB）
- 設備手動指派或寫回 MES
- 需求超過即時 WIP 快取的歷史分析

## Constraints

- 資料來源：DWH.DW_MES_LOT_V（現有 WIP 快取，5 分鐘更新）
- 頁面唯讀，不寫回任何系統
- 使用現有 portal-shell 架構新增抽屜與頁面

## Known Context

- DWH.DW_MES_LOT_V 欄位：SPECNAME, WORKFLOWNAME, BOP, PACKAGE_LEF, PJ_TYPE, WAFERLOT, UTS, QTY, EQUIPMENTS, STATUS
- DB 製程 SPEC 清單：1DB, 1DB1WB, 1DB2WB, 2DB, 2DB1WB, 2DB2WB, DBCB, Epoxy D/B, Eutectic D/B, Eutectic D/B-雙晶, Solder Paste D/B+E-Clip, 錫膏網印
- 目前 D/B-START 約 689 lots，93.5% 可由 WORKFLOWNAME 直接找到設備
- STATUS 值為 'ACTIVE'（非 'RUN'）

## Open Questions

無

## Requested Delivery Date / Priority

高優先
