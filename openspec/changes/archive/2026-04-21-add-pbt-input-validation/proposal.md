## Why

現有 fuzz 測試 (`tests/routes/test_fuzz_routes.py`) 採列舉式硬編碼樣本，覆蓋輸入空間有限，難以系統性地探索邊界（unicode、極長字串、整數溢位、異常組合）。對於 `core/request_validation.py`、URL state parser、查詢過濾器組合與分頁參數等「輸入空間大、純函式」的程式碼，property-based testing (PBT) 可在不增加多少維護成本下顯著提升輸入面安全性，補足列舉式 fuzz 漏掉的角落。

## What Changes

- 新增 `hypothesis` 至開發依賴（`environment.yml` / `requirements-dev.txt`）
- 新增 `tests/property/` 目錄，集中存放 PBT 測試
- 對下列模組撰寫 property tests：
  - `core/request_validation.py`：任意輸入不得 raise 未預期例外、合法輸入 round-trip 一致
  - URL state encode/decode（query-tool 等頁面的 query string serialization）
  - 查詢過濾器組合（filter normalization 不得改變語意子集關係）
  - 分頁 / 排序參數邊界（負數、超大值、零值都應安全降級）
- pytest 整合：`pytest -m property` marker 與 CI 配置
- 不改動現有列舉式 fuzz 測試（保留作為已知攻擊樣本回歸）

## Capabilities

### New Capabilities
- `property-based-test-coverage`: 規範 PBT 測試的範圍、目標模組、屬性類型、執行與 CI 整合策略

### Modified Capabilities
（無——新增測試類型不修改現有 spec 的需求）

## Impact

- **依賴**：新增 `hypothesis` 開發依賴
- **測試**：新增 `tests/property/` 目錄與相關測試檔
- **CI**：`pytest` 收集需包含新目錄；CI workflow 執行時間預估 +30-60s
- **不影響**：production 程式碼、API 契約、前端
