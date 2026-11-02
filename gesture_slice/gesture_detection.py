"""
gesture_detection.py - turns raw hand landmarks (or mouse movement) into
game input: a smoothed blade position, its speed, the cut segment since the
previous frame, and pause / resume commands.

Pipeline for every HandSample:

    landmark 8 (index fingertip, 0..1)
        -> map the camera's active box onto the canvas (pixels)
        -> One Euro filter (removes jitter, keeps fast swipes responsive)
        -> segment previous -> current point + speed in px/s
    all 21 landmarks
        -> classify pose: POINT / OPEN_PALM / FIST / NONE
        -> hold timer: palm held 0.7 s = "pause", fist held 0.7 s = "resume"
"""

import math
from dataclasses import dataclass
from enum import Enum

import numpy as np

from . import config
from .utils import clamp

# MediaPipe landmark indices
WRIST = 0
THUMB_TIP, THUMB_IP = 4, 3
INDEX_MCP = 5
MIDDLE_MCP = 9
PINKY_MCP = 17
FINGER_TIPS = (8, 12, 16, 20)     # index, middle, ring, pinky
FINGER_PIPS = (6, 10, 14, 18)     # the middle joint of the same fingers
INDEX_TIP = 8


class Gesture(str, Enum):
    NONE = "none"
    POINT = "point"
    OPEN_PALM = "open_palm"
    FIST = "fist"


GESTURE_EVENTS = {Gesture.OPEN_PALM: "pause", Gesture.FIST: "resume"}


# --------------------------------------------------------------------------
# One Euro filter  (Casiez, Roussel & Vogel, CHI 2012)
# --------------------------------------------------------------------------
class OneEuroFilter:
    """Adaptive low-pass filter.

    When the finger is almost still the cut-off frequency is low, so jitter
    is smoothed away.  When the finger moves fast the cut-off rises with the
    speed, so the blade does not lag behind a swipe.
    """

    def __init__(self, min_cutoff=config.ONE_EURO_MIN_CUTOFF,
                 beta=config.ONE_EURO_BETA, d_cutoff=config.ONE_EURO_D_CUTOFF):
        self.min_cutoff = min_cutoff
        self.beta = beta
        self.d_cutoff = d_cutoff
        self.reset()

    def reset(self):
        self._x = None
        self._dx = 0.0
        self._t = None

    @staticmethod
    def _alpha(cutoff, dt):
        tau = 1.0 / (2 * math.pi * cutoff)
        return 1.0 / (1.0 + tau / dt)

    def __call__(self, x, t):
        if self._x is None:
            self._x, self._t = x, t
            return x
        dt = max(t - self._t, 1e-4)
        self._t = t
        dx = (x - self._x) / dt
        a_d = self._alpha(self.d_cutoff, dt)
        self._dx = a_d * dx + (1 - a_d) * self._dx
        cutoff = self.min_cutoff + self.beta * abs(self._dx)
        a = self._alpha(cutoff, dt)
        self._x = a * x + (1 - a) * self._x
        return self._x


# --------------------------------------------------------------------------
# Output of one detector update
# --------------------------------------------------------------------------
@dataclass
class PointerFrame:
    present: bool                       # is there a hand / pointer at all
    x: float = 0.0
    y: float = 0.0
    speed: float = 0.0                  # px/s of the latest movement
    segment: tuple = None               # (ax, ay, bx, by, speed) or None
    gesture: Gesture = Gesture.NONE
    hold_progress: float = 0.0          # 0..1 while palm / fist is being held
    event: str = None                   # "pause" / "resume" when confirmed
    timestamp: float = 0.0


# --------------------------------------------------------------------------
# Motion tracking shared by hand and mouse input
# --------------------------------------------------------------------------
class MotionTracker:
    """Remembers the previous point and produces cut segments with speed."""

    def __init__(self, max_gap=config.MAX_SEGMENT_GAP):
        self.max_gap = max_gap
        self.reset()

    def reset(self):
        self.prev = None          # (x, y, t)
        self.speed = 0.0

    def update(self, x, y, t):
        segment = None
        if self.prev is not None:
            px, py, pt = self.prev
            dt = t - pt
            if 0 < dt <= self.max_gap:
                seg_speed = math.hypot(x - px, y - py) / dt
                # light smoothing of the *reported* speed (segments keep the raw one)
                self.speed = 0.5 * self.speed + 0.5 * seg_speed
                segment = (px, py, x, y, seg_speed)
            elif dt > self.max_gap:
                self.speed = 0.0
        self.prev = (x, y, t)
        return segment


# --------------------------------------------------------------------------
# Hand gesture detector
# --------------------------------------------------------------------------
class GestureDetector:
    """Converts HandSamples into PointerFrames."""

    def __init__(self, width=config.WIDTH, height=config.HEIGHT,
                 active_region=config.CAMERA_ACTIVE_REGION,
                 hold_seconds=config.GESTURE_HOLD_SECONDS,
                 max_hold_speed=config.GESTURE_MAX_HOLD_SPEED,
                 cooldown=config.GESTURE_COOLDOWN,
                 glitch_tolerance=config.GESTURE_GLITCH_TOLERANCE):
        self.width, self.height = width, height
        self.region = active_region
        self.hold_seconds = hold_seconds
        self.max_hold_speed = max_hold_speed
        self.cooldown = cooldown
        self.glitch_tolerance = glitch_tolerance
        self.filter_x = OneEuroFilter()
        self.filter_y = OneEuroFilter()
        self.motion = MotionTracker()
        self.reset()

    def reset(self):
        self.filter_x.reset()
        self.filter_y.reset()
        self.motion.reset()
        self._hold_gesture = Gesture.NONE
        self._hold_start = 0.0
        self._last_seen = 0.0
        self._fired = False
        self._last_event_time = -1e9
        self.last = PointerFrame(present=False)

    # --- coordinate conversion -------------------------------------------
    def map_to_canvas(self, nx, ny):
        """Stretch the camera's active box onto the full canvas (clamped)."""
        x0, y0, x1, y1 = self.region
        u = clamp((nx - x0) / (x1 - x0), 0.0, 1.0)
        v = clamp((ny - y0) / (y1 - y0), 0.0, 1.0)
        return u * self.width, v * self.height

    # --- pose classification -----------------------------------------------
    @staticmethod
    def classify(landmarks):
        """Recognise the hand pose from its 21 landmarks.

        A finger counts as *extended* when its tip is clearly further from
        the wrist than its middle (PIP) joint.  Using distance ratios makes
        the test independent of how far the hand is from the camera and of
        hand rotation.
        """
        if landmarks is None or len(landmarks) < 21:
            return Gesture.NONE
        pts = np.asarray(landmarks, dtype=float)
        pts[:, 0] *= config.CAMERA_WIDTH / config.CAMERA_HEIGHT   # undo 4:3 squash
        wrist = pts[WRIST]
        tip_d = np.linalg.norm(pts[list(FINGER_TIPS)] - wrist, axis=1)
        pip_d = np.linalg.norm(pts[list(FINGER_PIPS)] - wrist, axis=1)
        extended = tip_d > pip_d * 1.12
        curled = tip_d < pip_d * 1.02
        palm_size = np.linalg.norm(pts[MIDDLE_MCP] - wrist) + 1e-6
        thumb_out = np.linalg.norm(pts[THUMB_TIP] - pts[INDEX_MCP]) > 0.55 * palm_size

        if extended.all() and thumb_out:
            return Gesture.OPEN_PALM
        if curled.all():
            return Gesture.FIST
        if extended[0] and curled[1:].sum() >= 2:
            return Gesture.POINT
        return Gesture.NONE

    # --- main update -----------------------------------------------------------
    def update(self, sample):
        """Process one HandSample and return a PointerFrame."""
        t = sample.timestamp
        if sample.landmarks is None:
            # Hand lost: forget the old position so the next appearance does not
            # create a giant segment that slices everything in between.
            self.filter_x.reset()
            self.filter_y.reset()
            self.motion.reset()
            self._hold_gesture = Gesture.NONE
            self._fired = False
            self.last = PointerFrame(present=False, timestamp=t)
            return self.last

        nx, ny = sample.landmarks[INDEX_TIP]
        raw_x, raw_y = self.map_to_canvas(nx, ny)
        x = self.filter_x(raw_x, t)
        y = self.filter_y(raw_y, t)
        segment = self.motion.update(x, y, t)
        speed = self.motion.speed

        gesture = self.classify(sample.landmarks)
        progress, event = self._update_hold(gesture, speed, t)

        self.last = PointerFrame(True, x, y, speed, segment, gesture, progress, event, t)
        return self.last

    def _update_hold(self, gesture, speed, t):
        """Gesture confirmation: a pose only counts after being held still."""
        if gesture == self._hold_gesture:
            self._last_seen = t
        elif t - self._last_seen > self.glitch_tolerance:
            # A *different* pose has lasted long enough: start a new hold.
            self._hold_gesture = gesture
            self._hold_start = t
            self._last_seen = t
            self._fired = False

        if self._hold_gesture not in GESTURE_EVENTS or self._fired:
            return 0.0, None
        if speed > self.max_hold_speed:          # moving hand = slicing, not a command
            self._hold_start = t
            return 0.0, None
        if t - self._last_event_time < self.cooldown:
            self._hold_start = t
            return 0.0, None

        progress = clamp((t - self._hold_start) / self.hold_seconds, 0.0, 1.0)
        if progress >= 1.0:
            self._fired = True
            self._last_event_time = t
            return 1.0, GESTURE_EVENTS[self._hold_gesture]
        return progress, None


class MouseDetector:
    """Keyboard / mouse fallback that produces the same PointerFrames."""

    def __init__(self):
        self.motion = MotionTracker()
        self.last = PointerFrame(present=False)

    def reset(self):
        self.motion.reset()

    def update(self, x, y, t):
        segment = self.motion.update(x, y, t)
        self.last = PointerFrame(True, x, y, self.motion.speed, segment, timestamp=t)
        return self.last
