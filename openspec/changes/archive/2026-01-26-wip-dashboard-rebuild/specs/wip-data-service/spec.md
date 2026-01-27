## ADDED Requirements

### Requirement: 資料來源

系統 SHALL 使用 `DWH.DW_PJ_LOT_V` View 作為 WIP 資料的唯一來源。

#### Scenario: 查詢資料
- **WHEN** 任何 WIP API 被呼叫
- **THEN** 系統從 `DWH.DW_PJ_LOT_V` 查詢資料（含 schema prefix）

### Requirement: Overview Summary API

系統 SHALL 提供 `GET /api/wip/overview/summary` API 回傳 KPI 摘要。

#### Scenario: 取得 KPI 摘要
- **WHEN** 呼叫 `GET /api/wip/overview/summary`
- **THEN** 系統回傳 JSON：
  ```json
  {
    "success": true,
    "data": {
      "total_lots": 9073,
      "total_qty": 858878718,
      "hold_lots": 120,
      "hold_qty": 8213395,
      "sys_date": "2026-01-26 19:18:29"
    }
  }
  ```

### Requirement: Overview Matrix API

系統 SHALL 提供 `GET /api/wip/overview/matrix` API 回傳工站×產品線矩陣。

#### Scenario: 取得矩陣資料
- **WHEN** 呼叫 `GET /api/wip/overview/matrix`
- **THEN** 系統回傳 JSON：
  ```json
  {
    "success": true,
    "data": {
      "workcenters": ["切割", "焊接_DB", ...],
      "packages": ["SOT-23", "SOD-323", ...],
      "matrix": {
        "切割": {"SOT-23": 50200000, "SOD-323": 42100000, ...},
        ...
      },
      "workcenter_totals": {"切割": 234334583, ...},
      "package_totals": {"SOT-23": 172340257, ...},
      "grand_total": 858878718
    }
  }
  ```
- **AND** workcenters 依 WORKCENTERSEQUENCE_GROUP 排序
- **AND** packages 依 total QTY 降序排序

### Requirement: Overview Hold API

系統 SHALL 提供 `GET /api/wip/overview/hold` API 回傳 Hold 摘要。

#### Scenario: 取得 Hold 摘要
- **WHEN** 呼叫 `GET /api/wip/overview/hold`
- **THEN** 系統回傳 JSON：
  ```json
  {
    "success": true,
    "data": {
      "items": [
        {"reason": "特殊需求管控", "lots": 44, "qty": 4235060},
        {"reason": "YieldLimit", "lots": 21, "qty": 1084443},
        ...
      ]
    }
  }
  ```
- **AND** 依 lots 數量降序排序

### Requirement: Detail API

系統 SHALL 提供 `GET /api/wip/detail/{workcenter}` API 回傳工站細部資料。

#### Scenario: 取得工站細部資料
- **WHEN** 呼叫 `GET /api/wip/detail/焊接_DB?package=&status=&page=1&page_size=100`
- **THEN** 系統回傳 JSON：
  ```json
  {
    "success": true,
    "data": {
      "workcenter": "焊接_DB",
      "summary": {
        "total_lots": 859,
        "on_equipment_lots": 312,
        "waiting_lots": 547,
        "hold_lots": 15
      },
      "specs": ["Spec1", "Spec2", ...],
      "lots": [
        {
          "lot_id": "GA25102485-A00-004",
          "equipment": "GSMP-0054",
          "status": "ACTIVE",
          "hold_reason": null,
          "qty": 750,
          "package": "SOT-23",
          "spec": "鈦昇"
        },
        ...
      ],
      "pagination": {
        "page": 1,
        "page_size": 100,
        "total_count": 859,
        "total_pages": 9
      },
      "sys_date": "2026-01-26 19:18:29"
    }
  }
  ```
- **AND** specs 依 SPECSEQUENCE 排序
- **AND** lots 依 LOTID 排序
- **AND** 前端將 qty 顯示在對應的 spec 欄位中（非獨立欄位）

#### Scenario: 篩選 Package
- **WHEN** 呼叫 `GET /api/wip/detail/焊接_DB?package=SOT-23`
- **THEN** 系統只回傳 PRODUCTLINENAME = 'SOT-23' 的 Lots

#### Scenario: 篩選 Status
- **WHEN** 呼叫 `GET /api/wip/detail/焊接_DB?status=HOLD`
- **THEN** 系統只回傳 STATUS = 'HOLD' 的 Lots

### Requirement: Workcenters Meta API

系統 SHALL 提供 `GET /api/wip/meta/workcenters` API 回傳工站列表。

#### Scenario: 取得工站列表
- **WHEN** 呼叫 `GET /api/wip/meta/workcenters`
- **THEN** 系統回傳 JSON：
  ```json
  {
    "success": true,
    "data": [
      {"name": "切割", "lot_count": 1377},
      {"name": "焊接_DB", "lot_count": 859},
      ...
    ]
  }
  ```
- **AND** 依 WORKCENTERSEQUENCE_GROUP 排序

### Requirement: Packages Meta API

系統 SHALL 提供 `GET /api/wip/meta/packages` API 回傳 Package 列表。

#### Scenario: 取得 Package 列表
- **WHEN** 呼叫 `GET /api/wip/meta/packages`
- **THEN** 系統回傳 JSON：
  ```json
  {
    "success": true,
    "data": [
      {"name": "SOT-23", "lot_count": 2234},
      {"name": "SOD-323", "lot_count": 1392},
      ...
    ]
  }
  ```
- **AND** 依 lot_count 降序排序
