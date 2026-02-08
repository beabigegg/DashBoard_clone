## Context

The project already provides watchdog-assisted restart and resilience diagnostics, but policy boundaries for automated recovery are not yet formalized end-to-end. In practice, this can lead to either under-recovery (manual delays) or over-recovery (restart churn). We also need stronger conda/systemd path consistency checks to prevent runtime drift across deploy scripts and services.

## Goals / Non-Goals

**Goals:**
- Make conda/systemd runtime path contracts explicit, validated, and drift-detectable.
- Implement safe self-healing policy with cooldown and churn limits.
- Expose clear alert signals and recommended actions in health/admin payloads.
- Keep operator manual override available for incident control.

**Non-Goals:**
- Migrating from systemd to another orchestrator.
- Changing database vendor or introducing full autoscaling infrastructure.
- Removing existing admin restart endpoints.

## Decisions

1. **Single source runtime contract**
   - Decision: centralize conda runtime path configuration consumed by systemd units, watchdog, and scripts.
   - Rationale: prevents mismatched interpreter/path drift.

2. **Guarded self-healing state machine**
   - Decision: implement bounded restart policy (cooldown + max retries per time window + circuit-open gating).
   - Rationale: recovers quickly while preventing restart storms.

3. **Explicit recovery observability contract**
   - Decision: enrich health/admin payloads with churn counters, cooldown state, and recommended operator action.
   - Rationale: enables deterministic triage and alert automation.

4. **Auditability requirement**
   - Decision: emit structured logs/events for auto-restart decision, manual override, and blocked restart attempts.
   - Rationale: supports incident retrospectives and policy tuning.

5. **Runbook-first rollout**
   - Decision: deploy policy changes behind documentation and validation gates, including rollback steps.
   - Rationale: operational safety for production adoption.

## Risks / Trade-offs

- **[Risk] Overly strict policy delays recovery** → **Mitigation:** configurable thresholds and emergency manual override.
- **[Risk] Aggressive policy causes churn loops** → **Mitigation:** hard stop on churn threshold breach and explicit cool-off windows.
- **[Risk] Added operational complexity** → **Mitigation:** concise runbook with decision tables and tested scripts.
- **[Risk] Drift detection false positives** → **Mitigation:** normalize path resolution and clearly defined comparison sources.
