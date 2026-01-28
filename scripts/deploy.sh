#!/usr/bin/env bash
#
# MES Dashboard Deployment Script
# Usage: ./deploy.sh [--skip-db-check]
#
set -euo pipefail

# ============================================================
# Configuration
# ============================================================
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
CONDA_ENV="mes-dashboard"
PYTHON_VERSION="3.11"

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

log_important() {
    echo -e "${YELLOW}[IMPORTANT]${NC} $1"
}

# ============================================================
# Deployment Functions
# ============================================================

check_prerequisites() {
    log_info "Checking prerequisites..."

    # Check conda
    if ! command -v conda &> /dev/null; then
        log_error "Conda not found. Please install Miniconda/Anaconda first."
        log_info "Download from: https://docs.conda.io/en/latest/miniconda.html"
        exit 1
    fi
    log_success "Conda found"

    # Source conda
    source "$(conda info --base)/etc/profile.d/conda.sh"
}

setup_conda_env() {
    log_info "Setting up conda environment..."

    # Check if environment exists
    if conda env list | grep -q "^${CONDA_ENV} "; then
        log_success "Environment '${CONDA_ENV}' already exists"
    else
        log_info "Creating conda environment '${CONDA_ENV}' with Python ${PYTHON_VERSION}..."
        conda create -n "$CONDA_ENV" python="$PYTHON_VERSION" -y
        log_success "Environment '${CONDA_ENV}' created"
    fi

    # Activate environment
    conda activate "$CONDA_ENV"
    log_success "Environment '${CONDA_ENV}' activated"
}

install_dependencies() {
    log_info "Installing dependencies..."

    if [ -f "${ROOT}/requirements.txt" ]; then
        pip install -r "${ROOT}/requirements.txt" --quiet
        log_success "Dependencies installed"
    else
        log_error "requirements.txt not found"
        exit 1
    fi
}

setup_env_file() {
    log_info "Setting up configuration..."

    if [ -f "${ROOT}/.env" ]; then
        log_success ".env file already exists"
        return 0
    fi

    if [ ! -f "${ROOT}/.env.example" ]; then
        log_error ".env.example not found"
        exit 1
    fi

    log_warn ".env file not found"
    log_info "Copying .env.example to .env"
    cp "${ROOT}/.env.example" "${ROOT}/.env"

    echo ""
    log_important "Please edit .env with your database credentials:"
    echo "    nano ${ROOT}/.env"
    echo ""
    echo "Required settings:"
    echo "  - DB_USER: Your database username"
    echo "  - DB_PASSWORD: Your database password"
    echo "  - SECRET_KEY: A secure random key for production"
    echo ""

    read -p "Press Enter after editing .env to continue..."
    echo ""
}

verify_database() {
    local skip_db="${1:-false}"

    if [ "$skip_db" = "true" ]; then
        log_warn "Skipping database verification"
        return 0
    fi

    log_info "Verifying database connection..."

    # Load .env
    if [ -f "${ROOT}/.env" ]; then
        set -a
        source "${ROOT}/.env"
        set +a
    fi

    export PYTHONPATH="${ROOT}/src:${PYTHONPATH:-}"

    if python -c "
from sqlalchemy import text
from mes_dashboard.core.database import get_engine
engine = get_engine()
with engine.connect() as conn:
    conn.execute(text('SELECT 1 FROM DUAL'))
" 2>/dev/null; then
        log_success "Database connection successful"
    else
        log_warn "Database connection failed"
        log_info "You can still proceed, but the application may not work correctly"
        log_info "Please check your DB_* settings in .env"
    fi
}

show_next_steps() {
    echo ""
    echo "=========================================="
    echo "  Deployment Complete!"
    echo "=========================================="
    echo ""
    echo "Start the server:"
    echo "  ./scripts/start_server.sh start"
    echo ""
    echo "View logs:"
    echo "  ./scripts/start_server.sh logs follow"
    echo ""
    echo "Check status:"
    echo "  ./scripts/start_server.sh status"
    echo ""
    echo "Access URL:"
    local port=$(grep -E "^GUNICORN_BIND=" "${ROOT}/.env" 2>/dev/null | cut -d: -f2 || echo "8080")
    echo "  http://localhost:${port:-8080}"
    echo ""
    echo "=========================================="
}

# ============================================================
# Main
# ============================================================
main() {
    local skip_db=false

    # Parse arguments
    for arg in "$@"; do
        case "$arg" in
            --skip-db-check)
                skip_db=true
                ;;
            --help|-h)
                echo "Usage: $0 [--skip-db-check]"
                echo ""
                echo "Options:"
                echo "  --skip-db-check  Skip database connection verification"
                echo "  --help, -h       Show this help message"
                exit 0
                ;;
        esac
    done

    echo ""
    echo "=========================================="
    echo "  MES Dashboard Deployment"
    echo "=========================================="
    echo ""

    check_prerequisites
    setup_conda_env
    install_dependencies
    setup_env_file
    verify_database "$skip_db"
    show_next_steps
}

main "$@"
