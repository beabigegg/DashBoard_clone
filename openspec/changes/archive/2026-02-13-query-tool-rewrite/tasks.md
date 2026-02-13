## 1. App Shell + Tab Layout

- [x] 1.1 Rewrite `App.vue` as tab shell with "LOT 追蹤" and "設備查詢" top-level tabs using Tailwind (gradient header, tab buttons, active indicator)
- [x] 1.2 Implement URL `?tab=lot|equipment` sync — persist and restore active tab on page load
- [x] 1.3 Rewrite `main.js` to minimal Vite entry point (createApp + mount, ~5 lines)
- [x] 1.4 Delete `style.css` — all styling via Tailwind from this point forward

## 2. QueryBar + Resolve

- [x] 2.1 Create `QueryBar.vue` — input type selector (lot_id/serial_number/work_order), multi-line textarea, resolve button, Tailwind styling consistent with other pages' FilterToolbar patterns
- [x] 2.2 Create `useLotResolve.js` composable — input parsing (split by newline/comma), validation (empty check, max limits), `POST /api/query-tool/resolve` call, reactive state (`resolvedLots`, `notFound`, `loading.resolving`, `errorMessage`)
- [x] 2.3 Wire QueryBar into `LotTraceView.vue` — resolve results feed into the lineage tree below

## 3. Lineage Tree with Progressive Growth

- [x] 3.1 Create `useLotLineage.js` composable — auto-fire lineage calls after resolve, concurrency limiter (max 3 concurrent), per-lot reactive cache (`lineageMap: Map<containerId, {ancestors, merges, loading, error}>`), expand/collapse state (`expandedNodes: Set`), cache clearing on new resolve, 429 backoff handling
- [x] 3.2 Create `LineageNode.vue` recursive component — displays node label (container name, lot type icon for merge 🔀), expand/collapse toggle for non-leaf nodes, emits `select` event on click, highlight for selected node
- [x] 3.3 Create `LineageTree.vue` — renders resolved lots as root nodes, wraps children in `<TransitionGroup>` for growth animation, "全部展開" / "收合" buttons, not-found warnings below tree
- [x] 3.4 Implement CSS transitions for tree growth — `translateX(-16px)→0` + `opacity 0→1` enter transition, 30-50ms stagger via `transition-delay` on siblings, root nodes fade-in on resolve

## 4. Left-Right Master-Detail Layout

- [x] 4.1 Create `LotTraceView.vue` — left-right split layout (left panel ~280-300px for lineage tree, right panel fills remaining), responsive stacking below 1024px
- [x] 4.2 Create `LotDetail.vue` — right panel container with sub-tab bar (歷程, 物料, 退貨, Hold, Split, Job), active tab indicator, on-demand data loading when tab activated, contextual error display
- [x] 4.3 Wire tree node selection → right panel detail loading — clicking any node in LineageTree sets `selectedContainerId` and triggers active sub-tab data fetch

## 5. LOT Detail Sub-tabs

- [x] 5.1 Create `useLotDetail.js` composable — manages `activeSubTab`, per-tab data cache (invalidated on lot change), `GET /api/query-tool/lot-history` with workcenter group filter, `GET /api/query-tool/lot-associations?type=X` for each association type, loading/error state per sub-tab
- [x] 5.2 Create `LotHistoryTable.vue` — production history table with sticky headers, workcenter group MultiSelect filter, dynamic columns, horizontal scroll
- [x] 5.3 Create `LotAssociationTable.vue` — shared table component for materials/rejects/holds/splits/jobs, dynamic columns from response, empty state message
- [x] 5.4 Add per-sub-tab `ExportButton.vue` — calls `POST /api/query-tool/export-csv` with appropriate `export_type` and `container_id`, disabled when no data, download blob as CSV

## 6. TimelineChart Shared Component

- [x] 6.1 Create `TimelineChart.vue` — props interface (`tracks`, `events`, `timeRange`, `colorMap`), SVG rendering with horizontal time axis, auto-scaled ticks (hour/day granularity), sticky left track labels
- [x] 6.2 Implement multi-layer bar rendering — background layer behind foreground layer per track, proportional positioning from time range, color from colorMap
- [x] 6.3 Implement event markers — diamond/triangle SVG icons at time positions, hover tooltip with event label and detail
- [x] 6.4 Implement horizontal scroll container — overflow-x scroll wrapper, sticky label column, responsive width

## 7. LOT Production Timeline

- [x] 7.1 Create `LotTimeline.vue` — maps lot-history rows to TimelineChart tracks (one track per WORKCENTERNAME, bars from TRACKINTIMESTAMP to TRACKOUTTIMESTAMP), respects workcenter group filter
- [x] 7.2 Overlay hold/material event markers on timeline — fetches hold events and material consumption events, renders as markers on corresponding time positions
- [x] 7.3 Integrate into History sub-tab — timeline renders above or alongside the history table, shares the workcenter filter state

## 8. Equipment Tab

- [x] 8.1 Create `EquipmentView.vue` — filter bar (MultiSelect for equipment, date range inputs, query button), sub-tab bar (生產紀錄, 維修紀錄, 報廢紀錄, Timeline), shared filter state across sub-tabs
- [x] 8.2 Create `useEquipmentQuery.js` composable — equipment list bootstrap from `GET /api/query-tool/equipment-list`, date range default (last 30 days), `POST /api/query-tool/equipment-period` calls per query type, loading/error per sub-tab, URL state sync for equipment_ids + dates
- [x] 8.3 Create `EquipmentLotsTable.vue` — production lots table (CONTAINERID, SPECNAME, TRACK_IN/OUT, QTY, EQUIPMENTNAME), sticky headers, export button
- [x] 8.4 Create `EquipmentJobsPanel.vue` — maintenance job table (JOBID, STATUS, CAUSECODENAME, REPAIRCODENAME, SYMPTOMCODENAME, dates), expandable row detail (employee names, secondary codes, CONTAINERNAMES), export button
- [x] 8.5 Create `EquipmentRejectsTable.vue` — scrap records table (EQUIPMENTNAME, LOSSREASONNAME, TOTAL_REJECT_QTY, TOTAL_DEFECT_QTY, AFFECTED_LOT_COUNT), export button

## 9. Equipment Timeline

- [x] 9.1 Create `EquipmentTimeline.vue` — composes 3 data sources (status_hours + lots + jobs) into TimelineChart tracks, fires 3 API calls in parallel, one track per equipment
- [x] 9.2 Map status data to background layer bars — PRD=green, SBY=amber, UDT=red, SDT=blue-gray
- [x] 9.3 Map lot data to foreground layer bars — lot processing bars from track-in to track-out
- [x] 9.4 Map maintenance jobs to event markers — JOBID + CAUSECODENAME as label, tooltip with full detail

## 10. Polish + Cleanup

- [x] 10.1 Full URL state sync — all filter values (tab, input_type, container_id, workcenter_groups, equipment_ids, dates, sub-tabs) persisted to URL and restored on page load via `useQueryState` or custom sync
- [x] 10.2 Responsive layout testing — verify left-right split stacks correctly below 1024px, tab layout works on mobile, timeline horizontal scroll works on touch
- [x] 10.3 Delete dead code — remove old monolithic `useQueryToolData.js`, verify no imports reference deleted files
- [x] 10.4 Visual consistency audit — verify gradient header, button styles, table styles, card borders match other modernized pages (wip-detail, hold-detail, mid-section-defect)
