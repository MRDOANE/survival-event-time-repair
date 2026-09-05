#!/usr/bin/env bash
set -euo pipefail

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$PROJECT_DIR"

PYTHON_BIN="${PYTHON_BIN:-python3}"
VENV_DIR="${VENV_DIR:-$PROJECT_DIR/.venv}"
JOBS="${JOBS:-8}"
REPLICATES="${REPLICATES:-500}"
MODE="${MODE:-full}"
RESUME="${RESUME:-1}"
RUN_TESTS="${RUN_TESTS:-1}"

if [[ ! -x "$VENV_DIR/bin/python" ]]; then
  "$PYTHON_BIN" -m venv "$VENV_DIR"
fi
source "$VENV_DIR/bin/activate"
python -m pip install --upgrade pip
python -m pip install -r requirements.txt

if [[ "$RUN_TESTS" == "1" ]]; then
  python -m pytest -q
fi

if [[ "$MODE" == "smoke" ]]; then
  REPLICATES="${SMOKE_REPLICATES:-8}"
  OUTPUT_DIR="$PROJECT_DIR/outputs/smoke"
  RESULTS_ZIP="${RESULTS_ZIP:-/workspace/survival_hemophilia_hiv_external_smoke_results.zip}"
else
  OUTPUT_DIR="$PROJECT_DIR/outputs/full"
  RESULTS_ZIP="${RESULTS_ZIP:-/workspace/survival_hemophilia_hiv_external_results.zip}"
fi

RESUME_ARG=()
if [[ "$RESUME" == "1" ]]; then
  RESUME_ARG=(--resume)
fi

python src/run_study.py \
  --config config/study.json \
  --output "$OUTPUT_DIR" \
  --replicates "$REPLICATES" \
  --jobs "$JOBS" \
  --results-zip "$RESULTS_ZIP" \
  "${RESUME_ARG[@]}"
