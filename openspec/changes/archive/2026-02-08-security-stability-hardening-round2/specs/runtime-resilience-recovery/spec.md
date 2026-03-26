## ADDED Requirements

### Requirement: Circuit Breaker State Transitions SHALL Avoid Lock-Held Logging
Circuit breaker state transitions MUST avoid executing logger I/O while internal state locks are held.

#### Scenario: State transition occurs
- **WHEN** circuit breaker transitions between CLOSED, OPEN, or HALF_OPEN
- **THEN** lock-protected section MUST complete state mutation before emitting transition log output

#### Scenario: Slow log handler under load
- **WHEN** logger handlers are slow or blocked
- **THEN** circuit breaker lock contention MUST remain bounded and MUST NOT serialize unrelated request paths behind logging latency
