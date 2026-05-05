---
contract: ci
summary: CI gate inventory, artifact retention, and rollback requirements.
owner: platform-team
surface: delivery-pipeline
schema-version: 1.0.0
last-changed: 2026-05-05
breaking-change-policy: deprecate-2-minors
---

# CI/CD Gate Contract — MES Dashboard

> 來源：整合自 `ci/gate-policy.md`、`ci/required-check-policy.md`、`.github/workflows/contract-driven-gates.yml`（2026-05-05）

## Gate Inventory

| gate | tier | trigger | required | command | owner | artifact |
|---|---:|---|---:|---|---|---|
| contract-validate | 0 | local pre-PR | yes | `cdd-kit validate` | platform-team | — |
| lint | 0 | local / PR | yes | `ruff check .` | application-team | — |
| type-check | 0 | local / PR | yes | `mypy src/` | application-team | — |
| unit-tests | 1 | PR | yes | `pytest` | application-team | test report |
| frontend-unit | 1 | PR | yes | `cd frontend && npm run test` | application-team | vitest report |
| css-governance | 1 | PR | yes | `cd frontend && npm run css:check` | application-team | governance report |
| critical-e2e | 1 | PR | yes | `npx playwright test --project=critical` (TBD) | application-team | playwright trace |
| visual-regression | 2 | PR | informational | (TBD) | application-team | screenshot diff |
| real-infra-smoke | 2 | PR | informational | — | platform-team | — |
| nightly-integration | 3 | nightly (`0 18 * * 1`) | yes (nightly) | `pytest --run-integration-real` | application-team | test report |
| stress-soak | 4 | weekly / `workflow_dispatch` | yes (weekly) | locust / k6 (TBD) | platform-team | perf report |

## Required Check Policy

- **Tier 1** gates（unit-tests、frontend-unit、css-governance、critical-e2e）block merge。
- **Tier 2** gates（visual-regression、real-infra-smoke）run on PR but do not block until stable (20 days / 60 runs / pass rate > threshold / runtime within limit)。
- **Tier 3** nightly gates：failure must be triaged within 1 business day。
- **Tier 4** weekly soak：failure triggers production-readiness review。

新增 gate 必須先以 informational 啟動，達 promotion criteria 後才提升為 required。

## Gate Tier Semantics

| tier | name | when blocked |
|---|---|---|
| 0 | Local Fast Gate | 本地 pre-PR；lint、typecheck、targeted unit、contract validate |
| 1 | PR Required Gate | blocks merge；build、unit、API/CSS/env/data contracts、critical E2E、fuzz |
| 2 | PR Informational Gate | runs on PR, does not block；visual regression、real-infra smoke |
| 3 | Nightly Real-Infra Gate | real DB/cache/queue；driver timeout、failover、race condition |
| 4 | Weekly Soak / Stress Gate | long-run stability；soak hours、load vus |

## Workflow Configuration

檔案：`.github/workflows/contract-driven-gates.yml`

| job | trigger | stack | status |
|---|---|---|---|
| `contract-and-fast-tests` | push/PR | Python 3.10 + Node 20 + conda mes-dashboard | configured |
| `e2e-critical` | PR only | (Playwright — TBD) | placeholder |
| `scheduled-stress-soak` | weekly schedule / dispatch | (locust/k6 — TBD) | placeholder |

**TODO：** 填入 `e2e-critical` 和 `scheduled-stress-soak` job 的實際命令。

## Informational Gate Promotion Policy

Promote from informational to required after ALL of:
- 20 calendar days or 60 runs
- pass rate above agreed threshold
- failures triaged and documented
- runtime within acceptable limit
- owner assigned

## Artifact Retention Policy

| artifact | retention |
|---|---|
| pytest / vitest report | 30 days |
| Playwright traces | 7 days (longer on failure) |
| Screenshot diffs | 30 days |
| Soak/stress reports | 90 days |

## Rollback Policy

- 任何 Tier 1 gate 變紅後 main branch 不得合入新 PR，直到修復。
- Tier 3/4 failure 需開 incident ticket，24 小時內回復或降級。
- Feature flag 是 rollback 第一防線；DB migration rollback 需附 down migration。

## Contract Change Policy

新增、移除或修改 CI gate 時，必須同步更新此契約（同一 PR），並在 PR 描述說明影響的 tier 和原因。
