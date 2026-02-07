#!/bin/bash
DIR="$(cd "$(dirname "$0")" && pwd)"
for p in /opt/homebrew/bin/python3 /usr/local/bin/python3 /usr/bin/python3 python3; do
    if command -v "$p" &>/dev/null; then exec "$p" "$DIR/subtitle_sync_gui.py"; fi
done
echo "未找到 Python 3，请安装: brew install python3"
read -p "按回车退出..."
