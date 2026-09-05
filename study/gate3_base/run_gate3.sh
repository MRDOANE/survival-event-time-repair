#!/usr/bin/env bash
set -euo pipefail

MODE="${1:-full}"
if [[ "${MODE}" != "smoke" && "${MODE}" != "full" ]]; then
  echo "Usage: bash run_gate3.sh [smoke|full]" >&2
  exit 2
fi

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "${ROOT_DIR}"

BLAS_THREADS="${BLAS_THREADS:-1}"
export OMP_NUM_THREADS="${BLAS_THREADS}"
export OPENBLAS_NUM_THREADS="${BLAS_THREADS}"
export MKL_NUM_THREADS="${BLAS_THREADS}"
export NUMEXPR_NUM_THREADS="${BLAS_THREADS}"
export PYTHONHASHSEED="${PYTHONHASHSEED:-0}"
export R_LIBS_USER="${R_LIBS_USER:-${ROOT_DIR}/.r_libs}"
export DRCOSARC_UPSTREAM_DIR="${DRCOSARC_UPSTREAM_DIR:-${ROOT_DIR}/external/conformal_survival}"

PYTHON_BIN="${PYTHON_BIN:-python3}"
VENV_DIR="${VENV_DIR:-${ROOT_DIR}/.venv}"
RUN_NAME="${RUN_NAME:-${MODE}}"
OUT_DIR="${OUT_DIR:-${ROOT_DIR}/outputs/${RUN_NAME}}"
CONFIG="${CONFIG:-${ROOT_DIR}/configs/${MODE}.yaml}"

mkdir -p "${OUT_DIR}/logs"
exec > >(tee -a "${OUT_DIR}/logs/launcher.log") 2>&1

START_EPOCH="$(date +%s)"
echo "[$(date -u +%FT%TZ)] Gate 3 mode=${MODE} output=${OUT_DIR}"

bash "${ROOT_DIR}/scripts/bootstrap_official.sh"

if [[ ! -x "${VENV_DIR}/bin/python" ]]; then
  "${PYTHON_BIN}" -m venv "${VENV_DIR}"
fi
"${VENV_DIR}/bin/python" -m pip install --upgrade pip setuptools wheel
"${VENV_DIR}/bin/python" -m pip install -r requirements.txt
"${VENV_DIR}/bin/python" -m pip install -e .
"${VENV_DIR}/bin/python" -m pytest -q

EXTRA_ARGS=()
if [[ -n "${N_JOBS:-}" ]]; then
  EXTRA_ARGS+=(--n-jobs "${N_JOBS}")
fi

"${VENV_DIR}/bin/python" -m survival_noise_bakeoff.cli run \
  --config "${CONFIG}" \
  --output "${OUT_DIR}" \
  --resume \
  "${EXTRA_ARGS[@]}"

"${VENV_DIR}/bin/python" -m pip freeze > "${OUT_DIR}/environment_freeze.txt"
Rscript --vanilla -e 'sessionInfo()' > "${OUT_DIR}/r_session_info.txt"

END_EPOCH="$(date +%s)"
WALL_SECONDS="$((END_EPOCH - START_EPOCH))"
printf '%s\n' "${WALL_SECONDS}" > "${OUT_DIR}/wall_runtime_seconds.txt"

echo "[$(date -u +%FT%TZ)] completed in ${WALL_SECONDS}s"
echo "Gate: ${OUT_DIR}/gate_decision.json"
echo "Report: ${OUT_DIR}/gate_report.md"
