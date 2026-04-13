## ADDED Requirements

### Requirement: LogsTab SHALL be the single entry point for log viewing and persistent storage management
The Logs tab SHALL host all log-related views and cleanup actions in the admin dashboard, covering structured logs (SQLite + MySQL), SQLite databases under `logs/*.sqlite`, `.log` files under `logs/`, and rotated files under `logs/archive/`.

#### Scenario: Structured log section
- **WHEN** the user opens the Logs tab
- **THEN** the page SHALL render a "系統日誌" SectionCard that lists merged SQLite + MySQL log rows with level filter, search box, pagination, and a "清理日誌" button calling `POST /admin/api/logs/cleanup`

#### Scenario: SQLite databases section
- **WHEN** the user opens the Logs tab and `storage_info.sqlite_files` is non-empty
- **THEN** the page SHALL render a "SQLite 資料庫" SectionCard listing each sqlite file's path and size
- **AND** the row whose path includes `metrics_history` SHALL expose a "清除快照" button calling `POST /admin/api/performance-history/purge`

#### Scenario: Log files section
- **WHEN** the user opens the Logs tab and `storage_info.log_files` is non-empty
- **THEN** the page SHALL render a "Log 檔案" SectionCard listing each file's path and size
- **AND** SHALL provide a "清空 Log 檔案" button that calls `POST /admin/api/log-files/cleanup` with `{ "targets": ["logs"] }`

#### Scenario: Archive files section
- **WHEN** the user opens the Logs tab and `storage_info.archive_files` is non-empty
- **THEN** the page SHALL render an "Archive 歷史檔" SectionCard listing each archived file's path and size
- **AND** SHALL provide a "清空 Archive" button that calls `POST /admin/api/log-files/cleanup` with `{ "targets": ["archive"] }`

### Requirement: WorkerTab SHALL NOT manage any persistent storage
The Worker tab SHALL NOT display `.log` file listings, archive file listings, SQLite database listings, or any cleanup/purge buttons for storage under `logs/`. All persistent storage management SHALL live in the Logs tab.

#### Scenario: Worker tab no longer lists storage
- **WHEN** the user opens the Worker tab
- **THEN** no `Log 檔案`, `Archive`, `效能快照儲存`, or `SQLite` DataTable SHALL be rendered
- **AND** no "清空 Log 檔案", "清空 Archive", "清除快照", or "全部清理" button SHALL be present

### Requirement: Backend log API SHALL serialize timestamps as UTC ISO 8601
All `timestamp` fields returned by `GET /admin/api/logs` (from both SQLite and MySQL sources) SHALL be ISO 8601 strings with explicit `+00:00` UTC offset, regardless of original storage format.

#### Scenario: SQLite-sourced row carries UTC offset
- **WHEN** a log row was written by `core/log_store.write_log()` after this change ships
- **THEN** the `timestamp` SHALL match the regex `^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(\.\d+)?\+00:00$`

#### Scenario: Legacy naive SQLite row is normalized on read
- **WHEN** a pre-existing log row in `admin_logs.sqlite` has a naive ISO timestamp without timezone info
- **THEN** `GET /admin/api/logs` SHALL interpret it as the server's local timezone, convert it to UTC, and return it with `+00:00` suffix
- **AND** the original row in SQLite SHALL NOT be rewritten

#### Scenario: MySQL-sourced row is normalized
- **WHEN** a row from `dashboard_logs` is included in the merged response
- **THEN** its `timestamp` SHALL be returned as the same `+00:00` ISO 8601 format as SQLite rows

### Requirement: Backend log API SHALL sort merged rows by parsed datetime
`GET /admin/api/logs` SHALL sort merged SQLite + MySQL rows by parsing each `timestamp` into a `datetime` object before comparison, producing a strictly time-descending order even when the two sources had different stored string formats.

#### Scenario: Same-minute rows from both sources interleave correctly
- **GIVEN** a SQLite row at `2026-04-13T03:48:30+00:00` and a MySQL row at `2026-04-13T03:48:45+00:00`
- **WHEN** `GET /admin/api/logs` returns the merged page
- **THEN** the MySQL row SHALL appear before the SQLite row in the response

#### Scenario: Unparseable timestamps fall to the bottom
- **WHEN** a row's timestamp cannot be parsed by `datetime.fromisoformat`
- **THEN** it SHALL be ordered after all parseable rows rather than crashing the endpoint

### Requirement: Frontend SHALL use a shared formatter for log timestamps
The admin dashboard frontend SHALL provide a single shared utility `formatLogTime(iso)` exported from `frontend/src/core/datetime.js`, and LogsTab and WorkerTab SHALL both use it for any timestamp originating from the log/worker APIs.

#### Scenario: LogsTab uses shared formatter
- **WHEN** LogsTab renders a row from `GET /admin/api/logs`
- **THEN** the `timestamp` cell SHALL display the result of `formatLogTime(row.timestamp)`
- **AND** the displayed format SHALL be `YYYY/MM/DD HH:mm:ss` in the user's local timezone using `zh-TW` locale and 24-hour clock

#### Scenario: WorkerTab uses shared formatter for start time
- **WHEN** WorkerTab renders the worker start time card
- **THEN** the value SHALL be `formatLogTime(workerData.worker_start_time)` instead of an inline `toLocaleString` call

#### Scenario: Invalid input falls back gracefully
- **WHEN** `formatLogTime` is called with `null`, `undefined`, or a non-parseable string
- **THEN** it SHALL return `'-'` (or the original input if non-empty) without throwing
