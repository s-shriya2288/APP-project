"""
mouse_input.py - turns mouse / trackpad movement into game input.

Every <Motion> event gives a point (x, y, time).  Two points in a row make a
"cut segment" A -> B, and its length divided by the time between them is the
blade speed in pixels per second.  The game only slices fruit with segments
that are fast enough, so slow movements just aim.
"""

import math
from dataclasses import dataclass

from . import config


@dataclass
class PointerFrame:
    present: bool                       # has the pointer been seen at all
    x: float = 0.0
    y: float = 0.0
    speed: float = 0.0                  # px/s of the latest movement
    segment: tuple = None               # (ax, ay, bx, by, speed) or None
    timestamp: float = 0.0


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


class MouseDetector:
    """Converts mouse / trackpad positions into PointerFrames."""

    def __init__(self):
        self.motion = MotionTracker()
        self.last = PointerFrame(present=False)

    def reset(self):
        self.motion.reset()

    def update(self, x, y, t):
        segment = self.motion.update(x, y, t)
        self.last = PointerFrame(True, x, y, self.motion.speed, segment, timestamp=t)
        return self.last
