## ADDED Requirements

### Requirement: Mid-section defect genealogy SHALL use CONNECT BY instead of Python BFS
The mid-section-defect genealogy resolution SHALL use `LineageEngine.resolve_full_genealogy()` (CONNECT BY NOCYCLE) instead of the existing `_bfs_split_chain()` Python BFS implementation.

#### Scenario: Genealogy cold query performance
- **WHEN** mid-section-defect analysis executes genealogy resolution with cache miss
- **THEN** `LineageEngine.resolve_split_ancestors()` SHALL be called (single CONNECT BY query)
- **THEN** response time SHALL be ≤8s (P95) for ≥50 ancestor nodes
- **THEN** Python BFS `_bfs_split_chain()` SHALL NOT be called

#### Scenario: Genealogy hot query performance
- **WHEN** mid-section-defect analysis executes genealogy resolution with L2 Redis cache hit
- **THEN** response time SHALL be ≤1s (P95)

#### Scenario: Golden test result equivalence
- **WHEN** golden test runs with ≥5 known LOTs
- **THEN** CONNECT BY output (`child_to_parent`, `cid_to_name`) SHALL be identical to BFS output for the same inputs
