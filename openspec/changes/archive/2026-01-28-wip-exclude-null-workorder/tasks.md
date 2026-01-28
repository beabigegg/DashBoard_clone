# Implementation Tasks

## Phase 1: Backend 修改

### wip_service.py

- [x] 在 `_build_base_conditions()` 函數開頭新增 `WORKORDER IS NOT NULL` 條件

---

## Phase 2: 驗證

- [x] 手動測試：WIP Overview 頁面載入正常
- [x] 手動測試：WIP Detail 頁面載入正常
- [x] 確認：NULL WORKORDER 的 Lot 不再顯示於統計中
