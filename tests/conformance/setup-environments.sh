#!/usr/bin/env bash
# Reproduce the conformance Python venv under tmp/.
# Idempotent. Network use: PyPI (approved pins).
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
TMP="$ROOT/tmp"
VENV="$TMP/oasis-conformance"

mkdir -p "$TMP"

# Python
if [ ! -x "$VENV/bin/python" ]; then
  rm -rf "$VENV"
  if ! python3 -m venv "$VENV" 2>/dev/null; then
    # Hosts without python3-venv (no ensurepip): use the already-installed uv.
    rm -rf "$VENV"
    uv venv --python "$(command -v python3)" "$VENV"
  fi
fi
if "$VENV/bin/python" -m pip --version >/dev/null 2>&1; then
  "$VENV/bin/python" -m pip install --quiet --disable-pip-version-check \
    -r "$ROOT/tests/conformance/requirements-lock.txt"
else
  uv pip install --quiet --python "$VENV/bin/python" \
    -r "$ROOT/tests/conformance/requirements-lock.txt"
fi
"$VENV/bin/python" -c "import jsonschema, referencing, rfc3339_validator"

cat <<OUT
Environment ready.
Python: $VENV/bin/python
OUT
