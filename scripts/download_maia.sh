#!/usr/bin/env bash
# Download Maia weight files used for human-like sparring.
# Source: https://github.com/CSSLab/maia-chess (weights are released per rating band).
set -euo pipefail

DEST="${MAIA_WEIGHTS_DIR:-engines/weights}"
mkdir -p "$DEST"
BASE="https://github.com/CSSLab/maia-chess/raw/master/maia_weights"

for band in 1100 1300 1500 1700 1900; do
  out="$DEST/maia-${band}.pb.gz"
  if [ -f "$out" ]; then
    echo "have  maia-${band}"
    continue
  fi
  echo "fetch maia-${band}"
  curl -fsSL "${BASE}/maia-${band}.pb.gz" -o "$out" || {
    echo "  failed; see engines/README.md for manual download" >&2
    rm -f "$out"
  }
done
echo "Weights in $DEST:"; ls -1 "$DEST" 2>/dev/null || true
