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
GAME_SUBTITLE = "Gaming Arcade  -  slice fruit with your bare hand"

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
# Colour palette (dark neon arcade theme)
# --------------------------------------------------------------------------
COLORS = {
    "bg_top": "#1a0f3d",
    "bg_bottom": "#04050d",
    "bg_flat": "#0b0920",          # used by Tk widgets that cannot show images
    "panel": "#1b1640",
    "panel_edge": "#4a3b99",
    "text": "#f5f3ff",
    "muted": "#a59fd0",
    "dim": "#5d5791",
    "accent": "#ff4fa3",           # pink
    "accent2": "#36e2ff",          # cyan
    "gold": "#ffd447",
    "danger": "#ff3b5c",
    "success": "#3df5a1",
    "warning": "#ffb020",
    "blade_core": "#ffffff",
    "blade_glow": "#36e2ff",
    "blade_idle": "#6b7bbd",
}

# Font families tried in order; the first one installed is used.
FONT_CANDIDATES = (
    "Avenir Next", "Segoe UI", "Helvetica Neue", "Ubuntu",
    "Noto Sans", "DejaVu Sans", "Helvetica", "Arial",
)

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
# Camera / MediaPipe
# --------------------------------------------------------------------------
CAMERA_INDEX_OPTIONS = (0, 1, 2)
DEFAULT_CAMERA_INDEX = 0
CAMERA_WIDTH = 640
CAMERA_HEIGHT = 480
# Part of the (mirrored) camera image that is stretched onto the whole game
# canvas.  Your hand rarely reaches the very edge of the frame, so mapping an
# inner box makes it easy to reach every corner of the screen.
CAMERA_ACTIVE_REGION = (0.12, 0.10, 0.88, 0.82)   # x0, y0, x1, y1 (normalised)
MP_MAX_HANDS = 1
MP_MODEL_COMPLEXITY = 0                # 0 = fastest model, ideal for games
MP_DETECTION_CONFIDENCE = 0.6
MP_TRACKING_CONFIDENCE = 0.5
PREVIEW_SIZE = (192, 144)
CAMERA_FAIL_LIMIT = 30                 # consecutive failed reads = disconnected
CAMERA_RECONNECT_SECONDS = 1.5
CAMERA_START_RETRIES = 10             # retries (3 s apart) while waiting for permission
SAMPLE_QUEUE_SIZE = 32

# --------------------------------------------------------------------------
# Gesture detection
# --------------------------------------------------------------------------
ONE_EURO_MIN_CUTOFF = 1.4              # lower = smoother when still, more lag
ONE_EURO_BETA = 0.02                   # higher = less lag when moving fast
ONE_EURO_D_CUTOFF = 1.0
GESTURE_HOLD_SECONDS = 0.7             # palm / fist must be held this long
GESTURE_MAX_HOLD_SPEED = 380.0         # hand must be roughly still (px/s)
GESTURE_GLITCH_TOLERANCE = 0.15        # ignore pose flickers shorter than this
GESTURE_COOLDOWN = 1.0                 # seconds between two gesture commands
DWELL_SECONDS = 1.1                    # hover a button this long to press it by hand

# --------------------------------------------------------------------------
# Visual effects
# --------------------------------------------------------------------------
MAX_PARTICLES = 260
MAX_SPLATS = 10
SPLAT_LIFETIME = 1.4
SPRITE_ROTATION_FRAMES = 36            # 10 degree steps for spinning sprites
FADE_STEPS = 6                         # screen transition fade frames

# --------------------------------------------------------------------------
# Defaults for the settings stored in the database
# --------------------------------------------------------------------------
DEFAULT_SETTINGS = {
    "player_name": "Player 1",
    "control_mode": "Gesture",         # "Gesture" (webcam) or "Mouse"
    "camera_index": str(DEFAULT_CAMERA_INDEX),
    "show_preview": "On",
    "sound": "On",
    "round_seconds": str(DEFAULT_ROUND_SECONDS),
    "sensitivity": DEFAULT_SENSITIVITY,
}
