# Performance Baseline Comparison

Measured via Flask test client (route latency in ms).

## Key Entry Routes

| Surface | Avg (ms) | P95 (ms) |
| --- | ---: | ---: |
| Legacy portal `/` | 1.557 | 0.891 |
| SPA shell `/portal-shell` | 0.239 | 0.263 |

## Shared API Route

| Route | Legacy Avg (ms) | SPA Avg (ms) | Delta (ms) |
| --- | ---: | ---: | ---: |
| `/api/portal/navigation` | 0.341 | 0.313 | -0.028 |

## Notes

- This baseline is synthetic (test client), used for migration regression gate trend tracking.
- Production browser/network RUM should be captured separately during canary rollout.
