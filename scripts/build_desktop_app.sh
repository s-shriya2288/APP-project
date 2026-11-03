#!/usr/bin/env bash
# Build a double-click desktop app with PyInstaller.
#   macOS  -> dist/GestureSlice.app
#   Linux  -> dist/GestureSlice/GestureSlice
# Run from the project root with the virtual environment activated:
#   pip install -r requirements-dev.txt && ./scripts/build_desktop_app.sh
set -euo pipefail
cd "$(dirname "$0")/.."

pyinstaller --noconfirm --clean --windowed \
  --name GestureSlice \
  --hidden-import gesture_slice.ui \
  --osx-bundle-identifier com.gamingarcade.gestureslice \
  main.py

if [[ "$(uname)" == "Darwin" ]]; then
  echo "Built dist/GestureSlice.app  (open it with: open dist/GestureSlice.app)"
else
  echo "Built dist/GestureSlice/GestureSlice"
fi
