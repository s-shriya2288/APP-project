"""
sprites.py - all graphics are simple shapes drawn in code with Pillow, so the
game needs no image files.

Two layers:
  * pure Pillow functions ``render_*`` that return PIL images, and
  * ``SpriteBank`` which converts them once at start-up into Tk PhotoImages,
    including every rotation frame, so the game loop never has to rotate or
    convert an image while playing.

You can still drop your own art into assets/images/<fruit name>.png - it is
used instead of the generated fruit when present (see assets/README.md).
"""

import math
import random

import numpy as np
from PIL import Image, ImageDraw, ImageFilter

from . import config
from .fruit import BOMB_RADIUS, FRUIT_TYPES
from .utils import hex_to_rgb

SS = 2                      # draw 2x bigger then shrink, for smoother edges
LANCZOS = Image.Resampling.LANCZOS
BICUBIC = Image.Resampling.BICUBIC


# --------------------------------------------------------------------------
# Helpers
# --------------------------------------------------------------------------
def _rgba(color, alpha=255):
    return (*hex_to_rgb(color), alpha)


def _hex(rgb):
    return "#%02x%02x%02x" % tuple(int(max(0, min(255, v))) for v in rgb)


def _star_points(cx, cy, r_outer, r_inner, n=5, rotation=-90):
    pts = []
    for i in range(n * 2):
        rad = r_outer if i % 2 == 0 else r_inner
        a = math.radians(rotation + i * 180 / n)
        pts.append((cx + rad * math.cos(a), cy + rad * math.sin(a)))
    return pts


def _circle(draw, cx, cy, r, **kw):
    draw.ellipse((cx - r, cy - r, cx + r, cy + r), **kw)


# --------------------------------------------------------------------------
# Fruits and bombs (simple flat drawings)
# --------------------------------------------------------------------------
def sprite_size(radius, pad_ratio=0.6):
    return int(2 * radius * (1 + pad_ratio))


def render_fruit(kind):
    """A whole fruit: coloured circle with an outline, stem and leaf."""
    size = sprite_size(kind.radius)
    S, R = size * SS, kind.radius * SS
    c = S / 2
    img = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    _circle(draw, c, c, R, fill=_rgba(kind.skin), outline=_rgba(kind.skin_dark), width=int(R * 0.07))
    if kind.striped:                                   # watermelon stripes
        for f in (0.35, 0.7):
            draw.ellipse((c - R * f, c - R, c + R * f, c + R), outline=_rgba(kind.skin_dark), width=int(R * 0.08))
    if kind.special:                                   # golden star fruit
        draw.polygon(_star_points(c, c, R * 0.6, R * 0.26), fill=_rgba("#fff3a0"), outline=_rgba("#c08a00"))
    _circle(draw, c - R * 0.4, c - R * 0.4, R * 0.15, fill=(255, 255, 255, 255))   # small shine
    if kind.stem:
        draw.line([(c, c - R * 0.9), (c + R * 0.1, c - R * 1.2)], fill=_rgba("#6b4226"), width=int(R * 0.1))
    if kind.leaf:
        draw.ellipse((c + R * 0.1, c - R * 1.2, c + R * 0.6, c - R * 0.95), fill=_rgba("#2ecc71"))
    return img.resize((size, size), LANCZOS)


def render_half(kind):
    """Top half of a sliced fruit; the flat cut edge lies on the centre line."""
    size = sprite_size(kind.radius)
    S, R = size * SS, kind.radius * SS
    c = S / 2
    img = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    box = lambda f: (c - R * f, c - R * f, c + R * f, c + R * f)  # noqa: E731
    draw.pieslice(box(1.0), 180, 360, fill=_rgba(kind.skin))
    draw.pieslice(box(0.82), 180, 360, fill=_rgba(kind.flesh))
    if kind.seed:
        for i in range(5):
            a = math.radians(205 + i * 32)
            _circle(draw, c + R * 0.45 * math.cos(a), c + R * 0.45 * math.sin(a), R * 0.06, fill=_rgba(kind.seed))
    return img.resize((size, size), LANCZOS)


def half_from_image(full):
    """Make a 'half' sprite from a user-supplied full fruit image."""
    w, h = full.size
    arr = np.array(full.copy())
    arr[h // 2:, :, 3] = 0
    return Image.fromarray(arr)


def render_bomb(radius=BOMB_RADIUS):
    """Black ball with a red ring, a grey cap and a fuse."""
    size = sprite_size(radius, 0.62)
    S, R = size * SS, radius * SS
    c = S / 2
    img = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    _circle(draw, c, c, R, fill=_rgba("#2b2b2b"), outline=_rgba(config.COLORS["danger"]), width=int(R * 0.08))
    _circle(draw, c - R * 0.4, c - R * 0.4, R * 0.14, fill=(200, 200, 200, 255))
    draw.text((c - R * 0.12, c - R * 0.35), "!", fill=_rgba(config.COLORS["danger"]))
    draw.rectangle((c - R * 0.22, c - R * 1.08, c + R * 0.22, c - R * 0.86), fill=_rgba("#95a5a6"))
    # fuse ends where Bomb.fuse_tip() expects it
    draw.line([(c, c - R * 1.06), (c + R * 0.62, c - R * 1.28)], fill=_rgba("#d9b27a"), width=int(R * 0.09))
    return img.resize((size, size), LANCZOS)


def render_splat(color, radius, seed):
    """Juice stain left behind the fruit: one blob and a few drops."""
    size = int(radius * 3.2)
    c = size / 2
    rng = random.Random(seed)
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    fill = _rgba(color, 170)
    _circle(draw, c, c, radius * 0.6, fill=fill)
    for _ in range(6):
        a = rng.uniform(0, 2 * math.pi)
        d = rng.uniform(radius * 0.7, radius * 1.3)
        _circle(draw, c + d * math.cos(a), c + d * math.sin(a), rng.uniform(3, 7), fill=fill)
    return img


# --------------------------------------------------------------------------
# Background, panels, buttons, icons
# --------------------------------------------------------------------------
def draw_background(canvas, tag, w=config.WIDTH, h=config.HEIGHT, seed=7):
    """Plain background: one filled rectangle and a ground line."""
    canvas.create_rectangle(0, 0, w, h, fill=config.COLORS["bg_top"], width=0, tags=(tag,))
    canvas.create_line(0, h - 40, w, h - 40, fill=config.COLORS["panel_edge"], width=2, tags=(tag,))


def draw_panel(canvas, tags, cx, cy, w, h, radius=0, fill=None, outline=None, glow=None):
    """A simple rectangle panel."""
    return canvas.create_rectangle(cx - w / 2, cy - h / 2, cx + w / 2, cy + h / 2,
                                   fill=fill or config.COLORS["panel"],
                                   outline=outline or config.COLORS["panel_edge"], width=2, tags=tags)


def render_button(w, h, color_a, color_b=None, hover=False):
    """Flat button with slightly rounded corners (lighter on hover)."""
    S = 2
    img = Image.new("RGBA", (w * S, h * S), (0, 0, 0, 0))
    rgb = np.array(hex_to_rgb(color_a), np.float32)
    if hover:
        rgb = rgb * 0.8 + 255 * 0.2
    ImageDraw.Draw(img).rounded_rectangle((0, 0, w * S - 1, h * S - 1), 6 * S, fill=(*rgb.astype(int), 255),
                                          outline=(255, 255, 255, 255) if hover else _rgba(_hex(rgb * 0.7)),
                                          width=2 * S)
    return img.resize((w, h), LANCZOS)


def render_heart(size, color, filled=True):
    S = size * SS
    img = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    pts = []
    for i in range(120):
        t = i / 120 * 2 * math.pi
        x = 16 * math.sin(t) ** 3
        y = -(13 * math.cos(t) - 5 * math.cos(2 * t) - 2 * math.cos(3 * t) - math.cos(4 * t))
        pts.append((S / 2 + x * S / 36, S / 2 + y * S / 36))
    draw = ImageDraw.Draw(img)
    if filled:
        draw.polygon(pts, fill=_rgba(color))
    else:
        draw.polygon(pts, outline=(127, 140, 141, 255), width=int(S * 0.06))
    return img.resize((size, size), LANCZOS)


def render_hand_icon(kind, size=96, color=config.COLORS["accent2"]):
    """Simple outline icon of a hand pose: 'point', 'palm' or 'fist'."""
    S = size * SS
    mask = Image.new("L", (S, S), 0)
    d = ImageDraw.Draw(mask)
    u = S / 10
    d.rounded_rectangle((3 * u, 4.6 * u, 7.2 * u, 8.6 * u), radius=u * 1.1, fill=255)    # palm
    finger_x = (3.05 * u, 4.1 * u, 5.15 * u, 6.2 * u)
    tops = {"palm": (1.2, 0.8, 1.0, 1.6), "point": (0.9, 3.9, 4.1, 4.3), "fist": (3.9, 3.8, 3.9, 4.1)}[kind]
    for x, top in zip(finger_x, tops):
        d.rounded_rectangle((x, top * u, x + 0.95 * u, 5.4 * u), radius=u * 0.47, fill=255)
    thumb = Image.new("L", (S, S), 0)
    td = ImageDraw.Draw(thumb)
    if kind == "fist":
        td.rounded_rectangle((3.2 * u, 5.0 * u, 6.0 * u, 5.95 * u), radius=u * 0.47, fill=255)
    else:
        td.rounded_rectangle((1.5 * u, 4.4 * u, 2.45 * u, 7.0 * u), radius=u * 0.47, fill=255)
        thumb = thumb.rotate(32 if kind == "palm" else 20, center=(2.4 * u, 7.2 * u), resample=BICUBIC)
    mask = Image.fromarray(np.maximum(np.array(mask), np.array(thumb)))
    outline = mask.filter(ImageFilter.MaxFilter(int(u * 0.35) | 1))
    img = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    img.paste(Image.new("RGBA", (S, S), _rgba(color)), (0, 0), outline)
    img.paste(Image.new("RGBA", (S, S), _rgba(config.COLORS["panel"])), (0, 0), mask)
    return img.resize((size, size), LANCZOS)


def render_glow(radius, color):
    """Soft round spot drawn under the cursor."""
    S = radius * 2
    yy, xx = np.mgrid[0:S, 0:S].astype(np.float32)
    d = np.sqrt((xx - radius) ** 2 + (yy - radius) ** 2) / radius
    alpha = np.clip(1 - d, 0, 1) ** 2.2 * 140
    rgb = np.empty((S, S, 3), np.uint8)
    rgb[...] = hex_to_rgb(color)
    return Image.fromarray(np.dstack([rgb, alpha.astype(np.uint8)]), "RGBA")


def rotation_frames(img, frames=config.SPRITE_ROTATION_FRAMES):
    """frame k = image rotated k * (360 / frames) degrees clockwise."""
    step = 360 / frames
    return [img.rotate(-k * step, resample=BICUBIC) for k in range(frames)]


# --------------------------------------------------------------------------
# Tk side
# --------------------------------------------------------------------------
class SpriteBank:
    """Creates every Tk PhotoImage once (call after the Tk root exists)."""

    FADE_LEVELS = (1.0, 0.75, 0.5, 0.3, 0.12)

    def __init__(self, width=config.WIDTH, height=config.HEIGHT):
        from PIL import ImageTk           # needs Tk, so imported lazily
        self._tk = ImageTk.PhotoImage
        self.width, self.height = width, height
        self.frames = config.SPRITE_ROTATION_FRAMES
        self.warnings = []
        self._cache = {}

        self.fruit = {}
        self.half = {}
        self.splat = {}
        for kind in FRUIT_TYPES:
            full = self._load_override(kind) or render_fruit(kind)
            half = half_from_image(full) if (config.IMAGES_DIR / f"{kind.name}.png").exists() else render_half(kind)
            self.fruit[kind.name] = [self._tk(f) for f in rotation_frames(full, self.frames)]
            self.half[kind.name] = [self._tk(f) for f in rotation_frames(half, self.frames)]
            splat = render_splat(kind.juice, kind.radius, kind.name)
            self.splat[kind.name] = [self._tk(self._fade(splat, a)) for a in self.FADE_LEVELS]
        self.bomb = [self._tk(f) for f in rotation_frames(render_bomb(), self.frames)]
        self.heart_full = self._tk(render_heart(30, config.COLORS["danger"]))
        self.heart_empty = self._tk(render_heart(30, "#000000", filled=False))
        self.cursor_glow = self._tk(render_glow(18, config.COLORS["accent2"]))
        self.icons = {k: self._tk(render_hand_icon(k)) for k in ("point", "palm", "fist")}
        self.fruit_icon = {k.name: self._tk(render_fruit(k).resize((64, 64), LANCZOS)) for k in FRUIT_TYPES}
        self.bomb_icon = self._tk(render_bomb().resize((70, 70), LANCZOS))

    def frame_index(self, angle):
        return int(round(angle / (360 / self.frames))) % self.frames

    def button(self, w, h, color, hover=False):
        key = ("button", w, h, color, hover)
        if key not in self._cache:
            self._cache[key] = self._tk(render_button(w, h, color, hover=hover))
        return self._cache[key]

    def photo(self, pil_image):
        return self._tk(pil_image)

    @staticmethod
    def _fade(img, factor):
        arr = np.array(img)
        arr[..., 3] = (arr[..., 3] * factor).astype(np.uint8)
        return Image.fromarray(arr)

    def _load_override(self, kind):
        path = config.IMAGES_DIR / f"{kind.name}.png"
        if not path.exists():
            return None
        try:
            size = sprite_size(kind.radius)
            img = Image.open(path).convert("RGBA")
            inner = int(kind.radius * 2)
            img.thumbnail((inner, inner), LANCZOS)
            canvas = Image.new("RGBA", (size, size), (0, 0, 0, 0))
            canvas.paste(img, ((size - img.width) // 2, (size - img.height) // 2), img)
            return canvas
        except Exception as exc:  # corrupt / unreadable image -> procedural art
            self.warnings.append(f"Could not load {path.name}: {exc}")
            return None
