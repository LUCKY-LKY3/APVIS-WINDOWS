#!/bin/bash
# Copy APVIS Home (Python + QML + art + geo data) from an APVIS-OS checkout into app/.
# usage: scripts/sync-from-apvis-os.sh [path to APVIS-OS checkout on branch v3]
set -euo pipefail
SRC=${1:-"C:/Users/Lucky/Documents/ChatGPT/Vibecoded Apps/APVIS-OS-V2"}
ROOT=$(cd "$(dirname "$0")/.." && pwd)
PY="$SRC/config/includes.chroot/usr/lib/python3/dist-packages/apvis_os"
SHARE="$SRC/config/includes.chroot/usr/share/apvis-os"
rm -rf "$ROOT/app"
mkdir -p "$ROOT/app"
cp -r "$PY" "$ROOT/app/apvis_os"
cp -r "$SHARE/qml" "$ROOT/app/qml"
cp -r "$SHARE/geo" "$ROOT/app/geo"
find "$ROOT/app" -name "__pycache__" -type d -prune -exec rm -rf {} +
( cd "$SRC" && git log --oneline -1 ) > "$ROOT/app/SOURCE"
echo "synced from $(cat "$ROOT/app/SOURCE")"
