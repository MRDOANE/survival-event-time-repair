#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
OUTPUT_DIR="${1:-${ROOT_DIR}/outputs/full}"
TARGET="${2:-/workspace/survival_drcosarc_gate3_results.zip}"
PYTHON_BIN="${PYTHON_BIN:-${ROOT_DIR}/.venv/bin/python}"

"${PYTHON_BIN}" "${ROOT_DIR}/scripts/package_results.py" "${OUTPUT_DIR}" "${TARGET}"
