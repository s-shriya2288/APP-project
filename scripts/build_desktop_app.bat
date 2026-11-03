@echo off
REM Build a double-click desktop app with PyInstaller (Windows).
REM Run from the project root with the virtual environment activated:
REM   pip install -r requirements-dev.txt
REM   scripts\build_desktop_app.bat
cd /d "%~dp0\.."
pyinstaller --noconfirm --clean --windowed ^
  --name GestureSlice ^
  --hidden-import gesture_slice.ui ^
  main.py
echo Built dist\GestureSlice\GestureSlice.exe
