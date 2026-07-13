---
change-id: fix-equipment-lots-trim
schema-version: 0.1.0
last-changed: 2026-07-13
# ADR 0011 skip escape -- leave the two lines below commented out for any
# change that has a real screen, control, or user-facing state (almost every
# change does). Only uncomment BOTH lines if this specific change truly has
# NO user-facing surface at all (a pure backend job, a database migration, a
# CLI-only change with no screens). If you uncomment `applicability`,
# `applicability-reason` becomes REQUIRED and must be non-empty, or
# `cdd-kit gate` HARD-fails on purpose -- a bare skip with no justification
# is never allowed (ADR 0011; see docs/adr/0011-not-applicable-contract-marker.md).
# applicability: not-applicable
# applicability-reason: <why this change genuinely has no UI surface>
---

# Interaction Design: fix-equipment-lots-trim

<!--
WHAT THIS FILE IS FOR (read this before touching anything below).

Every other kind of mistake in this kit gets caught by a contract. This file
closes the one gap nothing else catches: an AI agent quietly deciding, on its
own judgment, what a screen shows, why a button exists, and how a user tells
one state of the world apart from another. Those are HUMAN decisions. This
file forces them into human hands and then locks the human's answer so no
later agent edit can quietly change it back.

WHO WRITES WHAT (the roles are strict; do not blur them):
  1. `interaction-designer` (an AI agent, READ-ONLY) fills in the derivation
     chain below -- Screens, Presented Information, User Intents, Controls,
     States, Reversibility, Consistency Commitments -- and writes the open
     questions into `## Open Decisions`. It is structurally incapable of
     writing `## Confirmed` (its tools are Read/Grep/Glob only).
  2. Main Claude runs a plain-language conversation with YOU (the human) to
     work through `## Open Decisions`.
  3. YOU decide. Main Claude transcribes your actual answers -- not a
     paraphrase, not "close enough" -- into `## Confirmed`.
  4. YOU (or whoever runs the CLI on your behalf) lock it in:
         cdd-kit design confirm <this-change-id>
     Until step 4 happens, `cdd-kit gate` will keep failing this change on
     purpose -- that is not a bug, it is the whole point (mirrors how
     `specs/changes/fix-equipment-lots-trim/acceptance.yml` works for behavior, ADR 0010).

HOW TO FILL THIS IN, IN PLAIN LANGUAGE (no code-reading required):
  - Every row you add should answer a real question a real user has. If you
    cannot say which question an item answers, it probably should not be on
    the screen (this is the same "does this need to exist at all" question
    the kit already asks about code, now asked about the interface).
  - Every citation (the `provenance` / `discriminator` columns) points at a
    specific row in `contracts/api/api-contract.md` or
    `contracts/data/data-shape-contract.md` -- see `## Provenance` below for
    the exact five ways to write one. If nothing in those contracts can back
    up what the screen wants to show, that is not a template-filling
    problem -- it means the backend contract needs to grow a field first.
    `interaction-designer` will loop back to `contract-reviewer` when that
    happens; you do not need to fix contracts by hand here.
  - A control you thought about and decided NOT to build still belongs in
    `### Deleted Controls`, with the real reason. A "reset" or "clear" button
    that nobody asked for and nothing derives is exactly the kind of
    gratuitous control this file exists to catch before it ships.
  - Nothing here is about color, spacing, font, animation, or "looking
    modern". None of that is ever checked by `cdd-kit gate` and none of it
    belongs in this file (see docs/adr/0012-interaction-design-loop.md
    "Never Gated"). This file is about what is shown, why, and how a user
    tells two situations apart -- never about taste.
-->

## Provenance

<!--
Reference only -- read this once, then use it while filling in the
`provenance` column below (## Presented Information) and the
`discriminator` column (## States). Every citation must be one of these five
forms, written EXACTLY like this (a human reviewer or `cdd-kit gate` reads
these mechanically, so the format matters):

  1. A field in an API response:
       GET /orders → items.status
     (dotted path for a nested field; bare name is enough for a field inside
     a list -- you never need to spell out "the third item's status", just
     `items.status`.)

  2. A field pinned to one specific value (use this when two states share
     the same field but mean different things -- e.g. "rejected" vs
     "approved" both live in a `status` field):
       POST /orders → status=rejected

  3. A specific HTTP status already listed for that endpoint's errors:
       POST /orders → 409

  4. The plain "it worked" status for that kind of request (201 for
     creating something, 200 for everything else) -- write it out so a
     reviewer does not have to guess:
       POST /orders → HTTP 201

  5. A named row in the data-shape contract's invalid-data table (copy the
     `condition` value exactly, e.g. `empty dataset`, `wrong type`,
     `missing required column`, `over max row limit`, `unexpected enum`):
       data-shape: empty dataset

If none of the five forms can describe where a piece of information or a
state actually comes from, that is a real signal -- it usually means the
backend contract is missing something (a field, a distinct error code, a
timestamp) and needs to grow before this screen can honestly show what it
promises. See docs/adr/0012-interaction-design-loop.md §2 for the full
reasoning (the "blank cheque" table).
-->

## Screens

<!--
One row per distinct screen or view in this change. Write like you are
describing a real person sitting in front of it, not a component name.

Example (delete or replace with your own):
| checkout summary | a shopper who has items in their cart | whether to trust this site enough to pay | being charged twice, or charged the wrong amount | seeing a total that does not match what they expect, with no way to check | the shopper's stored card number in full |
-->

| screen | who is here | what they are deciding | what they fear | what would make them abandon | what must not be shown |
|---|---|---|---|---|---|
| query-tool 批次追蹤生產設備 — 生產紀錄/維修紀錄/報廢紀錄 sub-tabs | a fab engineer who resolved a batch of LOT IDs/work orders to their processing equipment and now needs each equipment's production/repair/reject history for a date range | whether the equipment history shown is complete and current enough to act on (e.g. trace a defect, confirm a repair) | acting on a row set that looks complete but silently isn't (the pre-fix bug: real rows existed but the table rendered empty) | seeing "目前沒有資料" after a query that took a long time, with no way to tell whether that means "genuinely no data" or "the query is broken" | a stale row set left over from a previous, now-superseded filter selection |

## Presented Information

<!--
One row per distinct piece of information the screen shows. `rationale` is
the user question this item answers -- if you cannot write a real question,
reconsider whether the item should be on the screen at all. `provenance` is
one of the five citation forms from ## Provenance above.

Example (delete or replace with your own):
| order total | "how much am I actually being charged?" | POST /orders → total_amount |
-->

<!--
CONTAINERNAME/EQUIPMENTNAME/timestamp/qty/work-order columns below all cite
the same `data.data` field: this citation resolver (ADR 0012 §2) cannot
express per-array-item fields (`resolveDottedField` requires `type: object`
at every path segment, and `data.data` is a `type: array`), so a per-column
Form-1 citation is not expressible for any row-shape response in this
project, not just this one. The authoritative per-column type/nullability
source is `contracts/data/data-shape-contract.md` §3.6 (named in each
row's rationale below); `data.data`'s existence as a real, contract-typed
response field is what each citation here actually proves.
-->

| item | rationale | provenance |
|---|---|---|
| CONTAINERNAME (LOT ID) | "which batch does this row belong to?" (type/nullability: data-shape-contract.md §3.6 CONTAINERNAME) | POST /api/query-tool/equipment-period → data.data |
| EQUIPMENTNAME | "which machine processed this batch?" (type/nullability: data-shape-contract.md §3.6 EQUIPMENTNAME) | POST /api/query-tool/equipment-period → data.data |
| TRACKINTIMESTAMP / TRACKOUTTIMESTAMP | "when did this batch enter/leave this equipment?" (type/nullability: data-shape-contract.md §3.6 TRACKINTIMESTAMP / TRACKOUTTIMESTAMP) | POST /api/query-tool/equipment-period → data.data |
| TRACKINQTY / TRACKOUTQTY | "how many units went in vs. came out?" (type/nullability: data-shape-contract.md §3.6 TRACKINQTY / TRACKOUTQTY) | POST /api/query-tool/equipment-period → data.data |
| WORKORDER / PJ_TYPE / PJ_BOP / PACKAGE (PRODUCTLINENAME) / SPECNAME | "which work order/product spec is this batch running?" (type/nullability: data-shape-contract.md §3.6 PJ_WORKORDER, PJ_TYPE, PJ_BOP, PRODUCTLINENAME, SPECNAME) | POST /api/query-tool/equipment-period → data.data |
| row count found ("找到 N 台設備") | "did the equipment lookup actually find anything before I wait for the detail query?" | POST /api/query-tool/lot-equipment-lookup → data.equipment_ids |

## User Intents

<!--
List what users actually come here to DO, ordered by how often it really
happens -- not by how important the feature feels to build. Each intent
needs a stable `id` (referenced by ## Controls below) and the concrete path
(screen/step sequence) that serves it.

Example (delete or replace with your own):
| intent-checkout | complete a purchase | most requests, every day | checkout summary -> confirm -> receipt |
-->

| id | intent | frequency | path |
|---|---|---|---|
| intent-view-lots | see which pieces of equipment processed a resolved batch, and when | every visit to this tab | resolve batches → lookupEquipment() → 生產紀錄 sub-tab (default) |
| intent-view-jobs | check equipment repair/job history for the same resolved batch set | occasional, when investigating a defect | resolve batches → switch to 維修紀錄 sub-tab |
| intent-view-rejects | check reject events tied to the same resolved batch set | occasional, when investigating yield | resolve batches → switch to 報廢紀錄 sub-tab |

## Controls

<!--
One row per interactive control (button, link, toggle, filter chip -- any
element a user acts on). `intent` must cite EXACTLY ONE id from the User
Intents table above -- a control that cannot name the one intent it serves
should not exist (see Deleted Controls below for where it goes instead).

Example (delete or replace with your own):
| ctrl-confirm-pay | "Confirm and pay" button | intent-checkout |
-->

| id | control | intent |
|---|---|---|
| ctrl-subtab-lots | "生產紀錄" sub-tab button | intent-view-lots |
| ctrl-subtab-jobs | "維修紀錄" sub-tab button | intent-view-jobs |
| ctrl-subtab-rejects | "報廢紀錄" sub-tab button | intent-view-rejects |

### Deleted Controls

<!--
Controls that were considered and deliberately NOT built -- recorded WITH
the real reason, so nobody re-proposes the same gratuitous control later.
This is where a "reset all filters" button dies honorably when the same
need is already met another way (e.g. each active filter already shows its
own dismissible chip). A control here with no reason is a gate failure --
"we didn't think of a reason" is not an allowed reason.

Example (delete or replace with your own):
| clear-all-filters button | each active filter already renders as its own visible, individually-dismissible chip; a second global control would be a redundant, unrequested way to do the same thing (ADR 0012 rejected-proposal #2) |
-->

| control | reason |
|---|---|

## States

<!--
One row per meaning-distinct state a screen can be in (loading, empty,
error, success, offline, partial, etc.). `discriminator` is how the CONTRACT
tells this state apart from every other state -- one of the five citation
forms from ## Provenance above. This is the single most important table in
this file: an empty list from the backend often means two completely
different things to a user ("nothing happened yet" vs "the system is
broken") and if the contract does not supply a way to tell them apart, this
file's whole job is to surface that gap before it ships silently. Two rows
here with genuinely different meanings can never cite the same
discriminator -- `cdd-kit gate` enforces that mechanically.

Example (delete or replace with your own):
| state-empty | the search really did return zero results | GET /orders → HTTP 200 (empty items array, no error) |
| state-blocked | the search could not run because the backend is unavailable | GET /orders → 503 |
-->

| id | meaning | discriminator |
|---|---|---|
| state-async-pending | the query was classified async and is queued/running as an RQ job; the driver is polling for completion | POST /api/query-tool/equipment-period → 202 |
| state-populated | the query completed and matched at least one row for the resolved batch/equipment set | data-shape: non-empty dataset |
| state-empty-genuine | the query completed successfully and there really are zero matching rows for the resolved batch/equipment set in the given date range | data-shape: empty dataset |
| state-error | the query failed (timeout, validation, or server error) rather than genuinely finding zero rows | POST /api/query-tool/equipment-period → 500 |

<!--
state-loading (query dispatched, sync or async, result not yet available)
has NO backend-contract discriminator by design: before any response
arrives there is, by definition, no field or status code to point at --
this is pure client bookkeeping (a request-in-flight flag), never
observable on the wire. Documented here in prose rather than forced into
the table above, mirroring query-tool-subtab-cache's interaction-design.md
treatment of its own client-only cache-hit/cache-miss distinction. Per the
Consistency Commitment below, state-loading must render identically
whether the underlying request is still sync-pending or has already
transitioned to state-async-pending.
-->

## Reversibility

All three sub-tabs (生產紀錄/維修紀錄/報廢紀錄) are read-only views — switching between them is always reversible, and re-entering a sub-tab after leaving it does not lose or alter its previously-loaded rows. Re-running the batch/equipment lookup with a changed filter set (different LOT IDs/work orders, workcenter groups) replaces the resolved equipment set and clears each sub-tab's rows, so the user cannot end up looking at rows from a stale, now-superseded filter selection.

## Consistency Commitments

The loading state (`state-loading`) must look identical to the user regardless of whether the underlying query resolves synchronously or is dispatched as an async RQ job (`state-async-pending`) — this is the exact distinction the pre-fix bug got wrong: a query dispatched async silently ended up looking like `state-empty-genuine` (目前沒有資料) instead of staying in a visibly-loading state through to `state-populated`. `state-empty-genuine` and `state-error` must never share the same visible form — a failed/timed-out query must never look like "we searched and there is genuinely nothing here."


## Open Decisions

<!--
Questions `interaction-designer` could not answer on its own -- each one
needs real options and real trade-offs, not a rhetorical "should we do X?".
Main Claude turns each one into a real conversation with you. Mark a
question `- [x]` only once your actual answer has been transcribed into the
Confirmed section below; an unresolved `- [ ]` item fails `cdd-kit gate` on
purpose, so a question can never be silently skipped.
-->

- [x] For a wide-date-range query that gets dispatched as an async RQ job (can take from a few seconds up to the poller's 30-minute cap), should `state-loading`/`state-async-pending` show anything beyond a generic spinner (e.g. an elapsed-time counter or a "large date ranges can take longer" hint), or is a plain spinner sufficient? Option A: plain spinner only (matches what actually shipped — no new UI element was added by this change). Option B: add a hint/elapsed-time indicator for long-running async waits (a real UI addition beyond what this bug-fix change implemented).

## Confirmed

<!-- AGENT-FORBIDDEN. No agent -- not interaction-designer, not main Claude acting on its own judgment, not any other role -- may invent, paraphrase, or "fill in" an answer here. -->
<!-- Only a real, transcribed human answer belongs in this section, one per resolved Open Decisions item above, dated. -->

- Open Decision (state-loading/state-async-pending beyond generic spinner): **Option A — plain spinner only**, matching what actually shipped; no new UI element added. Confirmed by user on 2026-07-13.
<!-- Once every Open Decisions item above has a real transcribed answer here, lock this file against later tampering by running: cdd-kit design confirm <this-change-id> -->
<!-- That command is the ONLY sanctioned writer of .cdd/design-lock.json. A pre-tool-use-design-write.sh hook additionally blocks any agent from writing that lock file directly. -->
<!-- If this section is edited after locking, cdd-kit gate fails with: "interaction design modified after confirmation -- human must re-confirm." That is intentional: re-confirm, never silently trust an unreviewed edit. -->
