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
  --collect-data mediapipe \
  --collect-binaries mediapipe \
  --hidden-import gesture_slice.ui \
  --osx-bundle-identifier com.gamingarcade.gestureslice \
  main.py

if [[ "$(uname)" == "Darwin" ]]; then
  # Without this key macOS refuses camera access for the bundled app.
  /usr/libexec/PlistBuddy -c \
    "Add :NSCameraUsageDescription string 'Gesture Slice uses the camera to track your hand.'" \
    dist/GestureSlice.app/Contents/Info.plist 2>/dev/null || true
  echo "Built dist/GestureSlice.app  (open it with: open dist/GestureSlice.app)"
else
  echo "Built dist/GestureSlice/GestureSlice"
fi
