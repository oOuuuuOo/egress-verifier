#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
TARGETS_FILE="${SCRIPT_DIR}/../assets/targets.toml"
VERIFIER="${SCRIPT_DIR}/openclaw_egress_verifier.py"

if [[ -n "${OPENCLAW_EGRESS_PYTHON:-}" ]]; then
  PYTHON_BIN="${OPENCLAW_EGRESS_PYTHON}"
elif [[ -x "${SCRIPT_DIR}/../venv/bin/python" ]]; then
  PYTHON_BIN="${SCRIPT_DIR}/../venv/bin/python"
elif [[ -x "/home/split-tunnel/venv/bin/python" ]]; then
  PYTHON_BIN="/home/split-tunnel/venv/bin/python"
else
  PYTHON_BIN="python3"
fi

exec "${PYTHON_BIN}" "${VERIFIER}" "$@" -c "${TARGETS_FILE}"
