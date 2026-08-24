#!/usr/bin/env bash
# Dev launcher: runs Encantado straight from this checkout, no install needed.
# If you have pip-installed the package, just run `encantado` instead.
set -euo pipefail
cd "$(dirname "$0")"

PY="${ENCANTADO_PYTHON:-}"
if [ -z "$PY" ]; then
  for cand in python3 python; do
    if command -v "$cand" >/dev/null 2>&1 &&
       "$cand" -c 'import PyQt6, numpy, scipy' >/dev/null 2>&1; then
      PY="$cand"; break
    fi
  done
fi
if [ -z "$PY" ]; then
  echo "No interpreter found with PyQt6, numpy and scipy." >&2
  echo "Set ENCANTADO_PYTHON=/path/to/python, or: pip install -e ." >&2
  exit 1
fi
exec "$PY" -m encantado "$@"
