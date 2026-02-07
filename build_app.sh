#!/usr/bin/env bash
set -euo pipefail

python3 -m pip install --upgrade pyinstaller
pyinstaller --noconfirm --windowed --name SubSyncPro subtitle_sync_gui.py

echo "Build complete: dist/SubSyncPro"
