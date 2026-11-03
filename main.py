"""
main.py - entry point of Gesture Slice.

    python main.py

Checks that the required packages are installed, then opens the Tkinter
window.  The game is played with the trackpad or mouse.
"""

import importlib.util
import sys


def check_dependencies():
    missing = [package for module, package in (("numpy", "numpy"), ("PIL", "Pillow"))
               if importlib.util.find_spec(module) is None]
    if importlib.util.find_spec("tkinter") is None:
        missing.append("tkinter (install Python from python.org, or 'sudo apt install python3-tk')")
    return missing


def main():
    if sys.version_info < (3, 9):
        sys.exit("Gesture Slice needs Python 3.9 or newer (3.11 recommended).")
    missing = check_dependencies()
    if missing:
        sys.exit("Missing packages: " + ", ".join(missing) +
                 "\nInstall them with:  pip install -r requirements.txt")

    from gesture_slice.ui import App
    App().run()


if __name__ == "__main__":
    main()
