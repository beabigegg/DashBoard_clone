# Change Request

## Original Request

Apply the same 4-tuple partial-trackout aggregation with strict guard to query-tool's lot_history, equipment_lots, and adjacent_lots SQL queries, mirroring what was done in prod-history-detail-partial-merge for production-history.

Currently all three SQL files use `ROW_NUMBER() OVER (PARTITION BY ... ORDER BY TRACKOUTTIMESTAMP DESC)` to deduplicate partial track-outs, which silently yields incorrect values: TRACKINQTY reflects the last (lowest) partial's remaining quantity instead of the original load (MAX), and TRACKOUTQTY reflects only the last partial's output instead of the cumulative total (SUM).

## Business / User Goal

## Non-goals

## Constraints

## Known Context

## Open Questions

## Requested Delivery Date / Priority
