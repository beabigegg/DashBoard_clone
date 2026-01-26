#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
export PYTHONPATH="${ROOT}/src:${PYTHONPATH:-}"

cd "$ROOT"
exec gunicorn --config gunicorn.conf.py "mes_dashboard:create_app()"
