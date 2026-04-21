#!/usr/bin/env bash
# -*- coding: utf-8 -*-
#
# soak_local.sh — local 5-minute soak-workload smoke
#
# Runs the soak test with a 300-second duration and a 30-second sampling
# interval.  Intended for a developer to sanity-check the soak framework
# before pushing a change; NOT a substitute for the 30-minute nightly run.
#
# The test writes `soak-metrics-<ts>.json` to $SOAK_ARTIFACT_DIR (default
# `$(pwd)/artifacts/soak-local/<stamp>/`).  The artifact path is printed
# by the test via pytest's `-s` stream.
#
# Usage:
#   ./scripts/soak_local.sh                 # 300s default
#   SOAK_DURATION_SECONDS=600 ./scripts/soak_local.sh
#   SOAK_INTERVAL_SECONDS=15 ./scripts/soak_local.sh
#
# Prerequisites:
#   - conda env "mes-dashboard" with requirements installed
#   - redis-server on PATH
#   - Free TCP ports (the gunicorn_workers fixture finds them)
#
# Exit codes:
#   0  soak assertions passed + artifact produced
#   1+ test failure OR environment error (artifact still produced on fail)

set -euo pipefail

# --- defaults --------------------------------------------------------------

: "${SOAK_DURATION_SECONDS:=300}"
: "${SOAK_INTERVAL_SECONDS:=30}"

STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
DEFAULT_ARTIFACT_ROOT="$(pwd)/artifacts/soak-local/${STAMP}"
: "${SOAK_ARTIFACT_DIR:=${DEFAULT_ARTIFACT_ROOT}}"

export SOAK_DURATION_SECONDS
export SOAK_INTERVAL_SECONDS
export SOAK_ARTIFACT_DIR

mkdir -p "${SOAK_ARTIFACT_DIR}"

# --- sanity ---------------------------------------------------------------

if ! command -v redis-server >/dev/null 2>&1; then
    echo "error: redis-server not found on PATH (gunicorn_workers fixture requires it)" >&2
    exit 2
fi

if ! command -v conda >/dev/null 2>&1; then
    echo "error: conda not found on PATH; activate miniconda/anaconda before running" >&2
    exit 2
fi

echo "========================================================================"
echo "soak-workload local run"
echo "  duration:     ${SOAK_DURATION_SECONDS}s"
echo "  interval:     ${SOAK_INTERVAL_SECONDS}s"
echo "  artifact dir: ${SOAK_ARTIFACT_DIR}"
echo "========================================================================"

# --- run ------------------------------------------------------------------
# -s so the test's `[soak] ...` progress prints stream live to the terminal.
# --run-integration-real opts in to the integration_real tier (the soak
# test is marked both @integration_real and @soak).

cd "$(dirname "$0")/.."

set +e
conda run --no-capture-output -n mes-dashboard pytest \
    tests/integration/test_soak_workload.py \
    --run-integration-real \
    -m soak \
    -s -v \
    --tb=short
exit_code=$?
set -e

echo ""
if [ "${exit_code}" -eq 0 ]; then
    echo "[soak_local] PASS — see ${SOAK_ARTIFACT_DIR} for the time series"
else
    echo "[soak_local] FAIL (exit=${exit_code}) — artifact still at ${SOAK_ARTIFACT_DIR}"
fi

exit "${exit_code}"
