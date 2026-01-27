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
CONDA_ENV="mes-dashboard"
APP_NAME="mes-dashboard"
PID_FILE="${ROOT}/tmp/gunicorn.pid"
LOG_DIR="${ROOT}/logs"
ACCESS_LOG="${LOG_DIR}/access.log"
ERROR_LOG="${LOG_DIR}/error.log"
STARTUP_LOG="${LOG_DIR}/startup.log"
DEFAULT_PORT="${GUNICORN_BIND:-0.0.0.0:8080}"
PORT=$(echo "$DEFAULT_PORT" | cut -d: -f2)

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

# ============================================================
# Environment Check Functions
# ============================================================
check_conda() {
    if ! command -v conda &> /dev/null; then
        log_error "Conda not found. Please install Miniconda/Anaconda."
        return 1
    fi

    # Source conda
    source "$(conda info --base)/etc/profile.d/conda.sh"

    # Check if environment exists
    if ! conda env list | grep -q "^${CONDA_ENV} "; then
        log_error "Conda environment '${CONDA_ENV}' not found."
        log_info "Create it with: conda create -n ${CONDA_ENV} python=3.11"
        return 1
    fi

    log_success "Conda environment '${CONDA_ENV}' found"
    return 0
}

check_dependencies() {
    conda activate "$CONDA_ENV"

    local missing=()

    # Check critical packages
    python -c "import flask" 2>/dev/null || missing+=("flask")
    python -c "import gunicorn" 2>/dev/null || missing+=("gunicorn")
    python -c "import pandas" 2>/dev/null || missing+=("pandas")
    python -c "import oracledb" 2>/dev/null || missing+=("oracledb")

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

run_all_checks() {
    log_info "Running environment checks..."
    echo ""

    check_conda || return 1
    check_dependencies || return 1
    check_env_file
    check_port || return 1
    check_database

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
    mkdir -p "${ROOT}/tmp"
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

    # Clean up old archives (keep last 10)
    cd "${LOG_DIR}/archive" 2>/dev/null && \
        ls -t access_*.log 2>/dev/null | tail -n +11 | xargs -r rm -f && \
        ls -t error_*.log 2>/dev/null | tail -n +11 | xargs -r rm -f
    cd "$ROOT"

    # Create fresh log files
    touch "$ACCESS_LOG" "$ERROR_LOG"
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

do_start() {
    local foreground=false

    if [ "${1:-}" = "-f" ] || [ "${1:-}" = "--foreground" ]; then
        foreground=true
    fi

    if is_running; then
        local pid=$(get_pid)
        log_warn "Server is already running (PID: ${pid})"
        return 1
    fi

    # Run checks
    run_all_checks || return 1

    echo ""
    log_info "Starting ${APP_NAME} server..."

    ensure_dirs
    rotate_logs  # Archive old logs before starting new session
    conda activate "$CONDA_ENV"
    export PYTHONPATH="${ROOT}/src:${PYTHONPATH:-}"
    cd "$ROOT"

    # Log startup
    echo "[$(timestamp)] Starting server" >> "$STARTUP_LOG"

    if [ "$foreground" = true ]; then
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

        sleep 1

        if is_running; then
            local pid=$(get_pid)
            log_success "Server started successfully (PID: ${pid})"
            log_info "Access URL: http://localhost:${PORT}"
            log_info "Logs: ${LOG_DIR}/"
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
    if ! is_running; then
        log_warn "Server is not running"
        return 0
    fi

    local pid=$(get_pid)
    log_info "Stopping server (PID: ${pid})..."

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
}

do_restart() {
    log_info "Restarting ${APP_NAME} server..."
    do_stop
    sleep 1
    do_start "$@"
}

do_status() {
    echo ""
    echo "=========================================="
    echo "  ${APP_NAME} Server Status"
    echo "=========================================="
    echo ""

    if is_running; then
        local pid=$(get_pid)
        echo -e "  Status:  ${GREEN}RUNNING${NC}"
        echo "  PID:     ${pid}"
        echo "  Port:    ${PORT}"
        echo "  URL:     http://localhost:${PORT}"
        echo ""

        # Show process info
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
        echo -e "  Status:  ${RED}STOPPED${NC}"
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
            tail -f "$ACCESS_LOG" "$ERROR_LOG" 2>/dev/null
            ;;
        *)
            log_info "=== Error Log (last 20 lines) ==="
            tail -20 "$ERROR_LOG" 2>/dev/null || echo "(empty)"
            echo ""
            log_info "=== Access Log (last 20 lines) ==="
            tail -20 "$ACCESS_LOG" 2>/dev/null || echo "(empty)"
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
    echo "  status         Show server status"
    echo "  logs [type]    View logs (access|error|follow|all)"
    echo "  check          Run environment checks only"
    echo "  help           Show this help message"
    echo ""
    echo "Examples:"
    echo "  $0 start           # Start in background"
    echo "  $0 start -f        # Start in foreground"
    echo "  $0 logs follow     # Follow logs in real-time"
    echo "  $0 logs error 100  # Show last 100 error log lines"
    echo ""
    echo "Environment Variables:"
    echo "  GUNICORN_BIND      Bind address (default: 0.0.0.0:8080)"
    echo "  GUNICORN_WORKERS   Number of workers (default: 1)"
    echo "  GUNICORN_THREADS   Threads per worker (default: 4)"
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
