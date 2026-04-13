#!/usr/bin/env bash
# run_e2e.sh — Sequential E2E test runner (local + optional remote)
#
# Usage:
#   ./scripts/run_e2e.sh                                  # local only
#   E2E_REMOTE_URL=http://10.1.8.31:13006 ./scripts/run_e2e.sh  # local + remote
#
set -uo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
LOG_DIR="${ROOT}/logs"
mkdir -p "${LOG_DIR}"

LOCAL_E2E_LOG="${LOG_DIR}/e2e_local.log"
REMOTE_E2E_LOG="${LOG_DIR}/e2e_remote.log"
LOCAL_URL="${E2E_BASE_URL:-http://127.0.0.1:8080}"
REMOTE_URL="${E2E_REMOTE_URL:-}"

# ── Check local server ────────────────────────────────────────────────────────
echo "=== Checking local server status ==="
if ! "${ROOT}/scripts/start_server.sh" status 2>&1 | grep -q "RUNNING\|Gunicorn.*running\|gunicorn.*:8080"; then
  # Fallback: try a direct health check
  if ! curl -sf "${LOCAL_URL}/health" > /dev/null 2>&1; then
    echo ""
    echo "ERROR: Local server is not running."
    echo "Start it with: ./scripts/start_server.sh start"
    echo ""
    exit 1
  fi
fi
echo "Local server is up at ${LOCAL_URL}"

# ── Helper: extract summary counts ───────────────────────────────────────────
_extract_summary() {
  local log_file="$1"
  grep -E "passed|failed|skipped|error" "${log_file}" | tail -3
}

_run_e2e_target() {
  local label="$1"
  local base_url="$2"
  local log_file="$3"

  echo ""
  echo "=== Running E2E: ${label} (${base_url}) ==="
  echo "Log: ${log_file}"
  echo ""

  E2E_BASE_URL="${base_url}" pytest tests/e2e/ \
    -m e2e \
    --run-e2e \
    -v \
    --tb=short \
    2>&1 | tee "${log_file}"

  local exit_code=${PIPESTATUS[0]}
  echo ""
  echo "--- ${label} summary ---"
  _extract_summary "${log_file}"
  echo ""
  return "${exit_code}"
}

# ── Run local E2E ─────────────────────────────────────────────────────────────
local_exit=0
_run_e2e_target "LOCAL" "${LOCAL_URL}" "${LOCAL_E2E_LOG}" || local_exit=$?

# ── Run remote E2E (if configured) ───────────────────────────────────────────
remote_exit=0
if [[ -n "${REMOTE_URL}" ]]; then
  _run_e2e_target "REMOTE" "${REMOTE_URL}" "${REMOTE_E2E_LOG}" || remote_exit=$?
else
  echo "=== Remote E2E skipped (E2E_REMOTE_URL not set) ==="
fi

# ── Final status ──────────────────────────────────────────────────────────────
echo ""
echo "=== E2E Run Complete ==="
echo "Local:  $(tail -1 "${LOCAL_E2E_LOG}" 2>/dev/null || echo 'no log')"
if [[ -n "${REMOTE_URL}" ]]; then
  echo "Remote: $(tail -1 "${REMOTE_E2E_LOG}" 2>/dev/null || echo 'no log')"
fi

overall_exit=$(( local_exit + remote_exit ))
exit ${overall_exit}
