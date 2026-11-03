"""
config.py - every constant the game uses, in one place.

Changing a number here (window size, gravity, gesture timings, colours ...)
changes the behaviour of the whole application without touching the logic.
"""

import sys
from pathlib import Path

# --------------------------------------------------------------------------
# Application / window
# --------------------------------------------------------------------------
APP_TITLE = "Gesture Slice  |  Gaming Arcade"
GAME_TITLE = "GESTURE SLICE"
GAME_SUBTITLE = "Gaming Arcade  -  slice the fruit with your trackpad or mouse"

WIDTH = 1100
HEIGHT = 700

TARGET_FPS = 60
FRAME_MS = 1000 // TARGET_FPS          # ~16 ms between game ticks
MAX_DT = 1 / 20                        # clamp huge frame gaps (window drag etc.)

# --------------------------------------------------------------------------
# Paths
# --------------------------------------------------------------------------
PACKAGE_DIR = Path(__file__).resolve().parent
PROJECT_DIR = PACKAGE_DIR.parent
ASSETS_DIR = PROJECT_DIR / "assets"
IMAGES_DIR = ASSETS_DIR / "images"     # optional PNG overrides, see assets/README.md
# Running from source: keep the database next to the code.  Running as a
# packaged desktop app (PyInstaller) the bundle is read-only, so use the home folder.
DATA_DIR = (Path.home() / ".gesture_slice") if getattr(sys, "frozen", False) else PROJECT_DIR / "data"
DB_PATH = DATA_DIR / "gesture_slice.db"

# --------------------------------------------------------------------------
# Colour palette (simple flat colours)
# --------------------------------------------------------------------------
COLORS = {
    "bg_top": "#22313f",
    "bg_bottom": "#22313f",
    "bg_flat": "#22313f",          # used by Tk widgets such as the name entry
    "panel": "#2c3e50",
    "panel_edge": "#4a6278",
    "text": "#ecf0f1",
    "muted": "#a0aeb8",
    "dim": "#6c7a89",
    "accent": "#e67e22",           # orange
    "accent2": "#3498db",          # blue
    "gold": "#f1c40f",
    "danger": "#e74c3c",
    "success": "#2ecc71",
    "warning": "#f39c12",
    "blade_core": "#ffffff",
    "blade_glow": "#3498db",
    "blade_idle": "#7f8c8d",
}

# Font families tried in order; the first one installed is used.
FONT_CANDIDATES = ("Arial", "Helvetica", "DejaVu Sans")

# --------------------------------------------------------------------------
# Gameplay rules
# --------------------------------------------------------------------------
START_LIVES = 3
ROUND_SECONDS_OPTIONS = (60, 90, 120)
DEFAULT_ROUND_SECONDS = 90
COUNTDOWN_SECONDS = 3

GRAVITY = 900.0                        # px / s^2 at speed multiplier 1.0
NORMAL_POINTS = 10
SPECIAL_POINTS = 20
COMBO_WINDOW = 0.30                    # fruits cut within this many seconds = one combo
COMBO_BONUS_PER_EXTRA_FRUIT = 15       # combo of N fruits -> (N - 1) * 15 bonus
BOMB_INVULNERABLE_SECONDS = 0.6        # no double life-loss from one swipe
MAX_ACTIVE_OBJECTS = 14
GAME_OVER_DELAY = 1.6                  # seconds of "GAME OVER" banner before results

# Score needed to reach level 1, 2, 3, ... (after the list: +LEVEL_STEP each)
LEVEL_SCORE_THRESHOLDS = (0, 150, 400, 750, 1200)
LEVEL_STEP_AFTER = 600

# --------------------------------------------------------------------------
# Blade / slicing
# --------------------------------------------------------------------------
# Minimum blade speed (px/s) for a movement to count as a slice.
SLICE_SENSITIVITY = {"Low": 950.0, "Medium": 650.0, "High": 420.0}
DEFAULT_SENSITIVITY = "Medium"
TRAIL_LIFETIME = 0.20                  # seconds a trail point stays visible
TRAIL_MAX_POINTS = 18
MAX_SEGMENT_GAP = 0.25                 # samples further apart than this never form a cut

# --------------------------------------------------------------------------
# Visual effects
# --------------------------------------------------------------------------
MAX_PARTICLES = 120
MAX_SPLATS = 10
SPLAT_LIFETIME = 1.4
SPRITE_ROTATION_FRAMES = 36            # 10 degree steps for spinning sprites

# --------------------------------------------------------------------------
# Defaults for the settings stored in the database
# --------------------------------------------------------------------------
DEFAULT_SETTINGS = {
    "player_name": "Player 1",
    "sound": "On",
    "round_seconds": str(DEFAULT_ROUND_SECONDS),
    "sensitivity": DEFAULT_SENSITIVITY,
}
