"""
particle_effects.py - slicing trail, juice particles, sparks, floating
score text and juice splats.

Performance rule: Tkinter gets slow when thousands of canvas items are
created and deleted.  The particle system and the blade trail therefore
create a fixed *pool* of canvas items once and recycle them (hidden when
unused).  Nothing here grows without limit: every effect has a lifetime and a
hard cap.
"""

import math
import random
from collections import deque

from . import config
from .utils import clamp, ease_out_back, lerp_color

BG = config.COLORS["bg_bottom"]
COLOR_STEPS = 8          # colours are faded in steps to avoid an itemconfig every frame


class CanvasState:
    """Only talks to Tk when a value really changes.

    Every itemconfigure / coords call makes Tk repaint that part of the
    window, even if the value is identical.  Skipping redundant calls is the
    single biggest frame-rate win on macOS.
    """

    def __init__(self, canvas):
        self.canvas = canvas
        self._cache = {}

    def config(self, item, **options):
        changed = {k: v for k, v in options.items() if self._cache.get((item, k)) != v}
        if changed:
            for k, v in changed.items():
                self._cache[(item, k)] = v
            self.canvas.itemconfigure(item, **changed)

    def coords(self, item, *xy):
        xy = tuple(round(v, 1) for v in xy)
        if self._cache.get((item, "xy")) != xy:
            self._cache[(item, "xy")] = xy
            self.canvas.coords(item, *xy)

    def forget(self, item):
        for key in [k for k in self._cache if k[0] == item]:
            del self._cache[key]


class Particle:
    __slots__ = ("x", "y", "vx", "vy", "life", "max_life", "size", "color",
                 "gravity", "drag", "item", "step")

    def __init__(self, item):
        self.item = item
        self.life = 0.0
        self.max_life = 1.0
        self.step = -1


class ParticleSystem:
    """Pooled glowing particles (juice drops, sparks, smoke)."""

    def __init__(self, canvas, capacity=config.MAX_PARTICLES, rng=random):
        self.canvas = canvas
        self.rng = rng
        self.free = []
        self.active = []
        for _ in range(capacity):
            item = canvas.create_oval(0, 0, 0, 0, fill="#ffffff", width=0, state="hidden",
                                      tags=("particle",))
            self.free.append(Particle(item))

    def emit(self, x, y, color, count, speed=(120, 420), size=(2, 6), life=(0.35, 0.8),
             gravity=600.0, drag=1.5, spread=(0, 360), lift=0.0):
        """Spawn up to ``count`` particles (silently fewer if the pool is used up)."""
        for _ in range(count):
            if not self.free:
                return
            p = self.free.pop()
            a = math.radians(self.rng.uniform(*spread))
            s = self.rng.uniform(*speed)
            p.x, p.y = x, y
            p.vx, p.vy = math.cos(a) * s, math.sin(a) * s - lift
            p.max_life = p.life = self.rng.uniform(*life)
            p.size = self.rng.uniform(*size)
            p.color = color
            p.gravity, p.drag = gravity, drag
            p.step = -1
            self.canvas.itemconfigure(p.item, state="normal", fill=color)
            self.active.append(p)

    def update(self, dt, ox=0.0, oy=0.0):
        canvas = self.canvas
        still_alive = []
        for p in self.active:
            p.life -= dt
            if p.life <= 0:
                canvas.itemconfigure(p.item, state="hidden")
                self.free.append(p)
                continue
            damp = max(0.0, 1.0 - p.drag * dt)
            p.vx *= damp
            p.vy = p.vy * damp + p.gravity * dt
            p.x += p.vx * dt
            p.y += p.vy * dt
            t = p.life / p.max_life                       # 1 -> 0
            r = max(0.6, p.size * (0.35 + 0.65 * t))
            canvas.coords(p.item, p.x - r + ox, p.y - r + oy, p.x + r + ox, p.y + r + oy)
            step = int((1 - t) * COLOR_STEPS)
            if step != p.step:
                p.step = step
                canvas.itemconfigure(p.item, fill=lerp_color(p.color, BG, step / (COLOR_STEPS + 1)))
            still_alive.append(p)
        self.active = still_alive

    def clear(self):
        for p in self.active:
            self.canvas.itemconfigure(p.item, state="hidden")
            self.free.append(p)
        self.active = []

    def __len__(self):
        return len(self.active)


class BladeTrail:
    """Tapered glowing trail that follows the fingertip.

    Each segment is drawn twice: a wide coloured 'glow' line and a thin white
    'core' line on top.  Older segments are thinner, so the trail tapers.
    """

    def __init__(self, canvas, max_points=config.TRAIL_MAX_POINTS, lifetime=config.TRAIL_LIFETIME):
        self.canvas = canvas
        self.lifetime = lifetime
        self.points = deque(maxlen=max_points)
        n = max_points - 1
        self.glow = [canvas.create_line(0, 0, 0, 0, fill=config.COLORS["blade_glow"], width=1,
                                        capstyle="round", state="hidden", tags=("trail",)) for _ in range(n)]
        self.core = [canvas.create_line(0, 0, 0, 0, fill=config.COLORS["blade_core"], width=1,
                                        capstyle="round", state="hidden", tags=("trail",)) for _ in range(n)]
        self._shown = 0

    def add(self, x, y, t, active):
        self.points.append((x, y, t, active))

    def reset(self):
        self.points.clear()
        self._hide_from(0)

    def _hide_from(self, index):
        for i in range(index, self._shown):
            self.canvas.itemconfigure(self.glow[i], state="hidden")
            self.canvas.itemconfigure(self.core[i], state="hidden")
        self._shown = min(self._shown, index)

    def update(self, now):
        while self.points and now - self.points[0][2] > self.lifetime:
            self.points.popleft()
        pts = list(self.points)
        n = len(pts) - 1
        canvas = self.canvas
        for i in range(max(n, 0)):
            x0, y0, t0, _ = pts[i]
            x1, y1, t1, active = pts[i + 1]
            age = clamp((now - t1) / self.lifetime, 0.0, 1.0)
            taper = (i + 1) / n * (1 - age)                # 0 at the tail, 1 at the tip
            if active:
                glow_w, core_w = 4 + 14 * taper, 1 + 5 * taper
                glow_c = lerp_color(config.COLORS["blade_glow"], config.COLORS["accent"], 1 - taper)
            else:
                glow_w, core_w = 2 + 5 * taper, 1 + 1.5 * taper
                glow_c = config.COLORS["blade_idle"]
            canvas.coords(self.glow[i], x0, y0, x1, y1)
            canvas.coords(self.core[i], x0, y0, x1, y1)
            canvas.itemconfigure(self.glow[i], width=glow_w, fill=glow_c, state="normal")
            canvas.itemconfigure(self.core[i], width=core_w, state="normal" if active else "hidden")
        self._shown = max(self._shown, n)
        self._hide_from(max(n, 0))


class FloatingText:
    """'+10', 'COMBO x3' ... pops in, rises and fades out."""

    def __init__(self, canvas, x, y, text, color, size, family, life=0.9, rise=70, below=None):
        self.canvas = canvas
        self.x, self.y = x, y
        self.color, self.size, self.family = color, size, family
        self.life = self.max_life = life
        self.rise = rise
        self.shadow = canvas.create_text(x + 2, y + 3, text=text, fill="#000000",
                                         font=(family, size, "bold"), tags=("floattext",))
        self.item = canvas.create_text(x, y, text=text, fill=color, font=(family, size, "bold"),
                                       tags=("floattext",))
        if below is not None:
            canvas.tag_lower(self.shadow, below)
            canvas.tag_lower(self.item, below)
        self._last_size = size

    def update(self, dt):
        self.life -= dt
        if self.life <= 0:
            self.destroy()
            return False
        age = 1 - self.life / self.max_life
        y = self.y - self.rise * age
        scale = ease_out_back(min(age / 0.18, 1.0))
        size = max(6, int(self.size * (0.5 + 0.5 * scale)))
        self.canvas.coords(self.item, self.x, y)
        self.canvas.coords(self.shadow, self.x + 2, y + 3)
        fade = clamp((age - 0.55) / 0.45, 0, 1)
        if size != self._last_size:
            self._last_size = size
            font = (self.family, size, "bold")
            self.canvas.itemconfigure(self.item, font=font)
            self.canvas.itemconfigure(self.shadow, font=font)
        self.canvas.itemconfigure(self.item, fill=lerp_color(self.color, BG, fade))
        self.canvas.itemconfigure(self.shadow, state="hidden" if fade > 0.4 else "normal")
        return True

    def destroy(self):
        self.canvas.delete(self.item)
        self.canvas.delete(self.shadow)


class Splat:
    """Juice stain on the background that fades out in a few steps."""

    def __init__(self, canvas, x, y, frames, below=None, life=config.SPLAT_LIFETIME):
        self.canvas = canvas
        self.frames = frames
        self.life = self.max_life = life
        self.item = canvas.create_image(x, y, image=frames[0], tags=("splat",))
        if below is not None:
            canvas.tag_lower(self.item, below)
        self.level = 0

    def update(self, dt):
        self.life -= dt
        if self.life <= 0:
            self.destroy()
            return False
        age = 1 - self.life / self.max_life
        level = min(len(self.frames) - 1, int(max(0.0, age - 0.35) / 0.65 * len(self.frames)))
        if level != self.level:
            self.level = level
            self.canvas.itemconfigure(self.item, image=self.frames[level])
        return True

    def destroy(self):
        self.canvas.delete(self.item)
