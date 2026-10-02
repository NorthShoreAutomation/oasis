#!/usr/bin/env bash
# Reproduce the conformance Python venv and Go toolchain under tmp/.
# Idempotent. Network use: PyPI (approved pins), go.dev (go1.27.1), proxy.golang.org.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
TMP="$ROOT/tmp"
VENV="$TMP/oasis-conformance"
GO_VERSION="go1.27.1"
GO_TARBALL="$GO_VERSION.linux-amd64.tar.gz"
# Digest published at https://go.dev/dl/?mode=json&include=all
GO_SHA256="63d339f0da5ab53635a56f2490a7984dfe12dfcff22ad749f63edaf590168445"
GO_DIR="$TMP/$GO_VERSION"
MODULE="$ROOT/tests/conformance/go-validator"

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

# Go toolchain
if [ ! -x "$GO_DIR/go/bin/go" ] || [ "$("$GO_DIR/go/bin/go" env GOVERSION)" != "$GO_VERSION" ]; then
  mkdir -p "$GO_DIR"
  curl -fsSL -o "$GO_DIR/$GO_TARBALL" "https://go.dev/dl/$GO_TARBALL"
  actual="$(sha256sum "$GO_DIR/$GO_TARBALL" | cut -d' ' -f1)"
  if [ "$actual" != "$GO_SHA256" ]; then
    echo "SHA-256 mismatch for $GO_TARBALL" >&2
    rm -f "$GO_DIR/$GO_TARBALL"
    exit 1
  fi
  rm -rf "$GO_DIR/go"
  tar -C "$GO_DIR" -xzf "$GO_DIR/$GO_TARBALL"
fi

export GOROOT="$GO_DIR/go"
export PATH="$GOROOT/bin:$PATH"
export GOTOOLCHAIN=local
export GOPATH="$TMP/gopath"
export GOMODCACHE="$TMP/gomodcache"
export GOCACHE="$TMP/gocache"
unset GONOSUMDB GONOSUMCHECK GOFLAGS GOINSECURE GOPRIVATE
export GOPROXY="https://proxy.golang.org"
export GOSUMDB="sum.golang.org"

(cd "$MODULE" && go mod download && go build ./...)

cat <<OUT
Environment ready. Use these variables:
export GOROOT="$GOROOT"
export PATH="$GOROOT/bin:\$PATH"
export GOTOOLCHAIN=local
export GOPATH="$GOPATH"
export GOMODCACHE="$GOMODCACHE"
export GOCACHE="$GOCACHE"
export GOPROXY="$GOPROXY"
export GOSUMDB="$GOSUMDB"
Python: $VENV/bin/python
OUT
