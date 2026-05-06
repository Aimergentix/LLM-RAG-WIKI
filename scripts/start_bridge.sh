#!/usr/bin/env bash
# K3 convenience wrapper for the Spark bridge (ADR-0003).
#
# Loads SPARK_BRIDGE_TOKEN from spark/.env.local (gitignored), falls back to
# the caller's environment. Hard-codes the host to a loopback default so a
# typo cannot bind 0.0.0.0. Pass --host / --port to override the port only;
# any non-loopback host is rejected.
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ENV_FILE="${REPO_ROOT}/spark/.env.local"
HOST="${SPARK_BRIDGE_HOST:-127.0.0.1}"
PORT="${SPARK_BRIDGE_PORT:-8765}"

while [[ $# -gt 0 ]]; do
  case "$1" in
    --host) HOST="$2"; shift 2 ;;
    --port) PORT="$2"; shift 2 ;;
    *) echo "Unknown arg: $1" >&2; exit 2 ;;
  esac
done

case "${HOST}" in
  127.0.0.1|localhost|::1) ;;
  *)
    echo "Refusing to bind ${HOST}: ADR-0003 section 1 requires loopback." >&2
    exit 3
    ;;
esac

if [[ -z "${SPARK_BRIDGE_TOKEN:-}" && -f "${ENV_FILE}" ]]; then
  # Source only the VITE_BRIDGE_TOKEN line, never echo it.
  TOKEN_LINE="$(grep -E '^VITE_BRIDGE_TOKEN=' "${ENV_FILE}" || true)"
  if [[ -n "${TOKEN_LINE}" ]]; then
    export SPARK_BRIDGE_TOKEN="${TOKEN_LINE#VITE_BRIDGE_TOKEN=}"
  fi
fi

if [[ -z "${SPARK_BRIDGE_TOKEN:-}" ]]; then
  echo "SPARK_BRIDGE_TOKEN unset and not found in ${ENV_FILE}" >&2
  echo "Set it in the environment or copy spark/.env.example to .env.local." >&2
  exit 4
fi

cd "${REPO_ROOT}"

# Prefer the project venv if present, fall back to PATH python.
if [[ -x "${REPO_ROOT}/.venv/bin/python" ]]; then
  PY="${REPO_ROOT}/.venv/bin/python"
else
  PY="$(command -v python3 || command -v python)"
fi
if [[ -z "${PY}" ]]; then
  echo "No python interpreter found. Activate the venv or install python3." >&2
  exit 5
fi

# `src/` is the source layout root; uvicorn must see the layer packages
# (rag, wiki, persona_mcp, spark_bridge) at the top level.
export PYTHONPATH="${REPO_ROOT}/src${PYTHONPATH:+:${PYTHONPATH}}"

exec "${PY}" -m uvicorn spark_bridge.app:app --host "${HOST}" --port "${PORT}"
