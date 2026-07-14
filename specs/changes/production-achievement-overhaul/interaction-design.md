---
change-id: production-achievement-overhaul
schema-version: 0.1.0
last-changed: 2026-07-14
---

# Interaction Design: production-achievement-overhaul

## Provenance

Citations below follow the ADR 0012 §2 five-form grammar strictly (endpoint+field / enum-pin / errors-status / implicit-status / `data-shape: <condition>`, written as plain text with no surrounding backticks or trailing parenthetical); per-field/sub-column detail that a form cannot express is carried in each row's own `rationale`/`meaning` text instead, never appended to the citation cell.

- **G1 (resolved via OD-8).** WorkcenterMergeMappingPanel's "full raw list with include/exclude toggle" needed to enumerate the ~15 *currently-excluded* raw groups so an admin can switch one on, but no endpoint exposed the raw station-group universe. Resolved by adding `GET /api/production-achievement/known-workcenter-groups`, mirroring the existing `GET /known-package-lf-values` pattern — see `## Confirmed` OD-8.
- **G2 (resolved via OD-9/OD-10).** All three settings GETs (`package-lf-map`, `workcenter-merge-map`, `daily-plans`) degrade to an HTTP 200 empty array when `MYSQL_OPS_ENABLED=false` (§3.30/§3.31/§3.32), and the report's `workcenter_merge_map`-empty case collapses the *entire* report to an empty table via the D2 INNER JOIN (§3.31) — no read-time discriminator exists for "config store down" vs "genuinely empty" in either case. The human explicitly decided not to add one — see `## Confirmed` OD-9/OD-10. Consequently the states this file originally drafted as `state-empty-config-down` and `state-settings-read-ambiguous` are not present below: they described a distinction the product decided not to surface. Their observable behavior is identical to `state-empty-day` / `state-settings-empty-pkg`/`state-settings-empty-plan` respectively, and each of those rows' `meaning` notes this explicitly.
- **G3 (client-only, no backend discriminator by nature — mirrors ADR 0012's own "a pre-request client state has no contract discriminator" precedent).** The following are intentionally not rows in `## Presented Information` / `## States` below, because no citation form can honestly describe a fact the server never observes:
  - *active mode* (當日/前日/當月/自訂區間) — which of the four `ctrl-mode-*` buttons (`## Controls`) is currently selected; pure client UI state, already covered by the Controls table.
  - *state-poll-timeout* — the client gave up waiting past its own `JOB_POLL_TIMEOUT`; the server has no notion of this and keeps running regardless.
  - *state-cancelled* — the user clicked 取消; the best-effort `POST /api/job/{job_id}/abandon` call is a side effect, not what defines this state (the table renders empty locally whether or not that call itself succeeds).
  - *state-settings-editable* — the optimistic default before any write has been attempted; there is no pre-check endpoint by design (D4). It ends the moment `state-settings-readonly` is entered by a first observed 403.

## Screens

| screen | who is here | what they are deciding | what they fear | what would make them abandon | what must not be shown |
|---|---|---|---|---|---|
| report-daily (當日 / 前日) | a line/station engineer monitoring near-real-time output for one station group | is my station on track versus today's / yesterday's daily plan | that a blank or "0" cell means "broken" when it actually means "no output yet" (or vice-versa) | an empty table with no way to tell whether the selected station, a stale cache, or a dead config hid the data | data presented as "live" when it may be up to ~1 hr stale (warm cache, PA-14) without any hint of that bound |
| report-cumulative (當月 / 自訂區間) | a supervisor checking month-to-date or an arbitrary historical range | are we ahead of / behind cumulative plan for this station | mis-reading a trend % that silently averages unequal-plan package groups (the D3 trap) | a headline rate that contradicts the per-package rows below it | a per-day % computed as a mean-of-percentages instead of aggregate-then-divide (PA-13) |
| settings-editable (whitelisted) | a whitelisted engineer/admin correcting mappings or plans | which raw package/station values merge where, and what each daily plan is | making a persistent write that silently distorts the report or that they cannot walk back | not knowing whether a save actually took effect, given the report reflects it only after the next refresh | — |
| settings-readonly (non-whitelisted) | a non-whitelisted engineer trying to understand why the numbers group as they do | nothing to change — only to read the current configuration | mistaking a read-only page for a broken editor | an edit control that looks active but 403s on click | edit affordances that are not unmistakably read-only |

## Presented Information

| item | rationale | provenance |
|---|---|---|
| selected station group (single value) | "which station group is this report scoped to?" — GenericSuccessResponse's workcenter_groups field supplies the option list (data-shape-contract.md); the selected value itself is the user's own choice, not server state | GET /api/production-achievement/filter-options → HTTP 200 |
| PACKAGE_LF group (row label) | "which package type is this row?" — data.package_lf_map's merged_group resolved over the spool PACKAGE_LF column (data-shape §3.28.1) via COALESCE(...,'(未分類)') per PA-09 | GET /api/production-achievement/report → data |
| D班產出 | "how much did the day shift make?" — data.spool_download_url's parquet actual_output_qty where shift_code=D (data-shape §3.28.1) | GET /api/production-achievement/report → data |
| N班產出 | "how much did the night shift make?" — data.spool_download_url's parquet actual_output_qty where shift_code=N (data-shape §3.28.1) | GET /api/production-achievement/report → data |
| 每日產出 (D+N) | "total output for this package today?" — derived D+N sum (PA-12) from data.spool_download_url | GET /api/production-achievement/report → data |
| 每日計畫 | "what was the plan for this package/station?" — data.daily_plan_map's daily_plan_qty | GET /api/production-achievement/report → data |
| 每日達成率 | "did we hit plan?" — derived 產出/計畫 (PA-12) from data.spool_download_url and data.daily_plan_map; "—" when daily_plan_map lacks the key | GET /api/production-achievement/report → data |
| 累計計畫 | "cumulative plan through the elapsed days?" — data.daily_plan_map's daily_plan_qty × elapsed_days (PA-13) | GET /api/production-achievement/report → data |
| 累計產出 | "cumulative output so far?" — SUM data.spool_download_url's actual_output_qty across range (§3.28.1) | GET /api/production-achievement/report → data |
| 累計差異 | "how far ahead/behind?" — derived 累計產出 − 累計計畫 (PA-13) | GET /api/production-achievement/report → data |
| 累計達成率 | "are we on pace?" — derived aggregate-then-divide (PA-13, D3) | GET /api/production-achievement/report → data |
| stacked D%/N% chart (+ y=100 計畫 markLine) | "visual over/under-plan per package (daily) or per day (cumulative)" — derived actual÷plan (PA-12 daily; PA-13 trend, D3 aggregate-then-divide) | GET /api/production-achievement/report → data |
| async job progress (status / pct / elapsed) | "is my query still running, and for how long?" — data.status/data.pct/data.stage are sibling fields on the same response (status enum: pending/running/done/failed) | GET /api/job/{job_id} → data |
| old shift-based target list (TargetEditPanel — unchanged) | "what are the legacy shift-keyed targets?" | GET /api/production-achievement/targets → data |
| package-LF exception rows (raw→merged, updated_at/by) | "which raw package values are merged, by whom, when?" — raw_package_lf / merged_group / updated_at / updated_by, data-shape-contract.md §3.30 | GET /api/production-achievement/package-lf-map → data |
| known-unmapped raw PACKAGE_LF hint list | "which recently-seen raw values still fall back to themselves (merge candidates)?" — package_lf_values minus rows already in the map | GET /api/production-achievement/known-package-lf-values → data.package_lf_values |
| workcenter merge rows (raw→merged, include state) | "which station groups appear in the report, and under what name?" — raw_workcenter_group / merged_workcenter_group, data-shape-contract.md §3.31 | GET /api/production-achievement/workcenter-merge-map → data |
| full raw station-group universe (to include a currently-excluded group) | "which raw groups COULD I switch on that are excluded today?" (OD-8) | GET /api/production-achievement/known-workcenter-groups → data.raw_workcenter_groups |
| daily-plan rows (workcenter, package, qty, updated_at/by) | "what daily plan is set per station/package?" — workcenter_group / package_lf_group / daily_plan_qty / updated_at / updated_by, data-shape-contract.md §3.32 | GET /api/production-achievement/daily-plans → data |
| read-only-mode note (settings) | "am I allowed to edit here?" — client editForbidden flag; flips the moment any write 403s (D4, no pre-check endpoint) | PUT /api/production-achievement/package-lf-map → 403 |

## User Intents

| id | intent | frequency | path |
|---|---|---|---|
| intent-check-today | see today's D/N output vs daily plan for one station group | most requests, all day (default landing) | land → 當日 (auto) → read daily table + chart |
| intent-switch-workcenter | re-scope the whole report to a different station group | very frequent | station single-select → instant client re-filter of the same day's data |
| intent-check-yesterday | review yesterday's finalized D/N numbers (incl. the N-shift tail, PA-15) | daily (morning review) | 前日 → daily table + chart |
| intent-check-month-pace | check month-to-date cumulative pace | regular (supervisors) | 當月 → cumulative table + per-day trend |
| intent-check-custom-range | investigate an arbitrary historical range | occasional | 自訂區間 → pick dates → cumulative table + trend |
| intent-edit-target | edit the legacy shift-based target values (unchanged panel) | occasional | TargetEditPanel inline edit / new row |
| intent-abandon-slow-query | stop waiting on a cold-cache/slow poll and try something narrower | occasional (cold cache only) | 取消 on the progress card |
| intent-open-settings | go configure the mapping/plan tables | rare | 設定 button → settings route |
| intent-set-daily-plan | set/update daily plan qty per (station, package) | periodic (planning cycle) | settings → DailyPlanPanel edit / new row |
| intent-correct-package-lf | merge a newly-appeared raw PACKAGE_LF value into an existing group | rare (when a new raw value shows up) | settings → PackageLfMappingPanel edit/add/delete |
| intent-manage-workcenter-merge | include/exclude/rename a station group in the report | very rare (setup + occasional) | settings → WorkcenterMergeMappingPanel toggle/name |
| intent-review-settings-readonly | (non-whitelisted) read the config to understand the numbers | occasional | settings route → read-only tables |

## Controls

| id | control | intent |
|---|---|---|
| ctrl-mode-today | 當日 mode button | intent-check-today |
| ctrl-mode-yesterday | 前日 mode button | intent-check-yesterday |
| ctrl-mode-month | 當月 mode button | intent-check-month-pace |
| ctrl-mode-range | 自訂區間 mode button | intent-check-custom-range |
| ctrl-range-dates | start/end date inputs (visible only in 自訂區間) | intent-check-custom-range |
| ctrl-workcenter-select | station-group single-select | intent-switch-workcenter |
| ctrl-cancel-query | 取消 on the async progress card | intent-abandon-slow-query |
| ctrl-open-settings | 設定 button on the report page | intent-open-settings |
| ctrl-target-* | TargetEditPanel 新增/編輯/儲存/取消 (unchanged) | intent-edit-target |
| ctrl-pkg-edit / ctrl-pkg-delete / ctrl-pkg-add | package-LF inline edit / delete / add-from-hint | intent-correct-package-lf |
| ctrl-wc-toggle / ctrl-wc-name | station include-exclude toggle / merged-name input | intent-manage-workcenter-merge |
| ctrl-plan-edit / ctrl-plan-new | daily-plan inline edit / new-row form | intent-set-daily-plan |

### Deleted Controls

| control | reason |
|---|---|
| shift_code multi-select filter | Its only intent was "view one shift in isolation." The new design shows D班 and N班 as always-present adjacent columns (and D%/N% as stacked chart segments), which serves comparison better but does not by itself reproduce a "N-shift-only standalone view." See Open Decision OD-1. |
| free-form start/end date pickers for 當日/前日/當月 | These three are now fixed windows derived from the current date (PA-13 `resolveMonthPeriod`), so a free date picker for them serves no remaining intent. Retained only for 自訂區間. See Open Decision OD-2. |
| 查詢 (Query) submit button | If mode/filter changes drive the query directly, an explicit submit control serves no distinct intent. See Open Decision OD-3. |
| 清除篩選 (Clear filters) button | The old reset existed because free-form filters could reach an unclear "filtered to nothing" state. The new design has no hidden filter state to recover: the active mode is always one of four visible buttons, and the station select always shows its current defaulted value (焊接_DB). A global reset would be a redundant, unrequested second path. |

## States

| id | meaning | discriminator |
|---|---|---|
| state-daily-warm-hit | today/yesterday served instantly from the warm cache (PA-14) — data.query_id present, no 202 in between | GET /api/production-achievement/report → HTTP 200 |
| state-async-polling | spool miss — background job running; for 當日/前日 this is the warm-cache-miss fallback (PA-14), shared machinery for all 4 modes (D5) | GET /api/production-achievement/report → 202 |
| state-success-populated | ≥1 PACKAGE_LF row exists for the selected station group after client filter (data-shape §3.28.1) | data-shape: non-empty dataset |
| state-empty-day | the selected station had no qualifying output for that day/range — OR the whole report is empty because `workcenter_merge_map` is empty and the D2 INNER JOIN drops every row (§3.31); the product explicitly decided not to distinguish these two causes (OD-9, Provenance G2) | data-shape: empty dataset |
| state-worker-unavailable | spool miss + no RQ worker (or `PRODUCTION_ACHIEVEMENT_USE_UNIFIED_JOB=off`) | GET /api/production-achievement/report → 503 |
| state-validation-error | missing/invalid dates, or range > 730 days (SYS-04) | GET /api/production-achievement/report → 400 |
| state-job-failed | the background job errored during fan-out (data.status resolves to "failed") | GET /api/job/{job_id} → data |
| state-spool-expired | the parquet was TTL-evicted before download (namespace=production_achievement) | GET /api/spool/{namespace}/{query_id}.parquet → 410 |
| state-settings-readonly | non-whitelisted; edit controls disabled after the first 403 — applies uniformly across package-lf-map/workcenter-merge-map/daily-plans | PUT /api/production-achievement/package-lf-map → 403 |
| state-settings-empty-pkg | no merge exceptions configured (every raw value falls back to self) — a valid state; also the state shown when `MYSQL_OPS_ENABLED=false` (OD-10, Provenance G2: not distinguished) | GET /api/production-achievement/package-lf-map → data |
| state-settings-empty-plan | no daily plans set (report rates show "—") — a valid state; also the state shown when `MYSQL_OPS_ENABLED=false` (OD-10, Provenance G2: not distinguished) | GET /api/production-achievement/daily-plans → data |
| state-settings-write-unavailable | MySQL OPS disabled — writes rejected — applies uniformly across all 3 settings-write endpoint families | PUT /api/production-achievement/package-lf-map → 503 |

Note (client-only states, no server discriminator — see Provenance G3, mirrors ADR 0012's own "state-initial" precedent, not rows above): **state-poll-timeout** (client gave up past its own `JOB_POLL_TIMEOUT`); **state-cancelled** (user clicked 取消; the best-effort `POST /api/job/{job_id}/abandon` call is a side effect, not what defines the state); **state-settings-editable** (optimistic default before any write is attempted, ends the moment `state-settings-readonly` is entered by a first observed 403).

Note (no UI surface): the D6 / PA-15 closing-chunk fix silently corrects previously under-counted last-day N-shift numbers. It adds no control and no state; it changes historical values only.

## Reversibility

- **Mode switch (4 buttons):** fully reversible — every mode is always visible and one is always active. Switching to a different date window (today↔yesterday↔month↔range) may trigger a fetch/poll, whereas re-selecting the current mode is free.
- **Station-group switch:** instant, free, fully reversible — it is a client-side re-filter of the already-downloaded day's spool, not a new query. The selected value is always shown in the select, which disambiguates `state-empty-day` from a system fault.
- **Range date change:** reversible by re-picking; applies a new fetch (see OD-3 on whether that is auto or explicit).
- **Cancel query:** reversible — re-selecting a mode re-triggers; the progress card disappears and the table is left empty with no error, never a half-rendered result.
- **Settings writes (package-LF upsert/delete, workcenter toggle/rename, daily-plan upsert):** persistent MySQL writes with no undo. Reversible only by re-editing to the previous value — and the previous value is not retained after an overwrite (only `updated_at`/`updated_by` are). A delete is reversible only if the admin remembers both the raw and merged strings. A write's effect on the report is delayed until the next spool/warmup cycle (up to ~`WARMUP_INTERVAL_SECONDS` ≈ 1 hr for today/yesterday) — see OD-5.
- **Unsaved settings edit on navigate-away:** currently silently discarded (matches TargetEditPanel today) — see OD-6.

## Consistency Commitments

- **Editable-vs-readonly is one language everywhere.** The fail-closed `editForbidden` pattern (optimistic edit → first-403 flips to read-only, with a read-only note) must look and behave identically across all three new settings panels and the unchanged TargetEditPanel.
- **The inline-edit affordance is one language.** "編輯 → input + 儲存/取消" must be the same recognizable form in PackageLfMappingPanel, DailyPlanPanel, and TargetEditPanel; that form must never also mean something non-editable.
- **"—" always means "no denominator," never "0%".** The null-rate rendering must be identical across PA-12 (daily), PA-13 (cumulative), and the legacy PA-07 (shift-based) table; a real 0.0 must be visibly distinct from "—" in all three.
- **D-shift and N-shift are encoded consistently across chart and table.** The D segment of a stacked bar and the D班產出 column must be recognizably the same thing (and likewise N).
- **Empty means different things in different places, so it must read differently.** `state-empty-day` (report: "no output for this station/day") and `state-settings-empty-pkg` (settings: "no merges configured") are different meanings and must not share the same "no data" copy.
- **The async progress card is one shared component across all four modes** (D5). A cold-cache poll must look the same whether the user is in 當日 or 自訂區間; only 200-instant vs 202-with-card distinguishes warm from cold.
- **The station single-select reuses App.vue's own existing fake-single-select idiom** (`:model-value="x ? [x] : []"`) rather than a new pattern or a change to the shared `MultiSelect.vue` (16 consumers, additive-only per CLAUDE.md).

## Open Decisions

- [x] **OD-1 — Was a shift-isolated view a real need?** The removed `shift_code` filter let a user see only N-shift (or only D). The new design always shows D班/N班 side by side. Options: (a) accept columns-only; (b) add a lightweight D/N visibility toggle on the table/chart; (c) reinstate a true shift filter that narrows table + chart.
- [x] **OD-2 — Is the daily D/N breakdown acceptably limited to today/yesterday?** An arbitrary past single day is now reachable only via 自訂區間, which renders in cumulative columns, never the daily D班/N班 columns.
- [x] **OD-3 — Auto-run vs explicit apply.** Does changing mode or station auto-run the query, and does 自訂區間 need an explicit 套用/查詢? Options: (a) fully auto-run everywhere; (b) auto-run today/yesterday/month, explicit apply for range only; (c) keep an explicit submit for all four.
- [x] **OD-4 — Mid-poll mode/filter switch.** While a 202 poll is in flight, what happens if the user clicks a different mode or changes the station? Options: (a) keep ignore-until-resolved; (b) cancel the in-flight job and start the new one; (c) hybrid — station change applies on completion, mode change cancels and restarts.
- [x] **OD-5 — Should a settings save disclose the propagation delay?** Options: (a) show a "changes apply on the next data refresh" note on save; (b) trigger a spool refresh on save so the change is immediate; (c) accept a silent delay.
- [x] **OD-6 — Unsaved-edit guard on settings navigation.** Options: (a) no guard (matches current TargetEditPanel); (b) a confirm-before-leave prompt.
- [x] **OD-7 — "設定" button label/placement and the return path.** The settings route has no drawer entry (D4), so return is browser-back only, and the report re-lands on default 當日/焊接_DB. Options: (a) rely on browser back and accept the reset; (b) add an in-page "返回報表" link; (c) additionally preserve the report's last mode/station across the round-trip.
- [x] **OD-8 — How does WorkcenterMergeMappingPanel show the excluded raw groups?** Options: (a) add a `GET /known-workcenter-groups` endpoint and enumerate the full raw universe with per-row include/exclude toggles (contract addition, routes back to contract-reviewer); (b) list only the 12 current rows plus a free-text "add raw group name" form (no enumeration, zero backend change); (c) have `filter-options` return raw + merged.
- [x] **OD-9 — Should the report distinguish "empty because config is down" from "empty because no output"?** Options: (a) accept the silent empty (matches §3.31 "not an error state"); (b) add a signal so the report can show "配置服務暫時無法使用" instead of an empty table (contract addition, routes back to contract-reviewer).
- [x] **OD-10 — Is write-time 503 enough on the settings page, or is a read-time "config unavailable" banner needed?** Options: (a) accept the write-time-503 behavior (matches existing TargetEditPanel precedent); (b) add a read-time discriminator so the settings page can say "config store unavailable" up front (contract addition, routes back to contract-reviewer).
- [x] **OD-11 — Keep an overall KPI summary on the report?** Options: (a) drop summary cards, letting the per-row table + chart carry it; (b) keep a single "overall daily/cumulative achievement for this station" card; (c) keep a reduced set.
- [x] **OD-12 — DailyPlanPanel new-row: constrained or free-text keys?** Options: (a) constrain both `workcenter_group`/`package_lf_group` to dropdowns of existing merged values; (b) allow free-text so an admin can pre-provision a plan for a combo not yet seen in data; (c) dropdown plus an "other" free-text escape.

## Confirmed

Transcribed 2026-07-14 from a direct dialogue with the user (three rounds via AskUserQuestion), plus OD-2 which was already answered earlier in the same conversation thread that produced the approved implementation plan.

- **OD-1 (shift-isolated view):** Not retained. Columns-only — D班/N班 always shown side by side, no shift-visibility toggle, no reinstated shift filter. User's words: "不保留，只看欄位".
- **OD-2 (daily D/N breakdown scope):** Already decided earlier in this change's planning conversation: "日期區間查詢功能暫時保留, 但是內容要依照當月的方式進行呈現" — 自訂區間 always renders in the cumulative (累計) style, never the daily D/N-column style, even for a single-day range. Option (a) accepted.
- **OD-3 (auto-run vs explicit apply):** Fully auto-run everywhere, including 自訂區間 — no explicit 套用/查詢 button in any of the 4 modes. User's words: "全部自動查詢".
- **OD-4 (mid-poll mode/filter switch):** Keep ignore-until-resolved (option a) — a mode or station change while a 202 poll is in flight is ignored until the current query completes; matches the existing `runQuery` guard behavior, no new cancel-and-restart logic. User's words: "忽略直到當前查詢完成".
- **OD-5 (propagation-delay disclosure):** Show a "changes apply on the next data refresh" note immediately after a successful settings save (option a). No spool-refresh-on-save. User's words: "儲存時顯示提示訊息".
- **OD-6 (unsaved-edit guard):** No guard — matches existing TargetEditPanel behavior; unsaved settings edits are silently discarded on navigation away. User's words: "不需要警告".
- **OD-7 ("設定" return path):** Preserve the report page's last-selected mode and station-group across the round-trip to the settings page and back (option c) — do not reset to 當日/焊接_DB on return. Implementer note: this requires the report page's mode/station state to survive the navigation (e.g. route query params, a shared composable/store, or sessionStorage — implementation detail left to frontend-engineer). User's words: "保留之前的模式與站點".
- **OD-8 (WorkcenterMergeMappingPanel excluded-group enumeration):** Add a new `GET /known-workcenter-groups` endpoint mirroring the existing `GET /known-package-lf-values` pattern, so the panel can enumerate the full raw `WORK_CENTER_GROUP` universe (including the ~15 currently-excluded groups) with per-row include/exclude toggles. User's words: "新增 endpoint 列出完整原始清單". **Contract addition required** — added directly below in this same pass (mirrors the existing endpoint/schema exactly; no separate contract-reviewer re-invocation needed for this narrow, precedented addition).
- **OD-9 (empty-because-config-down vs genuinely-empty, report):** No distinction needed — accept the existing §3.31 behavior (empty `workcenter_merge_map` → whole report renders empty, not an error). No contract change. User's words: "不需要，接受目前行為".
- **OD-10 (settings read-time unavailable banner):** No read-time discriminator — keep the existing write-time-503 behavior (matches TargetEditPanel precedent). No contract change. User's words: "不需要，維持儲存時才提示".
- **OD-11 (KPI summary cards):** Keep a reduced set (2-3 cards) — the exact set is an implementation detail for frontend-engineer, but must use the same aggregate-then-divide formula (PA-12 daily / PA-13 cumulative) as the detail table and chart, never a naive re-aggregation, so the headline number never contradicts the rows below it. User's words: "保留縮減版（2-3張）".
- **OD-12 (DailyPlanPanel new-row key constraints):** Constrained dropdowns only — both `workcenter_group` and `package_lf_group` in the new-plan-row form must be selected from existing merged values (from `workcenter-merge-map` and `package-lf-map`/known values respectively), no free-text option. User's words: "限定下拉選單".
