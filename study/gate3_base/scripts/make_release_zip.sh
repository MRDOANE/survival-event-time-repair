#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
DESTINATION="${1:-${ROOT_DIR}/survival-drcosarc-gate3-v1.0.zip}"
PARENT_DIR="$(dirname "${ROOT_DIR}")"
PACKAGE_DIR="$(basename "${ROOT_DIR}")"

if ! command -v zip >/dev/null 2>&1; then
  echo "zip is required to build the release archive" >&2
  exit 1
fi

TEMP_DIR="$(mktemp -d "${ROOT_DIR}/.release_tmp.XXXXXX")"
TEMP_ZIP="${TEMP_DIR}/survival-drcosarc-gate3-v1.0.zip"
trap 'rm -rf "${TEMP_DIR}"' EXIT

cd "${PARENT_DIR}"
zip -q -r "${TEMP_ZIP}" "${PACKAGE_DIR}" \
  -x "${PACKAGE_DIR}/.venv/*" \
     "${PACKAGE_DIR}/.r_libs/*" \
     "${PACKAGE_DIR}/external/*" \
     "${PACKAGE_DIR}/outputs/*" \
     "${PACKAGE_DIR}/build/*" \
     "${PACKAGE_DIR}/.pytest_cache/*" \
     "${PACKAGE_DIR}/.ruff_cache/*" \
     "${PACKAGE_DIR}/*/__pycache__/*" \
     "${PACKAGE_DIR}/*/*/__pycache__/*" \
     "${PACKAGE_DIR}/*.egg-info/*" \
     "${PACKAGE_DIR}/*/*.egg-info/*" \
     "${PACKAGE_DIR}/*.pyc" \
     "${PACKAGE_DIR}/*/*.pyc" \
     "${PACKAGE_DIR}/*/*/*.pyc" \
     "${PACKAGE_DIR}/*.zip" \
     "${PACKAGE_DIR}/.release_tmp.*/*"

mkdir -p "${TEMP_DIR}/${PACKAGE_DIR}"
(
  cd "${ROOT_DIR}"
  find . -type f \
    ! -path './.venv/*' \
    ! -path './.r_libs/*' \
    ! -path './external/*' \
    ! -path './outputs/*' \
    ! -path './build/*' \
    ! -path './.pytest_cache/*' \
    ! -path './.ruff_cache/*' \
    ! -path '*/__pycache__/*' \
    ! -path '*.egg-info/*' \
    ! -path './.release_tmp.*/*' \
    ! -name '*.pyc' \
    ! -name '*.zip' \
    -print0 | sort -z | xargs -0 sha256sum
) > "${TEMP_DIR}/${PACKAGE_DIR}/SOURCE_SHA256SUMS.txt"
(
  cd "${TEMP_DIR}"
  zip -q "${TEMP_ZIP}" "${PACKAGE_DIR}/SOURCE_SHA256SUMS.txt"
)

mv -f "${TEMP_ZIP}" "${DESTINATION}"

echo "${DESTINATION}"
