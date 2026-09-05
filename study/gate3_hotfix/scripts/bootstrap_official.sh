#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
UPSTREAM_COMMIT="5b2cd20354e42105c980eabb4650240ae76dc866"
UPSTREAM_URL="https://github.com/msesia/conformal_survival.git"
export DRCOSARC_UPSTREAM_DIR="${DRCOSARC_UPSTREAM_DIR:-${ROOT_DIR}/external/conformal_survival}"
export R_LIBS_USER="${R_LIBS_USER:-${ROOT_DIR}/.r_libs}"

mkdir -p "${R_LIBS_USER}" "$(dirname "${DRCOSARC_UPSTREAM_DIR}")"

if ! command -v Rscript >/dev/null 2>&1; then
  if ! command -v apt-get >/dev/null 2>&1 || [[ "$(id -u)" -ne 0 ]]; then
    echo "Rscript is missing. Run this package in a root-capable Ubuntu/Debian pod or preinstall R >= 4.1." >&2
    exit 1
  fi
  export DEBIAN_FRONTEND=noninteractive
  apt-get update
  if ! apt-get install -y --no-install-recommends \
    r-base r-base-dev r-cran-jsonlite r-cran-r6 r-cran-survival r-cran-tidyverse \
    git ca-certificates libcurl4-openssl-dev libssl-dev libxml2-dev; then
    apt-get install -y --no-install-recommends \
      r-base r-base-dev git ca-certificates libcurl4-openssl-dev libssl-dev \
      libxml2-dev libfontconfig1-dev libharfbuzz-dev libfribidi-dev
  fi
fi

Rscript --vanilla "${ROOT_DIR}/scripts/install_r_packages.R"

if [[ ! -d "${DRCOSARC_UPSTREAM_DIR}/.git" ]]; then
  git clone --filter=blob:none "${UPSTREAM_URL}" "${DRCOSARC_UPSTREAM_DIR}"
fi

git -C "${DRCOSARC_UPSTREAM_DIR}" fetch --quiet origin "${UPSTREAM_COMMIT}"
git -C "${DRCOSARC_UPSTREAM_DIR}" checkout --quiet --detach "${UPSTREAM_COMMIT}"
ACTUAL_COMMIT="$(git -C "${DRCOSARC_UPSTREAM_DIR}" rev-parse HEAD)"
if [[ "${ACTUAL_COMMIT}" != "${UPSTREAM_COMMIT}" ]]; then
  echo "Official source commit mismatch: ${ACTUAL_COMMIT}" >&2
  exit 1
fi

(
  cd "${DRCOSARC_UPSTREAM_DIR}"
  sha256sum -c "${ROOT_DIR}/vendor_lock/DRCOSARC_SHA256SUMS.txt"
)

echo "Pinned official DR-COSARC source ready at ${DRCOSARC_UPSTREAM_DIR}"
