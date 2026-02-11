# Legacy Rewrite Priority Matrix

## Scoring model

`priority_score = usage(0-5)*0.3 + complexity(0-5)*0.4 + risk(0-5)*0.3`

- Usage: current observed operational usage + business criticality.
- Complexity: route/API count, frontend LOC, workflow branches.
- Risk: data mutation/export/upload sensitivity and regression blast radius.

## Measured technical baseline

| Page | Backend route LOC | Template LOC | Frontend LOC | API surface |
| --- | ---: | ---: | ---: | --- |
| `query-tool` | 509 | 1267 | 3139 | resolve/history/adjacent/associations/equipment/export |
| `excel-query` | 355 | 1181 | 624 | upload/schema/query/export |
| `job-query` | 195 | 995 | 520 | resources/jobs/txn/export |
| `tmtt-defect` | 82 | 271 | 363 | analysis/query + CSV export |

## Priority scoring

| Page | Usage | Complexity | Risk | Score |
| --- | ---: | ---: | ---: | ---: |
| `tmtt-defect` | 2 | 1 | 2 | 1.6 |
| `job-query` | 3 | 2 | 3 | 2.6 |
| `excel-query` | 3 | 4 | 4 | 3.7 |
| `query-tool` | 4 | 5 | 5 | 4.7 |

## Rewrite order decision

1. `tmtt-defect` (canonical exemplar)
2. `job-query`
3. `excel-query`
4. `query-tool`

## Rationale

- Start with lowest-complexity page to establish shared migration playbook.
- Keep high-complexity/high-risk `query-tool` last to maximize reuse from prior rewrites.
- Defer upload-heavy `excel-query` until shared error/retry/upload patterns are stabilized.
