#!/usr/bin/env bash
# Stand up the Lean verification environment on a fleet node (designed for ren4).
#
# Idempotent. Places the toolchain and mathlib cache on the fast /models SSD because
# ren4's internal NVMe (FIKWOT) is broken (~20 MB/s) — see docs/LEAN.md. Run:
#   scp scripts/setup-lean-checker.sh ren4:/tmp/ && ssh ren4 'bash /tmp/setup-lean-checker.sh'
set -euo pipefail

FAST_DISK="/models"
ELAN_HOME="${FAST_DISK}/.elan"
PROJECT_DIR="${FAST_DISK}/proving-ground-lean"
REPL_DIR="${FAST_DISK}/repl"
SAFEVERIFY_DIR="${FAST_DISK}/safeverify"
TOOLCHAIN="leanprover/lean4:v4.31.0-rc1"

echo "==> Preflight: confirm ${FAST_DISK} is mounted (FIKWOT NVMe is broken; need the SSD)"
if ! mountpoint -q "${FAST_DISK}"; then
  echo "ERROR: ${FAST_DISK} is not mounted. Run: sudo mount ${FAST_DISK}" >&2
  echo "Refusing to write GBs of mathlib cache to the slow internal disk." >&2
  exit 1
fi

export ELAN_HOME
export PATH="${ELAN_HOME}/bin:${PATH}"

echo "==> Installing elan (Lean toolchain manager) into ${ELAN_HOME}"
if ! command -v elan >/dev/null 2>&1; then
  curl -fsSL https://raw.githubusercontent.com/leanprover/elan/master/elan-init.sh \
    | sh -s -- -y --default-toolchain "${TOOLCHAIN}"
fi
elan --version

echo "==> Creating Lean project at ${PROJECT_DIR}"
mkdir -p "${PROJECT_DIR}/ProvingGround"
# Copy the repo's lean/ scaffold here. Assumes this repo is checked out; adjust REPO if not.
REPO="${REPO:-$HOME/code/proving-ground}"
if [ -d "${REPO}/lean" ]; then
  cp -r "${REPO}/lean/." "${PROJECT_DIR}/"
else
  echo "NOTE: ${REPO}/lean not found; using the pinned toolchain only. Clone the repo and re-run, or set REPO=." >&2
fi

cd "${PROJECT_DIR}"
echo "==> Resolving dependencies + fetching prebuilt mathlib cache (NOT building from source)"
lake update
lake exe cache get
lake build

echo "==> Building the proof-checking REPL into ${REPL_DIR}"
if [ ! -d "${REPL_DIR}" ]; then
  git clone --depth 1 https://github.com/leanprover-community/repl "${REPL_DIR}"
fi
( cd "${REPL_DIR}" && lake build )

echo "==> Building SafeVerify (anti-cheat gates) into ${SAFEVERIFY_DIR}"
if [ ! -d "${SAFEVERIFY_DIR}" ]; then
  git clone --depth 1 https://github.com/GasStationManager/SafeVerify "${SAFEVERIFY_DIR}"
fi
( cd "${SAFEVERIFY_DIR}" && (lake exe cache get || true) && lake build )

echo ""
echo "==> Done. Environment ready:"
echo "    ELAN_HOME=${ELAN_HOME}"
echo "    project=${PROJECT_DIR}  repl=${REPL_DIR}  safeverify=${SAFEVERIFY_DIR}"
echo "    Add ELAN_HOME to the service env that runs the checker."
