## ADDED Requirements

### Requirement: Recovery Recommendations SHALL Reflect Self-Healing Policy State
Health and admin resilience payloads MUST expose whether automated recovery is allowed, cooling down, or blocked by churn policy.

#### Scenario: Operator inspects degraded state
- **WHEN** `/health` or `/admin/api/worker/status` is requested during degradation
- **THEN** response MUST include policy state, cooldown remaining time, and next recommended action

### Requirement: Manual Recovery Override SHALL Be Explicit and Controlled
Manual restart actions MUST bypass automatic block only through authenticated operator pathways with explicit acknowledgement.

#### Scenario: Churn-blocked state with manual override request
- **WHEN** authorized admin requests manual restart while auto-recovery is blocked
- **THEN** system MUST execute controlled restart path and log the override context for auditability
