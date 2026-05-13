# Change Request

## Original Request

resource-history performance optimization:
1. 服務啟動時快取近三個月資料 (pre-warm Redis with the last ~3 months of data on service startup), TTL 一天 (TTL = 24 hours).
2. Implement a batch query progress polling endpoint (`GET /api/resource/history/query/progress?query_id=<id>`) to improve UX during long Oracle batch queries, and add frontend polling support.

The resource-history page has noticeably slow load and query times. The current Redis TTL is 2 hours for all queries (including immutable historical data). Long batch Oracle queries (date ranges > 10 days split into 31-day chunks) give no progress feedback to the user.

## Business / User Goal

## Non-goals

## Constraints

## Known Context

## Open Questions

## Requested Delivery Date / Priority
