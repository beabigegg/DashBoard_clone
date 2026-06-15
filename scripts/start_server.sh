#!/usr/bin/env bash
#
# MES Dashboard Server Management Script
# Usage: ./start_server.sh [start|stop|restart|status|logs]
#
set -uo pipefail

# ============================================================
# Configuration
# ============================================================
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
CONDA_ENV="${CONDA_ENV_NAME:-mes-dashboard}"
APP_NAME="mes-dashboard"
PID_FILE_DEFAULT="${ROOT}/tmp/gunicorn.pid"
PID_FILE="${WATCHDOG_PID_FILE:-${PID_FILE_DEFAULT}}"
LOG_DIR="${ROOT}/logs"
ACCESS_LOG="${LOG_DIR}/access.log"
ERROR_LOG="${LOG_DIR}/error.log"
WATCHDOG_LOG="${LOG_DIR}/watchdog.log"
STARTUP_LOG="${LOG_DIR}/startup.log"
DEFAULT_PORT="${GUNICORN_BIND:-0.0.0.0:8080}"
PORT=$(echo "$DEFAULT_PORT" | cut -d: -f2)

# Redis configuration
REDIS_ENABLED="${REDIS_ENABLED:-true}"
REDIS_KEY_PREFIX="${REDIS_KEY_PREFIX:-mes_wip}"
REDIS_MAXMEMORY="${REDIS_MAXMEMORY:-512mb}"
REDIS_MAXMEMORY_POLICY="${REDIS_MAXMEMORY_POLICY:-allkeys-lru}"
REDIS_PERSISTENCE_ENABLED="${REDIS_PERSISTENCE_ENABLED:-true}"
REDIS_APPENDONLY="${REDIS_APPENDONLY:-yes}"
REDIS_APPENDFSYNC="${REDIS_APPENDFSYNC:-everysec}"
REDIS_SAVE="${REDIS_SAVE:-900 1 300 10 60 10000}"
REDIS_TTL_CLEANUP_ON_START="${REDIS_TTL_CLEANUP_ON_START:-true}"
REDIS_TTL_CLEANUP_PATTERNS="${REDIS_TTL_CLEANUP_PATTERNS:-batch:*,reject_dataset:*,hold_dataset:*,resource_dataset:*,job_query:*}"
# Worker watchdog configuration
WATCHDOG_ENABLED="${WATCHDOG_ENABLED:-true}"
# RQ trace worker configuration
TRACE_WORKER_ENABLED="${TRACE_WORKER_ENABLED:-true}"
TRACE_WORKER_QUEUE="${TRACE_WORKER_QUEUE:-trace-events}"
# RQ reject query worker configuration
RQ_REJECT_WORKER_ENABLED="${RQ_REJECT_WORKER_ENABLED:-true}"
RQ_REJECT_WORKER_QUEUE="${RQ_REJECT_WORKER_QUEUE:-reject-query}"
# RQ msd analysis worker configuration
RQ_MSD_WORKER_ENABLED="${RQ_MSD_WORKER_ENABLED:-true}"
RQ_MSD_WORKER_QUEUE="${MSD_WORKER_QUEUE:-msd-analysis}"
# RQ production-history worker configuration
RQ_PRODUCTION_HISTORY_WORKER_ENABLED="${RQ_PRODUCTION_HISTORY_WORKER_ENABLED:-true}"
RQ_PRODUCTION_HISTORY_WORKER_QUEUE="${PRODUCTION_HISTORY_WORKER_QUEUE:-production-history-query}"
# RQ yield-alert worker configuration
RQ_YIELD_ALERT_WORKER_ENABLED="${RQ_YIELD_ALERT_WORKER_ENABLED:-true}"
RQ_YIELD_ALERT_WORKER_QUEUE="${YIELD_ALERT_WORKER_QUEUE:-yield-alert-query}"
# RQ hold-history worker configuration
RQ_HOLD_HIST_WORKER_ENABLED="${RQ_HOLD_HIST_WORKER_ENABLED:-true}"
RQ_HOLD_HIST_WORKER_QUEUE="${HOLD_WORKER_QUEUE:-hold-history-query}"
# RQ warmup worker configuration
RQ_WARMUP_WORKER_ENABLED="${RQ_WARMUP_WORKER_ENABLED:-true}"
RQ_WARMUP_WORKER_QUEUE="${WARMUP_WORKER_QUEUE:-warmup}"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# ============================================================
# Helper Functions
# ============================================================
log_info() {
    echo -e "${BLUE}[INFO]${NC} $1"
}

log_success() {
    echo -e "${GREEN}[OK]${NC} $1"
}

log_warn() {
    echo -e "${YELLOW}[WARN]${NC} $1"
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

timestamp() {
    date '+%Y-%m-%d %H:%M:%S'
}

is_enabled() {
    case "${1:-}" in
        1|[Tt][Rr][Uu][Ee]|[Yy][Ee][Ss]|[Oo][Nn])
            return 0
            ;;
        *)
            return 1
            ;;
    esac
}

resolve_runtime_paths() {
    WATCHDOG_RUNTIME_DIR="${WATCHDOG_RUNTIME_DIR:-${ROOT}/tmp}"
    WATCHDOG_RESTART_FLAG="${WATCHDOG_RESTART_FLAG:-${WATCHDOG_RUNTIME_DIR}/mes_dashboard_restart.flag}"
    WATCHDOG_PID_FILE="${WATCHDOG_PID_FILE:-${WATCHDOG_RUNTIME_DIR}/gunicorn.pid}"
    WATCHDOG_STATE_FILE="${WATCHDOG_STATE_FILE:-${WATCHDOG_RUNTIME_DIR}/mes_dashboard_restart_state.json}"
    WATCHDOG_PROCESS_PID_FILE="${WATCHDOG_PROCESS_PID_FILE:-${WATCHDOG_RUNTIME_DIR}/worker_watchdog.pid}"
    RQ_WORKER_PID_FILE="${WATCHDOG_RUNTIME_DIR}/rq_trace_worker.pid"
    RQ_WORKER_LOG="${LOG_DIR}/rq_worker.log"
    RQ_REJECT_WORKER_PID_FILE="${WATCHDOG_RUNTIME_DIR}/rq_reject_worker.pid"
    RQ_REJECT_WORKER_LOG="${LOG_DIR}/rq_reject_worker.log"
    RQ_MSD_WORKER_PID_FILE="${WATCHDOG_RUNTIME_DIR}/rq_msd_worker.pid"
    RQ_MSD_WORKER_LOG="${LOG_DIR}/rq_msd_worker.log"
    RQ_PROD_HIST_WORKER_PID_FILE="${WATCHDOG_RUNTIME_DIR}/rq_prod_hist_worker.pid"
    RQ_PROD_HIST_WORKER_LOG="${LOG_DIR}/rq_prod_hist_worker.log"
    RQ_YIELD_ALERT_WORKER_PID_FILE="${WATCHDOG_RUNTIME_DIR}/rq_yield_alert_worker.pid"
    RQ_YIELD_ALERT_WORKER_LOG="${LOG_DIR}/rq_yield_alert_worker.log"
    RQ_HOLD_HIST_WORKER_PID_FILE="${WATCHDOG_RUNTIME_DIR}/rq_hold_hist_worker.pid"
    RQ_HOLD_HIST_WORKER_LOG="${LOG_DIR}/rq_hold_hist_worker.log"
    RQ_WARMUP_WORKER_PID_FILE="${WATCHDOG_RUNTIME_DIR}/rq_warmup_worker.pid"
    RQ_WARMUP_WORKER_LOG="${LOG_DIR}/rq_warmup_worker.log"
    RQ_LOG_FORMAT="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
    RQ_DATE_FORMAT="%Y-%m-%d %H:%M:%S"
    PID_FILE="${WATCHDOG_PID_FILE}"
    export WATCHDOG_RUNTIME_DIR WATCHDOG_RESTART_FLAG WATCHDOG_PID_FILE WATCHDOG_STATE_FILE WATCHDOG_PROCESS_PID_FILE
}

# Load .env file if exists
load_env() {
    if [ -f "${ROOT}/.env" ]; then
        log_info "Loading environment from .env"
        set -a  # Mark all variables for export
        source "${ROOT}/.env"
        set +a
    fi
}

# ============================================================
# Environment Check Functions
# ============================================================
check_conda() {
    if ! command -v conda &> /dev/null; then
        log_error "Conda not found. Please install Miniconda/Anaconda."
        return 1
    fi

    if [ -n "${CONDA_BIN:-}" ] && [ ! -x "${CONDA_BIN}" ]; then
        log_error "CONDA_BIN is set but not executable: ${CONDA_BIN}"
        return 1
    fi

    # Source conda
    local conda_cmd="${CONDA_BIN:-$(command -v conda)}"
    source "$(${conda_cmd} info --base)/etc/profile.d/conda.sh"

    # Check if environment exists
    if ! conda env list | grep -q "^${CONDA_ENV} "; then
        log_error "Conda environment '${CONDA_ENV}' not found."
        log_info "Create it with: conda create -n ${CONDA_ENV} python=3.11"
        return 1
    fi

    log_success "Conda environment '${CONDA_ENV}' found"
    return 0
}

validate_runtime_contract() {
    conda activate "$CONDA_ENV"
    export PYTHONPATH="${ROOT}/src:${PYTHONPATH:-}"

    if python - <<'PY'
import os
import sys

from mes_dashboard.core.runtime_contract import build_runtime_contract_diagnostics

strict = os.getenv("RUNTIME_CONTRACT_ENFORCE", "true").strip().lower() in {"1", "true", "yes", "on"}
diag = build_runtime_contract_diagnostics(strict=strict)
if not diag["valid"]:
    for error in diag["errors"]:
        print(f"RUNTIME_CONTRACT_ERROR: {error}")
    raise SystemExit(1)
PY
    then
        log_success "Runtime contract validation passed"
        return 0
    fi

    log_error "Runtime contract validation failed"
    log_info "Fix env vars: WATCHDOG_RUNTIME_DIR / WATCHDOG_RESTART_FLAG / WATCHDOG_PID_FILE / WATCHDOG_STATE_FILE / CONDA_BIN"
    return 1
}

check_dependencies() {
    conda activate "$CONDA_ENV"

    local missing=()

    # Check critical packages
    python -c "import flask" 2>/dev/null || missing+=("flask")
    python -c "import gunicorn" 2>/dev/null || missing+=("gunicorn")
    python -c "import pandas" 2>/dev/null || missing+=("pandas")
    python -c "import oracledb" 2>/dev/null || missing+=("oracledb")
    python -c "import duckdb" 2>/dev/null || missing+=("duckdb")

    if [ ${#missing[@]} -gt 0 ]; then
        log_error "Missing dependencies: ${missing[*]}"
        log_info "Install with: pip install ${missing[*]}"
        return 1
    fi

    log_success "All dependencies installed"
    return 0
}

check_env_file() {
    if [ ! -f "${ROOT}/.env" ]; then
        if [ -f "${ROOT}/.env.example" ]; then
            log_warn ".env file not found, but .env.example exists"
            log_info "Copy and configure: cp .env.example .env"
        else
            log_warn ".env file not found (optional but recommended)"
        fi
        return 0
    fi

    log_success ".env file found"
    return 0
}

check_port() {
    if lsof -i ":${PORT}" -sTCP:LISTEN &>/dev/null; then
        local pid=$(lsof -t -i ":${PORT}" -sTCP:LISTEN 2>/dev/null | head -1)
        log_error "Port ${PORT} is already in use (PID: ${pid})"
        log_info "Stop the existing process or change GUNICORN_BIND"
        return 1
    fi

    log_success "Port ${PORT} is available"
    return 0
}

check_database() {
    conda activate "$CONDA_ENV"
    export PYTHONPATH="${ROOT}/src:${PYTHONPATH:-}"

    if python -c "
from sqlalchemy import text
from mes_dashboard.core.database import get_engine
engine = get_engine()
with engine.connect() as conn:
    conn.execute(text('SELECT 1 FROM DUAL'))
" 2>/dev/null; then
        log_success "Database connection OK"
        return 0
    else
        log_warn "Database connection failed (service may still start)"
        return 0  # Non-fatal, allow startup
    fi
}

build_frontend_assets() {
    local mode="${FRONTEND_BUILD_MODE:-}"
    local fail_on_error="${FRONTEND_BUILD_FAIL_ON_ERROR:-}"

    # Backward compatibility:
    # - FRONTEND_BUILD_MODE takes precedence when set.
    # - Otherwise, retain FRONTEND_BUILD_ON_START behavior.
    if [ -z "${mode}" ]; then
        if [ "${FRONTEND_BUILD_ON_START:-true}" = "true" ]; then
            mode="auto"
        else
            mode="never"
        fi
    fi
    mode="$(echo "${mode}" | tr '[:upper:]' '[:lower:]')"

    if [ -z "${fail_on_error}" ]; then
        if [ "$(echo "${FLASK_ENV:-development}" | tr '[:upper:]' '[:lower:]')" = "production" ]; then
            fail_on_error="true"
        else
            fail_on_error="false"
        fi
    fi

    if [ "${mode}" = "never" ]; then
        log_info "Skip frontend build (FRONTEND_BUILD_MODE=${mode})"
        return 0
    fi
    if [ "${mode}" != "auto" ] && [ "${mode}" != "always" ]; then
        log_warn "Invalid FRONTEND_BUILD_MODE='${mode}', fallback to auto"
        mode="auto"
    fi

    if [ ! -f "${ROOT}/frontend/package.json" ]; then
        return 0
    fi

    if ! command -v npm &> /dev/null; then
        log_warn "npm not found, skip frontend build"
        return 0
    fi

    local needs_build=true
    if [ "${mode}" = "auto" ]; then
        local required_entries=(
            "portal.js"
            "wip-overview.js"
            "wip-detail.js"
            "hold-detail.js"
            "hold-overview.js"
            "hold-history.js"
            "resource-status.js"
            "resource-history.js"
            "job-query.js"
            "excel-query.js"
            "tables.js"
            "query-tool.js"
            "qc-gate.js"
            "mid-section-defect.js"
        )
        needs_build=false
        local newest_entry=""

        for entry in "${required_entries[@]}"; do
            local entry_path="${ROOT}/src/mes_dashboard/static/dist/${entry}"
            if [ ! -f "${entry_path}" ]; then
                needs_build=true
                break
            fi
            if [ -z "${newest_entry}" ] || [ "${entry_path}" -nt "${newest_entry}" ]; then
                newest_entry="${entry_path}"
            fi
        done

        if [ "$needs_build" = false ] && find "${ROOT}/frontend/src" -type f -newer "${newest_entry}" | grep -q .; then
            needs_build=true
        fi
        if [ "$needs_build" = false ] && ([ "${ROOT}/frontend/package.json" -nt "${newest_entry}" ] || [ "${ROOT}/frontend/vite.config.js" -nt "${newest_entry}" ]); then
            needs_build=true
        fi

        if [ "$needs_build" = false ]; then
            log_success "Frontend assets are up to date (FRONTEND_BUILD_MODE=auto)"
            return 0
        fi
    fi

    log_info "Building frontend assets with Vite (FRONTEND_BUILD_MODE=${mode})..."
    if npm --prefix "${ROOT}/frontend" run build >/dev/null 2>&1; then
        log_success "Frontend assets built"
    else
        if is_enabled "${fail_on_error}"; then
            log_error "Frontend build failed; aborting startup (FRONTEND_BUILD_FAIL_ON_ERROR=${fail_on_error})"
            return 1
        fi
        log_warn "Frontend build failed; continuing startup (FRONTEND_BUILD_FAIL_ON_ERROR=${fail_on_error})"
    fi
}

# ============================================================
# Redis Management Functions
# ============================================================
check_redis() {
    if [ "$REDIS_ENABLED" != "true" ]; then
        log_info "Redis is disabled (REDIS_ENABLED=${REDIS_ENABLED})"
        return 0
    fi

    if ! command -v redis-cli &> /dev/null; then
        log_warn "Redis CLI not found (Redis features will be disabled)"
        return 0
    fi

    if redis-cli ping &>/dev/null; then
        log_success "Redis connection OK"
        return 0
    else
        log_warn "Redis not responding (will attempt to start)"
        return 1
    fi
}

apply_redis_runtime_config() {
    if [ "$REDIS_ENABLED" != "true" ]; then
        return 0
    fi
    if ! command -v redis-cli &> /dev/null; then
        return 0
    fi
    if ! redis-cli ping &>/dev/null; then
        return 0
    fi

    local configured=0

    if [ -n "${REDIS_MAXMEMORY:-}" ] && [ "${REDIS_MAXMEMORY}" != "0" ]; then
        if redis-cli CONFIG SET maxmemory "${REDIS_MAXMEMORY}" >/dev/null 2>&1; then
            configured=$((configured + 1))
        else
            log_warn "Failed to set Redis maxmemory=${REDIS_MAXMEMORY}"
        fi
    fi

    if [ -n "${REDIS_MAXMEMORY_POLICY:-}" ]; then
        if redis-cli CONFIG SET maxmemory-policy "${REDIS_MAXMEMORY_POLICY}" >/dev/null 2>&1; then
            configured=$((configured + 1))
        else
            log_warn "Failed to set Redis maxmemory-policy=${REDIS_MAXMEMORY_POLICY}"
        fi
    fi

    if is_enabled "${REDIS_PERSISTENCE_ENABLED:-true}"; then
        if redis-cli CONFIG SET appendonly "${REDIS_APPENDONLY}" >/dev/null 2>&1; then
            configured=$((configured + 1))
        else
            log_warn "Failed to set Redis appendonly=${REDIS_APPENDONLY}"
        fi
        if redis-cli CONFIG SET appendfsync "${REDIS_APPENDFSYNC}" >/dev/null 2>&1; then
            configured=$((configured + 1))
        else
            log_warn "Failed to set Redis appendfsync=${REDIS_APPENDFSYNC}"
        fi
        if [ -n "${REDIS_SAVE:-}" ]; then
            if redis-cli CONFIG SET save "${REDIS_SAVE}" >/dev/null 2>&1; then
                configured=$((configured + 1))
            else
                log_warn "Failed to set Redis save='${REDIS_SAVE}'"
            fi
        fi
    fi

    if redis-cli CONFIG REWRITE >/dev/null 2>&1; then
        configured=$((configured + 1))
    else
        log_warn "Redis CONFIG REWRITE failed (runtime config is active but may not persist restart)"
    fi

    if [ "$configured" -gt 0 ]; then
        log_info "Redis runtime config applied (maxmemory=${REDIS_MAXMEMORY}, policy=${REDIS_MAXMEMORY_POLICY}, appendonly=${REDIS_APPENDONLY})"
    fi
}

cleanup_redis_keys_without_ttl() {
    if [ "$REDIS_ENABLED" != "true" ]; then
        return 0
    fi
    if ! command -v redis-cli &> /dev/null; then
        return 0
    fi
    if ! redis-cli ping &>/dev/null; then
        return 0
    fi
    if ! is_enabled "${REDIS_TTL_CLEANUP_ON_START:-true}"; then
        return 0
    fi

    local deleted=0
    local raw_pattern
    for raw_pattern in ${REDIS_TTL_CLEANUP_PATTERNS//,/ }; do
        local full_pattern="${REDIS_KEY_PREFIX}:${raw_pattern}"
        while IFS= read -r key; do
            [ -z "${key}" ] && continue
            local pttl
            pttl=$(redis-cli PTTL "${key}" 2>/dev/null || echo "-2")
            if [[ "${pttl}" =~ ^-?[0-9]+$ ]] && [ "${pttl}" -lt 0 ]; then
                if redis-cli DEL "${key}" >/dev/null 2>&1; then
                    deleted=$((deleted + 1))
                fi
            fi
        done < <(redis-cli --scan --pattern "${full_pattern}" 2>/dev/null)
    done

    if [ "$deleted" -gt 0 ]; then
        log_info "Redis TTL cleanup removed ${deleted} stale keys without expiry"
    fi
}

start_redis() {
    if [ "$REDIS_ENABLED" != "true" ]; then
        return 0
    fi

    if ! command -v redis-cli &> /dev/null; then
        return 0
    fi

    # Check if Redis is already running
    if redis-cli ping &>/dev/null; then
        log_success "Redis is already running"
        apply_redis_runtime_config
        cleanup_redis_keys_without_ttl
        return 0
    fi

    # Try to start Redis via systemctl
    if command -v systemctl &> /dev/null; then
        log_info "Starting Redis service..."
        if sudo systemctl start redis-server 2>/dev/null; then
            sleep 1
            if redis-cli ping &>/dev/null; then
                log_success "Redis service started"
                apply_redis_runtime_config
                cleanup_redis_keys_without_ttl
                return 0
            fi
        fi
    fi

    log_warn "Could not start Redis (fallback mode will be used)"
    return 0
}

stop_redis() {
    if [ "$REDIS_ENABLED" != "true" ]; then
        return 0
    fi

    if ! command -v redis-cli &> /dev/null; then
        return 0
    fi

    # Check if Redis is running
    if ! redis-cli ping &>/dev/null; then
        log_info "Redis is not running"
        return 0
    fi

    # Stop Redis via systemctl
    if command -v systemctl &> /dev/null; then
        log_info "Stopping Redis service..."
        if sudo systemctl stop redis-server 2>/dev/null; then
            log_success "Redis service stopped"
            return 0
        fi
    fi

    log_warn "Could not stop Redis service"
    return 0
}

redis_status() {
    if [ "$REDIS_ENABLED" != "true" ]; then
        echo -e "  Redis:   ${YELLOW}DISABLED${NC}"
        return 0
    fi

    if ! command -v redis-cli &> /dev/null; then
        echo -e "  Redis:   ${YELLOW}NOT INSTALLED${NC}"
        return 0
    fi

    if redis-cli ping &>/dev/null; then
        local info=$(redis-cli info memory 2>/dev/null | grep "used_memory_human" | cut -d: -f2 | tr -d '\r')
        echo -e "  Redis:   ${GREEN}RUNNING${NC} (Memory: ${info:-unknown})"
    else
        echo -e "  Redis:   ${RED}STOPPED${NC}"
    fi
}

run_all_checks() {
    log_info "Running environment checks..."
    echo ""

    check_conda || return 1
    check_dependencies || return 1
    check_env_file
    load_env
    resolve_runtime_paths
    validate_runtime_contract || return 1
    check_port || return 1
    check_database
    check_redis

    echo ""
    log_success "All checks passed"
    return 0
}

# ============================================================
# Service Management Functions
# ============================================================
ensure_dirs() {
    mkdir -p "${LOG_DIR}"
    mkdir -p "${LOG_DIR}/archive"
    mkdir -p "$(dirname "${PID_FILE}")"
    mkdir -p "${WATCHDOG_RUNTIME_DIR}"
}

rotate_logs() {
    # Archive existing logs with timestamp before starting new session
    local ts=$(date '+%Y%m%d_%H%M%S')

    if [ -f "$ACCESS_LOG" ] && [ -s "$ACCESS_LOG" ]; then
        mv "$ACCESS_LOG" "${LOG_DIR}/archive/access_${ts}.log"
        log_info "Archived access.log -> archive/access_${ts}.log"
    fi

    if [ -f "$ERROR_LOG" ] && [ -s "$ERROR_LOG" ]; then
        mv "$ERROR_LOG" "${LOG_DIR}/archive/error_${ts}.log"
        log_info "Archived error.log -> archive/error_${ts}.log"
    fi

    if [ -f "$WATCHDOG_LOG" ] && [ -s "$WATCHDOG_LOG" ]; then
        mv "$WATCHDOG_LOG" "${LOG_DIR}/archive/watchdog_${ts}.log"
        log_info "Archived watchdog.log -> archive/watchdog_${ts}.log"
    fi

    if [ -f "$RQ_WORKER_LOG" ] && [ -s "$RQ_WORKER_LOG" ]; then
        mv "$RQ_WORKER_LOG" "${LOG_DIR}/archive/rq_worker_${ts}.log"
        log_info "Archived rq_worker.log -> archive/rq_worker_${ts}.log"
    fi

    if [ -f "$RQ_REJECT_WORKER_LOG" ] && [ -s "$RQ_REJECT_WORKER_LOG" ]; then
        mv "$RQ_REJECT_WORKER_LOG" "${LOG_DIR}/archive/rq_reject_worker_${ts}.log"
        log_info "Archived rq_reject_worker.log -> archive/rq_reject_worker_${ts}.log"
    fi

    if [ -f "$RQ_MSD_WORKER_LOG" ] && [ -s "$RQ_MSD_WORKER_LOG" ]; then
        mv "$RQ_MSD_WORKER_LOG" "${LOG_DIR}/archive/rq_msd_worker_${ts}.log"
        log_info "Archived rq_msd_worker.log -> archive/rq_msd_worker_${ts}.log"
    fi

    if [ -f "$RQ_PROD_HIST_WORKER_LOG" ] && [ -s "$RQ_PROD_HIST_WORKER_LOG" ]; then
        mv "$RQ_PROD_HIST_WORKER_LOG" "${LOG_DIR}/archive/rq_prod_hist_worker_${ts}.log"
        log_info "Archived rq_prod_hist_worker.log -> archive/rq_prod_hist_worker_${ts}.log"
    fi

    if [ -f "$RQ_YIELD_ALERT_WORKER_LOG" ] && [ -s "$RQ_YIELD_ALERT_WORKER_LOG" ]; then
        mv "$RQ_YIELD_ALERT_WORKER_LOG" "${LOG_DIR}/archive/rq_yield_alert_worker_${ts}.log"
        log_info "Archived rq_yield_alert_worker.log -> archive/rq_yield_alert_worker_${ts}.log"
    fi

    if [ -f "$RQ_HOLD_HIST_WORKER_LOG" ] && [ -s "$RQ_HOLD_HIST_WORKER_LOG" ]; then
        mv "$RQ_HOLD_HIST_WORKER_LOG" "${LOG_DIR}/archive/rq_hold_hist_worker_${ts}.log"
        log_info "Archived rq_hold_hist_worker.log -> archive/rq_hold_hist_worker_${ts}.log"
    fi

    if [ -f "$RQ_WARMUP_WORKER_LOG" ] && [ -s "$RQ_WARMUP_WORKER_LOG" ]; then
        mv "$RQ_WARMUP_WORKER_LOG" "${LOG_DIR}/archive/rq_warmup_worker_${ts}.log"
        log_info "Archived rq_warmup_worker.log -> archive/rq_warmup_worker_${ts}.log"
    fi

    # Clean up old archives (keep last 10)
    cd "${LOG_DIR}/archive" 2>/dev/null && \
        ls -t access_*.log 2>/dev/null | tail -n +11 | xargs -r rm -f && \
        ls -t error_*.log 2>/dev/null | tail -n +11 | xargs -r rm -f && \
        ls -t watchdog_*.log 2>/dev/null | tail -n +11 | xargs -r rm -f && \
        ls -t rq_worker_*.log 2>/dev/null | tail -n +11 | xargs -r rm -f && \
        ls -t rq_reject_worker_*.log 2>/dev/null | tail -n +11 | xargs -r rm -f && \
        ls -t rq_msd_worker_*.log 2>/dev/null | tail -n +11 | xargs -r rm -f && \
        ls -t rq_prod_hist_worker_*.log 2>/dev/null | tail -n +11 | xargs -r rm -f && \
        ls -t rq_yield_alert_worker_*.log 2>/dev/null | tail -n +11 | xargs -r rm -f && \
        ls -t rq_hold_hist_worker_*.log 2>/dev/null | tail -n +11 | xargs -r rm -f && \
        ls -t rq_warmup_worker_*.log 2>/dev/null | tail -n +11 | xargs -r rm -f
    cd "$ROOT"

    # Create fresh log files
    touch "$ACCESS_LOG" "$ERROR_LOG" "$WATCHDOG_LOG"
}

get_pid() {
    if [ -f "$PID_FILE" ]; then
        local pid=$(cat "$PID_FILE" 2>/dev/null)
        if [ -n "$pid" ] && kill -0 "$pid" 2>/dev/null; then
            echo "$pid"
            return 0
        fi
    fi

    # Fallback: find by port
    local pid=$(lsof -t -i ":${PORT}" -sTCP:LISTEN 2>/dev/null | head -1)
    if [ -n "$pid" ]; then
        echo "$pid"
        return 0
    fi

    return 1
}

is_running() {
    get_pid &>/dev/null
}

get_watchdog_pid() {
    if [ -f "$WATCHDOG_PROCESS_PID_FILE" ]; then
        local pid
        pid=$(cat "$WATCHDOG_PROCESS_PID_FILE" 2>/dev/null || true)
        if [ -n "$pid" ] && kill -0 "$pid" 2>/dev/null; then
            echo "$pid"
            return 0
        fi
        rm -f "$WATCHDOG_PROCESS_PID_FILE"
    fi

    # Fallback: discover watchdog process even if PID file is missing/stale
    local discovered_pid
    discovered_pid=$(pgrep -f "[p]ython .*scripts/worker_watchdog.py" 2>/dev/null | head -1 || true)
    if [ -n "${discovered_pid}" ] && kill -0 "${discovered_pid}" 2>/dev/null; then
        echo "${discovered_pid}" > "$WATCHDOG_PROCESS_PID_FILE"
        echo "${discovered_pid}"
        return 0
    fi

    return 1
}

is_watchdog_running() {
    get_watchdog_pid &>/dev/null
}

start_watchdog() {
    if ! is_enabled "${WATCHDOG_ENABLED:-true}"; then
        log_info "Worker watchdog is disabled (WATCHDOG_ENABLED=${WATCHDOG_ENABLED})"
        return 0
    fi

    if is_watchdog_running; then
        local pid
        pid=$(get_watchdog_pid)
        log_success "Worker watchdog already running (PID: ${pid})"
        return 0
    fi

    log_info "Starting worker watchdog..."
    if command -v setsid >/dev/null 2>&1; then
        # Start watchdog in its own session so it survives non-interactive shell teardown.
        setsid python scripts/worker_watchdog.py >> "$WATCHDOG_LOG" 2>&1 < /dev/null &
    else
        nohup python scripts/worker_watchdog.py >> "$WATCHDOG_LOG" 2>&1 < /dev/null &
    fi
    local pid=$!
    echo "$pid" > "$WATCHDOG_PROCESS_PID_FILE"

    sleep 1
    if kill -0 "$pid" 2>/dev/null; then
        log_success "Worker watchdog started (PID: ${pid})"
        return 0
    fi

    rm -f "$WATCHDOG_PROCESS_PID_FILE"
    log_error "Failed to start worker watchdog"
    return 1
}

stop_watchdog() {
    if ! is_watchdog_running; then
        rm -f "$WATCHDOG_PROCESS_PID_FILE"
        return 0
    fi

    local pid
    pid=$(get_watchdog_pid)
    log_info "Stopping worker watchdog (PID: ${pid})..."
    kill -TERM "$pid" 2>/dev/null || true

    local count=0
    while kill -0 "$pid" 2>/dev/null && [ $count -lt 5 ]; do
        sleep 1
        count=$((count + 1))
    done

    if kill -0 "$pid" 2>/dev/null; then
        kill -9 "$pid" 2>/dev/null || true
        sleep 1
    fi

    rm -f "$WATCHDOG_PROCESS_PID_FILE"
    if kill -0 "$pid" 2>/dev/null; then
        log_error "Failed to stop worker watchdog"
        return 1
    fi

    log_success "Worker watchdog stopped"
    return 0
}

# ============================================================
# RQ Trace Worker Management Functions
# ============================================================
get_rq_worker_pid() {
    if [ -f "$RQ_WORKER_PID_FILE" ]; then
        local pid
        pid=$(cat "$RQ_WORKER_PID_FILE" 2>/dev/null || true)
        if [ -n "$pid" ] && kill -0 "$pid" 2>/dev/null; then
            echo "$pid"
            return 0
        fi
        rm -f "$RQ_WORKER_PID_FILE"
    fi

    local discovered_pid
    discovered_pid=$(pgrep -f "[r]q worker.*${TRACE_WORKER_QUEUE}" 2>/dev/null | head -1 || true)
    if [ -n "${discovered_pid}" ] && kill -0 "${discovered_pid}" 2>/dev/null; then
        echo "${discovered_pid}" > "$RQ_WORKER_PID_FILE"
        echo "${discovered_pid}"
        return 0
    fi

    return 1
}

is_rq_worker_running() {
    get_rq_worker_pid &>/dev/null
}

start_rq_worker() {
    if ! is_enabled "${TRACE_WORKER_ENABLED:-false}"; then
        log_info "RQ trace worker is disabled (TRACE_WORKER_ENABLED=${TRACE_WORKER_ENABLED:-false})"
        return 0
    fi

    if [ "$REDIS_ENABLED" != "true" ]; then
        log_warn "Redis is disabled; cannot start RQ trace worker"
        return 0
    fi

    if is_rq_worker_running; then
        local pid
        pid=$(get_rq_worker_pid)
        log_success "RQ trace worker already running (PID: ${pid})"
        return 0
    fi

    # Check if rq is installed
    if ! python -c "import rq" 2>/dev/null; then
        log_warn "rq package not installed; skip trace worker (pip install rq)"
        return 0
    fi

    log_info "Starting RQ trace worker (queue: ${TRACE_WORKER_QUEUE})..."
    local redis_url="${REDIS_URL:-redis://localhost:6379/0}"
    if command -v setsid >/dev/null 2>&1; then
        setsid env DB_POOL_SIZE=2 DB_MAX_OVERFLOW=1 rq worker "${TRACE_WORKER_QUEUE}" --url "${redis_url}" -P src -c mes_dashboard.rq_worker_preload --log-format "${RQ_LOG_FORMAT}" --date-format "${RQ_DATE_FORMAT}" >> "$RQ_WORKER_LOG" 2>&1 < /dev/null &
    else
        env DB_POOL_SIZE=2 DB_MAX_OVERFLOW=1 nohup rq worker "${TRACE_WORKER_QUEUE}" --url "${redis_url}" -P src -c mes_dashboard.rq_worker_preload --log-format "${RQ_LOG_FORMAT}" --date-format "${RQ_DATE_FORMAT}" >> "$RQ_WORKER_LOG" 2>&1 < /dev/null &
    fi
    local pid=$!
    echo "$pid" > "$RQ_WORKER_PID_FILE"

    sleep 1
    if kill -0 "$pid" 2>/dev/null; then
        log_success "RQ trace worker started (PID: ${pid})"
        return 0
    fi

    rm -f "$RQ_WORKER_PID_FILE"
    log_error "Failed to start RQ trace worker"
    return 1
}

stop_rq_worker() {
    if ! is_rq_worker_running; then
        rm -f "$RQ_WORKER_PID_FILE"
        return 0
    fi

    local pid
    pid=$(get_rq_worker_pid)
    log_info "Stopping RQ trace worker (PID: ${pid})..."
    kill -TERM "$pid" 2>/dev/null || true

    local count=0
    while kill -0 "$pid" 2>/dev/null && [ $count -lt 10 ]; do
        sleep 1
        count=$((count + 1))
    done

    if kill -0 "$pid" 2>/dev/null; then
        kill -9 "$pid" 2>/dev/null || true
        sleep 1
    fi

    rm -f "$RQ_WORKER_PID_FILE"
    if kill -0 "$pid" 2>/dev/null; then
        log_error "Failed to stop RQ trace worker"
        return 1
    fi

    log_success "RQ trace worker stopped"
    return 0
}

rq_worker_status() {
    if ! is_enabled "${TRACE_WORKER_ENABLED:-false}"; then
        echo -e "  RQ Worker:${YELLOW} DISABLED${NC}"
        return 0
    fi

    if is_rq_worker_running; then
        local pid=$(get_rq_worker_pid)
        echo -e "  RQ Worker:${GREEN} RUNNING${NC} (PID: ${pid}, queue: ${TRACE_WORKER_QUEUE})"
    else
        echo -e "  RQ Worker:${RED} STOPPED${NC}"
    fi
}

# ---------------------------------------------------------------------------
# RQ Reject Query Worker functions (independent from trace worker)
# ---------------------------------------------------------------------------
get_rq_reject_worker_pid() {
    local saved_pid=""
    if [ -f "${RQ_REJECT_WORKER_PID_FILE:-}" ]; then
        saved_pid=$(cat "${RQ_REJECT_WORKER_PID_FILE}" 2>/dev/null || true)
        if [ -n "$saved_pid" ] && kill -0 "$saved_pid" 2>/dev/null; then
            echo "$saved_pid"
            return 0
        fi
    fi
    local discovered_pid
    discovered_pid=$(pgrep -f "[r]q worker.*${RQ_REJECT_WORKER_QUEUE}" 2>/dev/null | head -1 || true)
    if [ -n "$discovered_pid" ]; then
        echo "$discovered_pid"
        return 0
    fi
    return 1
}

is_rq_reject_worker_running() {
    get_rq_reject_worker_pid &>/dev/null
}

start_rq_reject_worker() {
    if ! is_enabled "${RQ_REJECT_WORKER_ENABLED:-true}"; then
        log_info "RQ reject worker is disabled (RQ_REJECT_WORKER_ENABLED=${RQ_REJECT_WORKER_ENABLED:-true})"
        return 0
    fi

    resolve_runtime_paths

    if is_rq_reject_worker_running; then
        local pid
        pid=$(get_rq_reject_worker_pid)
        log_info "RQ reject worker already running (PID: ${pid})"
        return 0
    fi

    local redis_url="redis://127.0.0.1:6379/0"
    if [ -n "${REDIS_URL:-}" ]; then
        redis_url="${REDIS_URL}"
    fi

    log_info "Starting RQ reject worker (queue: ${RQ_REJECT_WORKER_QUEUE})..."

    if command -v setsid &>/dev/null; then
        setsid env DB_POOL_SIZE=2 DB_MAX_OVERFLOW=1 rq worker "${RQ_REJECT_WORKER_QUEUE}" --url "${redis_url}" -P src -c mes_dashboard.rq_worker_preload --log-format "${RQ_LOG_FORMAT}" --date-format "${RQ_DATE_FORMAT}" >> "${RQ_REJECT_WORKER_LOG}" 2>&1 < /dev/null &
    else
        env DB_POOL_SIZE=2 DB_MAX_OVERFLOW=1 nohup rq worker "${RQ_REJECT_WORKER_QUEUE}" --url "${redis_url}" -P src -c mes_dashboard.rq_worker_preload --log-format "${RQ_LOG_FORMAT}" --date-format "${RQ_DATE_FORMAT}" >> "${RQ_REJECT_WORKER_LOG}" 2>&1 < /dev/null &
    fi
    local worker_pid=$!
    echo "$worker_pid" > "${RQ_REJECT_WORKER_PID_FILE}"
    sleep 1
    if kill -0 "$worker_pid" 2>/dev/null; then
        log_success "RQ reject worker started (PID: ${worker_pid}, queue: ${RQ_REJECT_WORKER_QUEUE})"
        return 0
    else
        log_error "RQ reject worker failed to start"
        return 1
    fi
}

stop_rq_reject_worker() {
    if ! is_rq_reject_worker_running; then
        log_info "RQ reject worker is not running"
        return 0
    fi

    local pid
    pid=$(get_rq_reject_worker_pid)
    log_info "Stopping RQ reject worker (PID: ${pid})..."
    if kill "$pid" 2>/dev/null; then
        local wait=0
        while kill -0 "$pid" 2>/dev/null && [ "$wait" -lt 10 ]; do
            sleep 1
            wait=$((wait+1))
        done
        if kill -0 "$pid" 2>/dev/null; then
            kill -9 "$pid" 2>/dev/null || true
        fi
        rm -f "${RQ_REJECT_WORKER_PID_FILE:-}" 2>/dev/null || true
        log_success "RQ reject worker stopped"
        return 0
    else
        log_error "Failed to stop RQ reject worker"
        return 1
    fi
}

rq_reject_worker_status() {
    if ! is_enabled "${RQ_REJECT_WORKER_ENABLED:-true}"; then
        echo -e "  RQ Reject Worker:${YELLOW} DISABLED${NC}"
        return 0
    fi

    if is_rq_reject_worker_running; then
        local pid
        pid=$(get_rq_reject_worker_pid)
        echo -e "  RQ Reject Worker:${GREEN} RUNNING${NC} (PID: ${pid}, queue: ${RQ_REJECT_WORKER_QUEUE})"
    else
        echo -e "  RQ Reject Worker:${RED} STOPPED${NC}"
    fi
}

# ---------------------------------------------------------------------------
# RQ MSD Analysis Worker functions
# ---------------------------------------------------------------------------
get_rq_msd_worker_pid() {
    local saved_pid=""
    if [ -f "${RQ_MSD_WORKER_PID_FILE:-}" ]; then
        saved_pid=$(cat "${RQ_MSD_WORKER_PID_FILE}" 2>/dev/null || true)
        if [ -n "$saved_pid" ] && kill -0 "$saved_pid" 2>/dev/null; then
            echo "$saved_pid"
            return 0
        fi
    fi
    local discovered_pid
    discovered_pid=$(pgrep -f "[r]q worker.*${RQ_MSD_WORKER_QUEUE}" 2>/dev/null | head -1 || true)
    if [ -n "$discovered_pid" ]; then
        echo "$discovered_pid"
        return 0
    fi
    return 1
}

is_rq_msd_worker_running() {
    get_rq_msd_worker_pid &>/dev/null
}

start_rq_msd_worker() {
    if ! is_enabled "${RQ_MSD_WORKER_ENABLED:-true}"; then
        log_info "RQ msd worker is disabled (RQ_MSD_WORKER_ENABLED=${RQ_MSD_WORKER_ENABLED:-true})"
        return 0
    fi

    resolve_runtime_paths

    if is_rq_msd_worker_running; then
        local pid
        pid=$(get_rq_msd_worker_pid)
        log_info "RQ msd worker already running (PID: ${pid})"
        return 0
    fi

    local redis_url="redis://127.0.0.1:6379/0"
    if [ -n "${REDIS_URL:-}" ]; then
        redis_url="${REDIS_URL}"
    fi

    log_info "Starting RQ msd worker (queue: ${RQ_MSD_WORKER_QUEUE})..."

    if command -v setsid &>/dev/null; then
        setsid env DB_POOL_SIZE=2 DB_MAX_OVERFLOW=1 rq worker "${RQ_MSD_WORKER_QUEUE}" --url "${redis_url}" -P src -c mes_dashboard.rq_worker_preload --log-format "${RQ_LOG_FORMAT}" --date-format "${RQ_DATE_FORMAT}" >> "${RQ_MSD_WORKER_LOG}" 2>&1 < /dev/null &
    else
        env DB_POOL_SIZE=2 DB_MAX_OVERFLOW=1 nohup rq worker "${RQ_MSD_WORKER_QUEUE}" --url "${redis_url}" -P src -c mes_dashboard.rq_worker_preload --log-format "${RQ_LOG_FORMAT}" --date-format "${RQ_DATE_FORMAT}" >> "${RQ_MSD_WORKER_LOG}" 2>&1 < /dev/null &
    fi
    local worker_pid=$!
    echo "$worker_pid" > "${RQ_MSD_WORKER_PID_FILE}"
    sleep 1
    if kill -0 "$worker_pid" 2>/dev/null; then
        log_success "RQ msd worker started (PID: ${worker_pid}, queue: ${RQ_MSD_WORKER_QUEUE})"
        return 0
    else
        log_error "RQ msd worker failed to start"
        return 1
    fi
}

stop_rq_msd_worker() {
    if ! is_rq_msd_worker_running; then
        log_info "RQ msd worker is not running"
        return 0
    fi

    local pid
    pid=$(get_rq_msd_worker_pid)
    log_info "Stopping RQ msd worker (PID: ${pid})..."
    if kill "$pid" 2>/dev/null; then
        local wait=0
        while kill -0 "$pid" 2>/dev/null && [ "$wait" -lt 10 ]; do
            sleep 1
            wait=$((wait+1))
        done
        if kill -0 "$pid" 2>/dev/null; then
            kill -9 "$pid" 2>/dev/null || true
        fi
        rm -f "${RQ_MSD_WORKER_PID_FILE:-}" 2>/dev/null || true
        log_success "RQ msd worker stopped"
        return 0
    else
        log_error "Failed to stop RQ msd worker"
        return 1
    fi
}

rq_msd_worker_status() {
    if ! is_enabled "${RQ_MSD_WORKER_ENABLED:-true}"; then
        echo -e "  RQ MSD Worker:${YELLOW} DISABLED${NC}"
        return 0
    fi

    if is_rq_msd_worker_running; then
        local pid
        pid=$(get_rq_msd_worker_pid)
        echo -e "  RQ MSD Worker:${GREEN} RUNNING${NC} (PID: ${pid}, queue: ${RQ_MSD_WORKER_QUEUE})"
    else
        echo -e "  RQ MSD Worker:${RED} STOPPED${NC}"
    fi
}

# ---------------------------------------------------------------------------
# RQ Production History Worker functions
# ---------------------------------------------------------------------------
get_rq_prod_hist_worker_pid() {
    local saved_pid=""
    if [ -f "${RQ_PROD_HIST_WORKER_PID_FILE:-}" ]; then
        saved_pid=$(cat "${RQ_PROD_HIST_WORKER_PID_FILE}" 2>/dev/null || true)
        if [ -n "$saved_pid" ] && kill -0 "$saved_pid" 2>/dev/null; then
            echo "$saved_pid"
            return 0
        fi
    fi
    local discovered_pid
    discovered_pid=$(pgrep -f "[r]q worker.*${RQ_PRODUCTION_HISTORY_WORKER_QUEUE}" 2>/dev/null | head -1 || true)
    if [ -n "$discovered_pid" ]; then
        echo "$discovered_pid"
        return 0
    fi
    return 1
}

is_rq_prod_hist_worker_running() {
    get_rq_prod_hist_worker_pid &>/dev/null
}

start_rq_prod_hist_worker() {
    if ! is_enabled "${RQ_PRODUCTION_HISTORY_WORKER_ENABLED:-true}"; then
        log_info "RQ production-history worker is disabled (RQ_PRODUCTION_HISTORY_WORKER_ENABLED=${RQ_PRODUCTION_HISTORY_WORKER_ENABLED:-true})"
        return 0
    fi

    resolve_runtime_paths

    if is_rq_prod_hist_worker_running; then
        local pid
        pid=$(get_rq_prod_hist_worker_pid)
        log_info "RQ production-history worker already running (PID: ${pid})"
        return 0
    fi

    local redis_url="redis://127.0.0.1:6379/0"
    if [ -n "${REDIS_URL:-}" ]; then
        redis_url="${REDIS_URL}"
    fi

    log_info "Starting RQ production-history worker (queue: ${RQ_PRODUCTION_HISTORY_WORKER_QUEUE})..."

    if command -v setsid &>/dev/null; then
        setsid env DB_POOL_SIZE=2 DB_MAX_OVERFLOW=1 rq worker "${RQ_PRODUCTION_HISTORY_WORKER_QUEUE}" --url "${redis_url}" -P src -c mes_dashboard.rq_worker_preload --log-format "${RQ_LOG_FORMAT}" --date-format "${RQ_DATE_FORMAT}" >> "${RQ_PROD_HIST_WORKER_LOG}" 2>&1 < /dev/null &
    else
        env DB_POOL_SIZE=2 DB_MAX_OVERFLOW=1 nohup rq worker "${RQ_PRODUCTION_HISTORY_WORKER_QUEUE}" --url "${redis_url}" -P src -c mes_dashboard.rq_worker_preload --log-format "${RQ_LOG_FORMAT}" --date-format "${RQ_DATE_FORMAT}" >> "${RQ_PROD_HIST_WORKER_LOG}" 2>&1 < /dev/null &
    fi
    local worker_pid=$!
    echo "$worker_pid" > "${RQ_PROD_HIST_WORKER_PID_FILE}"
    sleep 1
    if kill -0 "$worker_pid" 2>/dev/null; then
        log_success "RQ production-history worker started (PID: ${worker_pid}, queue: ${RQ_PRODUCTION_HISTORY_WORKER_QUEUE})"
        return 0
    else
        log_error "RQ production-history worker failed to start"
        return 1
    fi
}

stop_rq_prod_hist_worker() {
    if ! is_rq_prod_hist_worker_running; then
        log_info "RQ production-history worker is not running"
        return 0
    fi

    local pid
    pid=$(get_rq_prod_hist_worker_pid)
    log_info "Stopping RQ production-history worker (PID: ${pid})..."
    if kill "$pid" 2>/dev/null; then
        local wait=0
        while kill -0 "$pid" 2>/dev/null && [ "$wait" -lt 10 ]; do
            sleep 1
            wait=$((wait+1))
        done
        if kill -0 "$pid" 2>/dev/null; then
            kill -9 "$pid" 2>/dev/null || true
        fi
        rm -f "${RQ_PROD_HIST_WORKER_PID_FILE:-}" 2>/dev/null || true
        log_success "RQ production-history worker stopped"
        return 0
    else
        log_error "Failed to stop RQ production-history worker"
        return 1
    fi
}

rq_prod_hist_worker_status() {
    if ! is_enabled "${RQ_PRODUCTION_HISTORY_WORKER_ENABLED:-true}"; then
        echo -e "  RQ Prod-Hist Worker:${YELLOW} DISABLED${NC}"
        return 0
    fi

    if is_rq_prod_hist_worker_running; then
        local pid
        pid=$(get_rq_prod_hist_worker_pid)
        echo -e "  RQ Prod-Hist Worker:${GREEN} RUNNING${NC} (PID: ${pid}, queue: ${RQ_PRODUCTION_HISTORY_WORKER_QUEUE})"
    else
        echo -e "  RQ Prod-Hist Worker:${RED} STOPPED${NC}"
    fi
}

# ---------------------------------------------------------------------------
# RQ Yield Alert Worker functions
# ---------------------------------------------------------------------------
get_rq_yield_alert_worker_pid() {
    local saved_pid=""
    if [ -f "${RQ_YIELD_ALERT_WORKER_PID_FILE:-}" ]; then
        saved_pid=$(cat "${RQ_YIELD_ALERT_WORKER_PID_FILE}" 2>/dev/null || true)
        if [ -n "$saved_pid" ] && kill -0 "$saved_pid" 2>/dev/null; then
            echo "$saved_pid"
            return 0
        fi
    fi
    local discovered_pid
    discovered_pid=$(pgrep -f "[r]q worker.*${RQ_YIELD_ALERT_WORKER_QUEUE}" 2>/dev/null | head -1 || true)
    if [ -n "$discovered_pid" ]; then
        echo "$discovered_pid"
        return 0
    fi
    return 1
}

is_rq_yield_alert_worker_running() {
    get_rq_yield_alert_worker_pid &>/dev/null
}

start_rq_yield_alert_worker() {
    if ! is_enabled "${RQ_YIELD_ALERT_WORKER_ENABLED:-true}"; then
        log_info "RQ yield-alert worker is disabled (RQ_YIELD_ALERT_WORKER_ENABLED=${RQ_YIELD_ALERT_WORKER_ENABLED:-true})"
        return 0
    fi

    resolve_runtime_paths

    if is_rq_yield_alert_worker_running; then
        local pid
        pid=$(get_rq_yield_alert_worker_pid)
        log_info "RQ yield-alert worker already running (PID: ${pid})"
        return 0
    fi

    local redis_url="redis://127.0.0.1:6379/0"
    if [ -n "${REDIS_URL:-}" ]; then
        redis_url="${REDIS_URL}"
    fi

    log_info "Starting RQ yield-alert worker (queue: ${RQ_YIELD_ALERT_WORKER_QUEUE})..."

    if command -v setsid &>/dev/null; then
        setsid env DB_POOL_SIZE=2 DB_MAX_OVERFLOW=1 rq worker "${RQ_YIELD_ALERT_WORKER_QUEUE}" --url "${redis_url}" -P src -c mes_dashboard.rq_worker_preload --log-format "${RQ_LOG_FORMAT}" --date-format "${RQ_DATE_FORMAT}" >> "${RQ_YIELD_ALERT_WORKER_LOG}" 2>&1 < /dev/null &
    else
        env DB_POOL_SIZE=2 DB_MAX_OVERFLOW=1 nohup rq worker "${RQ_YIELD_ALERT_WORKER_QUEUE}" --url "${redis_url}" -P src -c mes_dashboard.rq_worker_preload --log-format "${RQ_LOG_FORMAT}" --date-format "${RQ_DATE_FORMAT}" >> "${RQ_YIELD_ALERT_WORKER_LOG}" 2>&1 < /dev/null &
    fi
    local worker_pid=$!
    echo "$worker_pid" > "${RQ_YIELD_ALERT_WORKER_PID_FILE}"
    sleep 1
    if kill -0 "$worker_pid" 2>/dev/null; then
        log_success "RQ yield-alert worker started (PID: ${worker_pid}, queue: ${RQ_YIELD_ALERT_WORKER_QUEUE})"
        return 0
    else
        log_error "RQ yield-alert worker failed to start"
        return 1
    fi
}

stop_rq_yield_alert_worker() {
    if ! is_rq_yield_alert_worker_running; then
        log_info "RQ yield-alert worker is not running"
        return 0
    fi

    local pid
    pid=$(get_rq_yield_alert_worker_pid)
    log_info "Stopping RQ yield-alert worker (PID: ${pid})..."
    if kill "$pid" 2>/dev/null; then
        local wait=0
        while kill -0 "$pid" 2>/dev/null && [ "$wait" -lt 10 ]; do
            sleep 1
            wait=$((wait+1))
        done
        if kill -0 "$pid" 2>/dev/null; then
            kill -9 "$pid" 2>/dev/null || true
        fi
        rm -f "${RQ_YIELD_ALERT_WORKER_PID_FILE:-}" 2>/dev/null || true
        log_success "RQ yield-alert worker stopped"
        return 0
    else
        log_error "Failed to stop RQ yield-alert worker"
        return 1
    fi
}

rq_yield_alert_worker_status() {
    if ! is_enabled "${RQ_YIELD_ALERT_WORKER_ENABLED:-true}"; then
        echo -e "  RQ Yield-Alert Worker:${YELLOW} DISABLED${NC}"
        return 0
    fi

    if is_rq_yield_alert_worker_running; then
        local pid
        pid=$(get_rq_yield_alert_worker_pid)
        echo -e "  RQ Yield-Alert Worker:${GREEN} RUNNING${NC} (PID: ${pid}, queue: ${RQ_YIELD_ALERT_WORKER_QUEUE})"
    else
        echo -e "  RQ Yield-Alert Worker:${RED} STOPPED${NC}"
    fi
}

# ---------------------------------------------------------------------------
# RQ Hold-History Worker functions
# ---------------------------------------------------------------------------
get_rq_hold_hist_worker_pid() {
    local saved_pid=""
    if [ -f "${RQ_HOLD_HIST_WORKER_PID_FILE:-}" ]; then
        saved_pid=$(cat "${RQ_HOLD_HIST_WORKER_PID_FILE}" 2>/dev/null || true)
        if [ -n "$saved_pid" ] && kill -0 "$saved_pid" 2>/dev/null; then
            echo "$saved_pid"
            return 0
        fi
    fi
    local discovered_pid
    discovered_pid=$(pgrep -f "[r]q worker.*${RQ_HOLD_HIST_WORKER_QUEUE}" 2>/dev/null | head -1 || true)
    if [ -n "$discovered_pid" ]; then
        echo "$discovered_pid"
        return 0
    fi
    return 1
}

is_rq_hold_hist_worker_running() {
    get_rq_hold_hist_worker_pid &>/dev/null
}

start_rq_hold_hist_worker() {
    if ! is_enabled "${RQ_HOLD_HIST_WORKER_ENABLED:-true}"; then
        log_info "RQ hold-history worker is disabled (RQ_HOLD_HIST_WORKER_ENABLED=${RQ_HOLD_HIST_WORKER_ENABLED:-true})"
        return 0
    fi

    resolve_runtime_paths

    if is_rq_hold_hist_worker_running; then
        local pid
        pid=$(get_rq_hold_hist_worker_pid)
        log_info "RQ hold-history worker already running (PID: ${pid})"
        return 0
    fi

    local redis_url="redis://127.0.0.1:6379/0"
    if [ -n "${REDIS_URL:-}" ]; then
        redis_url="${REDIS_URL}"
    fi

    log_info "Starting RQ hold-history worker (queue: ${RQ_HOLD_HIST_WORKER_QUEUE})..."

    if command -v setsid &>/dev/null; then
        setsid env DB_POOL_SIZE=2 DB_MAX_OVERFLOW=1 rq worker "${RQ_HOLD_HIST_WORKER_QUEUE}" --url "${redis_url}" -P src -c mes_dashboard.rq_worker_preload --log-format "${RQ_LOG_FORMAT}" --date-format "${RQ_DATE_FORMAT}" >> "${RQ_HOLD_HIST_WORKER_LOG}" 2>&1 < /dev/null &
    else
        env DB_POOL_SIZE=2 DB_MAX_OVERFLOW=1 nohup rq worker "${RQ_HOLD_HIST_WORKER_QUEUE}" --url "${redis_url}" -P src -c mes_dashboard.rq_worker_preload --log-format "${RQ_LOG_FORMAT}" --date-format "${RQ_DATE_FORMAT}" >> "${RQ_HOLD_HIST_WORKER_LOG}" 2>&1 < /dev/null &
    fi
    local worker_pid=$!
    echo "$worker_pid" > "${RQ_HOLD_HIST_WORKER_PID_FILE}"
    sleep 1
    if kill -0 "$worker_pid" 2>/dev/null; then
        log_success "RQ hold-history worker started (PID: ${worker_pid}, queue: ${RQ_HOLD_HIST_WORKER_QUEUE})"
        return 0
    else
        log_error "RQ hold-history worker failed to start"
        return 1
    fi
}

stop_rq_hold_hist_worker() {
    if ! is_rq_hold_hist_worker_running; then
        log_info "RQ hold-history worker is not running"
        return 0
    fi

    local pid
    pid=$(get_rq_hold_hist_worker_pid)
    log_info "Stopping RQ hold-history worker (PID: ${pid})..."
    if kill "$pid" 2>/dev/null; then
        local wait=0
        while kill -0 "$pid" 2>/dev/null && [ "$wait" -lt 10 ]; do
            sleep 1
            wait=$((wait+1))
        done
        if kill -0 "$pid" 2>/dev/null; then
            kill -9 "$pid" 2>/dev/null || true
        fi
        rm -f "${RQ_HOLD_HIST_WORKER_PID_FILE:-}" 2>/dev/null || true
        log_success "RQ hold-history worker stopped"
        return 0
    else
        log_error "Failed to stop RQ hold-history worker"
        return 1
    fi
}

rq_hold_hist_worker_status() {
    if ! is_enabled "${RQ_HOLD_HIST_WORKER_ENABLED:-true}"; then
        echo -e "  RQ Hold-History Worker:${YELLOW} DISABLED${NC}"
        return 0
    fi

    if is_rq_hold_hist_worker_running; then
        local pid
        pid=$(get_rq_hold_hist_worker_pid)
        echo -e "  RQ Hold-History Worker:${GREEN} RUNNING${NC} (PID: ${pid}, queue: ${RQ_HOLD_HIST_WORKER_QUEUE})"
    else
        echo -e "  RQ Hold-History Worker:${RED} STOPPED${NC}"
    fi
}

# ---------------------------------------------------------------------------
# RQ Warmup Worker functions
# ---------------------------------------------------------------------------
get_rq_warmup_worker_pid() {
    local saved_pid=""
    if [ -f "${RQ_WARMUP_WORKER_PID_FILE:-}" ]; then
        saved_pid=$(cat "${RQ_WARMUP_WORKER_PID_FILE}" 2>/dev/null || true)
        if [ -n "$saved_pid" ] && kill -0 "$saved_pid" 2>/dev/null; then
            echo "$saved_pid"
            return 0
        fi
    fi
    local discovered_pid
    discovered_pid=$(pgrep -f "[r]q worker.*${RQ_WARMUP_WORKER_QUEUE}" 2>/dev/null | head -1 || true)
    if [ -n "$discovered_pid" ]; then
        echo "$discovered_pid"
        return 0
    fi
    return 1
}

is_rq_warmup_worker_running() {
    get_rq_warmup_worker_pid &>/dev/null
}

start_rq_warmup_worker() {
    if ! is_enabled "${RQ_WARMUP_WORKER_ENABLED:-true}"; then
        log_info "RQ warmup worker is disabled (RQ_WARMUP_WORKER_ENABLED=${RQ_WARMUP_WORKER_ENABLED:-true})"
        return 0
    fi

    resolve_runtime_paths

    if is_rq_warmup_worker_running; then
        local pid
        pid=$(get_rq_warmup_worker_pid)
        log_info "RQ warmup worker already running (PID: ${pid})"
        return 0
    fi

    local redis_url="redis://127.0.0.1:6379/0"
    if [ -n "${REDIS_URL:-}" ]; then
        redis_url="${REDIS_URL}"
    fi

    log_info "Starting RQ warmup worker (queue: ${RQ_WARMUP_WORKER_QUEUE})..."

    if command -v setsid &>/dev/null; then
        setsid env DB_POOL_SIZE=2 DB_MAX_OVERFLOW=1 rq worker "${RQ_WARMUP_WORKER_QUEUE}" --url "${redis_url}" -P src -c mes_dashboard.rq_worker_preload --log-format "${RQ_LOG_FORMAT}" --date-format "${RQ_DATE_FORMAT}" >> "${RQ_WARMUP_WORKER_LOG}" 2>&1 < /dev/null &
    else
        env DB_POOL_SIZE=2 DB_MAX_OVERFLOW=1 nohup rq worker "${RQ_WARMUP_WORKER_QUEUE}" --url "${redis_url}" -P src -c mes_dashboard.rq_worker_preload --log-format "${RQ_LOG_FORMAT}" --date-format "${RQ_DATE_FORMAT}" >> "${RQ_WARMUP_WORKER_LOG}" 2>&1 < /dev/null &
    fi
    local worker_pid=$!
    echo "$worker_pid" > "${RQ_WARMUP_WORKER_PID_FILE}"
    sleep 1
    if kill -0 "$worker_pid" 2>/dev/null; then
        log_success "RQ warmup worker started (PID: ${worker_pid}, queue: ${RQ_WARMUP_WORKER_QUEUE})"
        return 0
    else
        log_error "RQ warmup worker failed to start"
        return 1
    fi
}

stop_rq_warmup_worker() {
    if ! is_rq_warmup_worker_running; then
        log_info "RQ warmup worker is not running"
        return 0
    fi

    local pid
    pid=$(get_rq_warmup_worker_pid)
    log_info "Stopping RQ warmup worker (PID: ${pid})..."
    if kill "$pid" 2>/dev/null; then
        local wait=0
        while kill -0 "$pid" 2>/dev/null && [ "$wait" -lt 10 ]; do
            sleep 1
            wait=$((wait+1))
        done
        if kill -0 "$pid" 2>/dev/null; then
            kill -9 "$pid" 2>/dev/null || true
        fi
        rm -f "${RQ_WARMUP_WORKER_PID_FILE:-}" 2>/dev/null || true
        log_success "RQ warmup worker stopped"
        return 0
    else
        log_error "Failed to stop RQ warmup worker"
        return 1
    fi
}

rq_warmup_worker_status() {
    if ! is_enabled "${RQ_WARMUP_WORKER_ENABLED:-true}"; then
        echo -e "  RQ Warmup Worker:${YELLOW} DISABLED${NC}"
        return 0
    fi

    if is_rq_warmup_worker_running; then
        local pid
        pid=$(get_rq_warmup_worker_pid)
        echo -e "  RQ Warmup Worker:${GREEN} RUNNING${NC} (PID: ${pid}, queue: ${RQ_WARMUP_WORKER_QUEUE})"
    else
        echo -e "  RQ Warmup Worker:${RED} STOPPED${NC}"
    fi
}

do_start() {
    local foreground=false

    if [ "${1:-}" = "-f" ] || [ "${1:-}" = "--foreground" ]; then
        foreground=true
    fi

    load_env
    resolve_runtime_paths

    if is_running; then
        local pid=$(get_pid)
        log_warn "Server is already running (PID: ${pid})"
        if is_enabled "${WATCHDOG_ENABLED:-true}" && ! is_watchdog_running; then
            check_conda || return 1
            conda activate "$CONDA_ENV"
            export PYTHONPATH="${ROOT}/src:${PYTHONPATH:-}"
            cd "$ROOT"
            start_watchdog || return 1
        fi
        return 0
    fi

    # Run checks
    run_all_checks || return 1

    echo ""

    # Start Redis if enabled
    start_redis

    log_info "Starting ${APP_NAME} server..."

    ensure_dirs
    rotate_logs  # Archive old logs before starting new session
    conda activate "$CONDA_ENV"
    load_env  # Load environment variables from .env file
    resolve_runtime_paths
    # Re-evaluate port after loading .env (GUNICORN_BIND may have changed)
    PORT=$(echo "${GUNICORN_BIND:-0.0.0.0:8080}" | cut -d: -f2)
    export PYTHONPATH="${ROOT}/src:${PYTHONPATH:-}"
    cd "$ROOT"
    build_frontend_assets || return 1

    # Log startup
    echo "[$(timestamp)] Starting server" >> "$STARTUP_LOG"

    if [ "$foreground" = true ]; then
        if is_enabled "${WATCHDOG_ENABLED:-true}"; then
            log_info "Foreground mode does not auto-start watchdog (use background start for watchdog)."
        fi
        log_info "Running in foreground mode (Ctrl+C to stop)"
        exec gunicorn \
            --config gunicorn.conf.py \
            --pid "$PID_FILE" \
            --access-logfile "$ACCESS_LOG" \
            --error-logfile "$ERROR_LOG" \
            --capture-output \
            "mes_dashboard:create_app()"
    else
        gunicorn \
            --config gunicorn.conf.py \
            --pid "$PID_FILE" \
            --access-logfile "$ACCESS_LOG" \
            --error-logfile "$ERROR_LOG" \
            --capture-output \
            --daemon \
            "mes_dashboard:create_app()"

        local readiness_timeout="${SERVER_STARTUP_TIMEOUT:-60}"
        local waited=0
        while [ "$waited" -lt "$readiness_timeout" ]; do
            if is_running; then
                break
            fi
            sleep 1
            waited=$((waited + 1))
        done

        if is_running; then
            local pid=$(get_pid)
            log_success "Server started successfully (PID: ${pid}, ready in ${waited}s)"
            log_info "Access URL: http://localhost:${PORT}"
            log_info "Logs: ${LOG_DIR}/"
            start_watchdog || return 1
            start_rq_worker
            start_rq_reject_worker
            start_rq_msd_worker
            start_rq_prod_hist_worker
            start_rq_yield_alert_worker
            start_rq_hold_hist_worker
            start_rq_warmup_worker
            echo "[$(timestamp)] Server started (PID: ${pid})" >> "$STARTUP_LOG"
        else
            log_error "Failed to start server"
            log_info "Check error log: ${ERROR_LOG}"
            echo "[$(timestamp)] Server start failed" >> "$STARTUP_LOG"
            return 1
        fi
    fi
}

do_stop() {
    load_env
    resolve_runtime_paths

    local server_running=false
    local pid=""
    if is_running; then
        server_running=true
        pid=$(get_pid)
        log_info "Stopping server (PID: ${pid})..."
    else
        log_warn "Server is not running"
    fi

    if [ "$server_running" = true ]; then
        # Find all gunicorn processes (master + workers)
        local all_pids=$(pgrep -f "gunicorn.*mes_dashboard" 2>/dev/null | tr '\n' ' ')

        # Graceful shutdown with SIGTERM
        kill -TERM "$pid" 2>/dev/null

        # Wait for graceful shutdown (max 10 seconds)
        local count=0
        while kill -0 "$pid" 2>/dev/null && [ $count -lt 10 ]; do
            sleep 1
            count=$((count + 1))
            echo -n "."
        done
        echo ""

        # Force kill if still running (including orphaned workers)
        if kill -0 "$pid" 2>/dev/null || [ -n "$(pgrep -f 'gunicorn.*mes_dashboard' 2>/dev/null)" ]; then
            log_warn "Graceful shutdown timeout, forcing..."
            # Kill all gunicorn processes related to mes_dashboard
            pkill -9 -f "gunicorn.*mes_dashboard" 2>/dev/null
            sleep 1
        fi

        # Cleanup PID file
        rm -f "$PID_FILE"

        # Verify all processes are stopped
        if [ -z "$(pgrep -f 'gunicorn.*mes_dashboard' 2>/dev/null)" ]; then
            log_success "Server stopped"
            echo "[$(timestamp)] Server stopped (PID: ${pid})" >> "$STARTUP_LOG"
        else
            log_error "Failed to stop server"
            return 1
        fi
    fi

    stop_rq_warmup_worker
    stop_rq_hold_hist_worker
    stop_rq_yield_alert_worker
    stop_rq_prod_hist_worker
    stop_rq_msd_worker
    stop_rq_reject_worker
    stop_rq_worker
    stop_watchdog
}

do_restart() {
    log_info "Restarting ${APP_NAME} server..."
    do_stop
    sleep 1
    do_start "$@"
}

do_status() {
    # Load environment to get REDIS_ENABLED
    load_env
    resolve_runtime_paths

    echo ""
    echo "=========================================="
    echo "  ${APP_NAME} Server Status"
    echo "=========================================="
    echo ""

    if is_running; then
        local pid=$(get_pid)
        echo -e "  Server:  ${GREEN}RUNNING${NC}"
        echo "  PID:     ${pid}"
        echo "  Port:    ${PORT}"
        echo "  URL:     http://localhost:${PORT}"
        echo "  PIDFile: ${PID_FILE}"
        echo "  Watchdog Runtime: ${WATCHDOG_RUNTIME_DIR}"
    else
        echo -e "  Server:  ${RED}STOPPED${NC}"
    fi

    # Show Redis status
    redis_status
    if is_enabled "${WATCHDOG_ENABLED:-true}"; then
        if is_watchdog_running; then
            local watchdog_pid=$(get_watchdog_pid)
            echo -e "  Watchdog:${GREEN} RUNNING${NC} (PID: ${watchdog_pid})"
        else
            echo -e "  Watchdog:${YELLOW} STOPPED${NC}"
        fi
    else
        echo -e "  Watchdog:${YELLOW} DISABLED${NC}"
    fi
    rq_worker_status
    rq_reject_worker_status
    rq_msd_worker_status
    rq_prod_hist_worker_status
    rq_yield_alert_worker_status
    rq_hold_hist_worker_status
    rq_warmup_worker_status

    if is_running; then
        echo ""

        # Show process info
        local pid=$(get_pid)
        if command -v ps &>/dev/null; then
            echo "  Process Info:"
            ps -p "$pid" -o pid,ppid,%cpu,%mem,etime,cmd --no-headers 2>/dev/null | \
                awk '{printf "    PID: %s | CPU: %s%% | MEM: %s%% | Uptime: %s\n", $1, $3, $4, $5}'
        fi

        # Show recent log entries
        if [ -f "$ERROR_LOG" ]; then
            echo ""
            echo "  Recent Errors (last 3):"
            tail -3 "$ERROR_LOG" 2>/dev/null | sed 's/^/    /'
        fi
    else
        echo ""
        echo "  Start with: $0 start"
    fi

    echo ""
    echo "=========================================="
}

do_logs() {
    local log_type="${1:-all}"
    local lines="${2:-50}"

    case "$log_type" in
        access)
            if [ -f "$ACCESS_LOG" ]; then
                log_info "Access log (last ${lines} lines):"
                tail -n "$lines" "$ACCESS_LOG"
            else
                log_warn "Access log not found"
            fi
            ;;
        error)
            if [ -f "$ERROR_LOG" ]; then
                log_info "Error log (last ${lines} lines):"
                tail -n "$lines" "$ERROR_LOG"
            else
                log_warn "Error log not found"
            fi
            ;;
        follow)
            log_info "Following logs (Ctrl+C to stop)..."
            tail -f "$ACCESS_LOG" "$ERROR_LOG" "$WATCHDOG_LOG" 2>/dev/null
            ;;
        watchdog)
            if [ -f "$WATCHDOG_LOG" ]; then
                log_info "Watchdog log (last ${lines} lines):"
                tail -n "$lines" "$WATCHDOG_LOG"
            else
                log_warn "Watchdog log not found"
            fi
            ;;
        *)
            log_info "=== Error Log (last 20 lines) ==="
            tail -20 "$ERROR_LOG" 2>/dev/null || echo "(empty)"
            echo ""
            log_info "=== Access Log (last 20 lines) ==="
            tail -20 "$ACCESS_LOG" 2>/dev/null || echo "(empty)"
            echo ""
            log_info "=== Watchdog Log (last 20 lines) ==="
            tail -20 "$WATCHDOG_LOG" 2>/dev/null || echo "(empty)"
            ;;
    esac
}

do_check() {
    run_all_checks
}

show_help() {
    echo ""
    echo "Usage: $0 <command> [options]"
    echo ""
    echo "Commands:"
    echo "  start [-f]     Start the server (-f for foreground mode)"
    echo "  stop           Stop the server gracefully"
    echo "  restart        Restart the server"
    echo "  status         Show server and Redis status"
    echo "  logs [type]    View logs (access|error|watchdog|follow|all)"
    echo "  check          Run environment checks only"
    echo "  help           Show this help message"
    echo ""
    echo "Examples:"
    echo "  $0 start           # Start in background (with Redis)"
    echo "  $0 start -f        # Start in foreground"
    echo "  $0 logs follow     # Follow logs in real-time"
    echo "  $0 logs error 100  # Show last 100 error log lines"
    echo ""
    echo "Environment Variables:"
    echo "  GUNICORN_BIND      Bind address (default: 0.0.0.0:8080)"
    echo "  GUNICORN_WORKERS   Number of workers (default: 1)"
    echo "  GUNICORN_THREADS   Threads per worker (default: 4)"
    echo "  REDIS_ENABLED      Enable Redis cache (default: true)"
    echo "  REDIS_URL          Redis connection URL"
    echo "  WATCHDOG_ENABLED   Enable worker watchdog (default: true)"
    echo ""
}

# ============================================================
# Main
# ============================================================
main() {
    local command="${1:-}"
    shift || true

    case "$command" in
        start)
            do_start "$@"
            ;;
        stop)
            do_stop
            ;;
        restart)
            do_restart "$@"
            ;;
        status)
            do_status
            ;;
        logs)
            do_logs "$@"
            ;;
        check)
            do_check
            ;;
        help|--help|-h)
            show_help
            ;;
        "")
            # Default: start in foreground for backward compatibility
            do_start
            ;;
        *)
            log_error "Unknown command: ${command}"
            show_help
            exit 1
            ;;
    esac
}

main "$@"
