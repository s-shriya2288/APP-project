"""
sprites.py - all graphics are generated in code with Pillow + NumPy, so the
game needs no image files (and never shows an empty placeholder).

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

SS = 3                      # super-sampling factor for smooth (anti-aliased) edges
LANCZOS = Image.Resampling.LANCZOS
BICUBIC = Image.Resampling.BICUBIC


# --------------------------------------------------------------------------
# Helpers
# --------------------------------------------------------------------------
def _rgba(color, alpha=255):
    return (*hex_to_rgb(color), alpha)


def _shaded_sphere(size, r, light, dark, striped=False):
    """RGBA array of a ball lit from the upper left (size x size, centred)."""
    c = size / 2
    yy, xx = np.mgrid[0:size, 0:size].astype(np.float32)
    dx, dy = xx - c, yy - c
    d = np.sqrt(dx * dx + dy * dy)
    lx, ly = -0.38 * r, -0.42 * r
    t = np.clip(np.sqrt((dx - lx) ** 2 + (dy - ly) ** 2) / (1.55 * r), 0, 1) ** 1.25
    light = np.array(hex_to_rgb(light), np.float32)
    dark = np.array(hex_to_rgb(dark), np.float32)
    rgb = light * (1 - t[..., None]) + dark * t[..., None]
    if striped:
        # Stripes that wrap around the sphere (arcsin warps them near the edge).
        half_w = np.sqrt(np.clip(r * r - dy * dy, 1, None))
        ang = np.arcsin(np.clip(dx / half_w, -1, 1))
        wobble = np.sin(dy / r * 5.0) * 0.12
        stripe = np.sin(ang * 7.0 + wobble) > 0.25
        rgb = np.where(stripe[..., None], rgb * 0.55, rgb)
    edge = np.clip((d - r * 0.80) / (r * 0.20), 0, 1)
    rgb *= (1 - 0.28 * edge)[..., None]
    alpha = (d <= r).astype(np.float32) * 255
    return np.dstack([np.clip(rgb, 0, 255), alpha]).astype(np.uint8)


def _soft_disc(size, r, color, alpha, blur):
    layer = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    c = size / 2
    ImageDraw.Draw(layer).ellipse((c - r, c - r, c + r, c + r), fill=_rgba(color, alpha))
    return layer.filter(ImageFilter.GaussianBlur(blur))


def _highlight(size, r):
    """Glossy white reflection in the upper-left of a sphere."""
    layer = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    c = size / 2
    draw = ImageDraw.Draw(layer)
    draw.ellipse((c - r * 0.62, c - r * 0.72, c - r * 0.05, c - r * 0.30), fill=(255, 255, 255, 120))
    draw.ellipse((c - r * 0.48, c - r * 0.62, c - r * 0.28, c - r * 0.48), fill=(255, 255, 255, 200))
    return layer.filter(ImageFilter.GaussianBlur(r * 0.07))


def _star_points(cx, cy, r_outer, r_inner, n=5, rotation=-90):
    pts = []
    for i in range(n * 2):
        rad = r_outer if i % 2 == 0 else r_inner
        a = math.radians(rotation + i * 180 / n)
        pts.append((cx + rad * math.cos(a), cy + rad * math.sin(a)))
    return pts


def _leaf(draw, c, r, color, angle_deg):
    """Leaf polygon attached near the top of the fruit."""
    base_x, base_y = c + r * 0.05, c - r * 0.92
    a = math.radians(angle_deg)
    length, width = r * 0.62, r * 0.26
    pts = []
    for i in range(21):
        t = i / 20
        w = math.sin(t * math.pi) * width
        pts.append((t * length, -w))
    for i in range(20, -1, -1):
        t = i / 20
        w = math.sin(t * math.pi) * width * 0.6
        pts.append((t * length, w))
    rot = [(base_x + x * math.cos(a) - y * math.sin(a), base_y + x * math.sin(a) + y * math.cos(a))
           for x, y in pts]
    draw.polygon(rot, fill=_rgba(color))
    mid_end = (base_x + length * 0.85 * math.cos(a), base_y + length * 0.85 * math.sin(a))
    draw.line([(base_x, base_y), mid_end], fill=(32, 120, 48, 255), width=max(1, int(r * 0.04)))


class _Layer:
    """Context manager for translucent details.

    ImageDraw *replaces* pixels on RGBA images instead of blending them, so a
    50 % white dot would punch a see-through hole into a fruit.  Shapes are
    drawn on a separate transparent layer that is alpha-composited on exit.
    """

    def __init__(self, img):
        self.img = img
        self.layer = Image.new("RGBA", img.size, (0, 0, 0, 0))

    def __enter__(self):
        return ImageDraw.Draw(self.layer)

    def __exit__(self, *exc):
        self.img.alpha_composite(self.layer)
        return False


def _rounded_mask(w, h, radius):
    mask = Image.new("L", (w, h), 0)
    ImageDraw.Draw(mask).rounded_rectangle((0, 0, w - 1, h - 1), radius=radius, fill=255)
    return mask


# --------------------------------------------------------------------------
# Fruits and bombs
# --------------------------------------------------------------------------
def sprite_size(radius, pad_ratio=0.6):
    return int(2 * radius * (1 + pad_ratio))


def render_fruit(kind):
    """A whole fruit with shading, highlight, stem and leaf."""
    size = sprite_size(kind.radius)
    S, R = size * SS, kind.radius * SS
    c = S / 2
    img = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    glow_alpha = 150 if kind.special else 60
    img.alpha_composite(_soft_disc(S, R * (1.18 if kind.special else 1.06), kind.skin, glow_alpha, R * 0.18))
    img.alpha_composite(Image.fromarray(_shaded_sphere(S, R, kind.skin, kind.skin_dark, kind.striped)))
    rng = random.Random(kind.name)
    with _Layer(img) as draw:
        if kind.name in ("orange", "lime"):           # pitted citrus skin
            for _ in range(int(R * 0.9)):
                a, d = rng.uniform(0, 2 * math.pi), R * math.sqrt(rng.random()) * 0.92
                x, y = c + d * math.cos(a), c + d * math.sin(a)
                s = R * 0.022
                draw.ellipse((x - s, y - s, x + s, y + s), fill=(0, 0, 0, 30))
        if kind.special:                              # golden star fruit
            draw.polygon(_star_points(c, c, R * 0.66, R * 0.29), fill=_rgba("#fff3a0", 235),
                         outline=_rgba("#c08a00"), width=int(R * 0.04))
    if kind.special:
        with _Layer(img) as draw:                     # sparkles on top of the star
            for _ in range(5):
                a, d = rng.uniform(0, 2 * math.pi), R * rng.uniform(0.3, 0.8)
                x, y, s = c + d * math.cos(a), c + d * math.sin(a), R * 0.09
                draw.polygon(_star_points(x, y, s, s * 0.3, 4, 0), fill=(255, 255, 255, 210))

    img.alpha_composite(_highlight(S, R))
    draw = ImageDraw.Draw(img)
    if kind.stem:
        draw.line([(c, c - R * 0.82), (c + R * 0.10, c - R * 1.22)], fill=_rgba("#5b3a1e"),
                  width=int(R * 0.10))
    if kind.leaf:
        _leaf(draw, c, R, "#3fbf4f", -35)
    return img.resize((size, size), LANCZOS)


def render_half(kind):
    """Top half of a sliced fruit; the flat cut edge lies on the centre line."""
    size = sprite_size(kind.radius)
    S, R = size * SS, kind.radius * SS
    c = S / 2
    sphere = Image.fromarray(_shaded_sphere(S, R, kind.skin, kind.skin_dark, kind.striped))
    mask = Image.new("L", (S, S), 0)
    ImageDraw.Draw(mask).rectangle((0, 0, S, c), fill=255)
    img = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    img.paste(sphere, (0, 0), Image.fromarray(np.minimum(np.array(mask), np.array(sphere)[..., 3])))

    draw = ImageDraw.Draw(img)
    box = lambda f: (c - R * f, c - R * f, c + R * f, c + R * f)  # noqa: E731
    draw.pieslice(box(0.93), 180, 360, fill=_rgba(kind.rim))
    draw.pieslice(box(0.84), 180, 360, fill=_rgba(kind.flesh))
    # brighter core near the cut
    core = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    ImageDraw.Draw(core).pieslice(box(0.5), 180, 360, fill=(255, 255, 255, 70))
    img.alpha_composite(core.filter(ImageFilter.GaussianBlur(R * 0.12)))

    rng = random.Random(kind.name + "half")
    with _Layer(img) as draw:
        if kind.seed:
            count = 9 if kind.striped else 3
            for i in range(count):
                a = math.radians(200 + (140 / max(count - 1, 1)) * i)
                d = R * (0.55 if kind.striped else 0.25)
                x, y = c + d * math.cos(a), c + d * math.sin(a) * 0.9
                s = R * (0.05 if kind.striped else 0.07)
                draw.ellipse((x - s * 0.7, y - s, x + s * 0.7, y + s), fill=_rgba(kind.seed))
        else:  # citrus segments / juice dots
            for i in range(7):
                a = math.radians(180 + i * 30)
                draw.line([(c, c), (c + R * 0.8 * math.cos(a), c + R * 0.8 * math.sin(a))],
                          fill=_rgba(kind.rim, 160), width=max(1, int(R * 0.03)))
    with _Layer(img) as draw:
        if not kind.seed:
            for _ in range(10):
                a, d = math.radians(rng.uniform(185, 355)), R * rng.uniform(0.2, 0.7)
                x, y, s = c + d * math.cos(a), c + d * math.sin(a), R * 0.03
                draw.ellipse((x - s, y - s, x + s, y + s), fill=(255, 255, 255, 120))
        draw.line([(c - R * 0.93, c), (c + R * 0.93, c)], fill=(255, 255, 255, 150), width=max(1, int(R * 0.03)))
    return img.resize((size, size), LANCZOS)


def half_from_image(full):
    """Make a 'half' sprite from a user-supplied full fruit image."""
    w, h = full.size
    half = full.copy()
    arr = np.array(half)
    arr[h // 2:, :, 3] = 0
    return Image.fromarray(arr)


def render_bomb(radius=BOMB_RADIUS):
    size = sprite_size(radius, 0.62)
    S, R = size * SS, radius * SS
    c = S / 2
    img = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    img.alpha_composite(_soft_disc(S, R * 1.12, config.COLORS["danger"], 120, R * 0.2))
    img.alpha_composite(Image.fromarray(_shaded_sphere(S, R, "#4a5164", "#08090d")))
    with _Layer(img) as draw:
        draw.ellipse((c - R * 0.97, c - R * 0.97, c + R * 0.97, c + R * 0.97),
                     outline=_rgba(config.COLORS["danger"], 200), width=int(R * 0.06))
        # warning symbol
        tri = [(c, c - R * 0.42), (c + R * 0.42, c + R * 0.32), (c - R * 0.42, c + R * 0.32)]
        draw.polygon(tri, fill=_rgba(config.COLORS["danger"], 230))
    with _Layer(img) as draw:
        draw.rounded_rectangle((c - R * 0.05, c - R * 0.2, c + R * 0.05, c + R * 0.1), R * 0.03,
                               fill=(255, 255, 255, 240))
        draw.ellipse((c - R * 0.055, c + R * 0.15, c + R * 0.055, c + R * 0.26), fill=(255, 255, 255, 240))
    img.alpha_composite(_highlight(S, R))
    draw = ImageDraw.Draw(img)
    # metal cap + curved fuse ending where Bomb.fuse_tip() expects it
    draw.rounded_rectangle((c - R * 0.22, c - R * 1.08, c + R * 0.22, c - R * 0.86), R * 0.05, fill=_rgba("#8a93a8"))
    tip = (c + R * 0.62, c - R * 1.28)
    pts = [(c + (tip[0] - c) * t + math.sin(t * math.pi) * R * -0.08,
            (c - R * 1.06) + (tip[1] - (c - R * 1.06)) * t - math.sin(t * math.pi) * R * 0.18)
           for t in [i / 12 for i in range(13)]]
    draw.line(pts, fill=_rgba("#d9b27a"), width=int(R * 0.09), joint="curve")
    return img.resize((size, size), LANCZOS)


def render_splat(color, radius, seed):
    """Juice splash left on the 'wall' behind the fruit."""
    size = int(radius * 3.2)
    S = size * 2
    c = S / 2
    rng = random.Random(seed)
    img = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    rr = radius * 2 * 0.62
    fill = _rgba(color, 190)
    draw.ellipse((c - rr, c - rr, c + rr, c + rr), fill=fill)
    for _ in range(14):
        a = rng.uniform(0, 2 * math.pi)
        d = rng.uniform(rr * 0.6, rr * 1.45)
        s = rng.uniform(rr * 0.08, rr * 0.3)
        x, y = c + d * math.cos(a), c + d * math.sin(a)
        draw.ellipse((x - s, y - s, x + s, y + s), fill=fill)
        draw.line([(c, c), (x, y)], fill=fill, width=int(s * 0.9))
    img = img.filter(ImageFilter.GaussianBlur(1.5))
    return img.resize((size, size), LANCZOS)


# --------------------------------------------------------------------------
# Backgrounds, panels, buttons, icons
# --------------------------------------------------------------------------
def draw_background(canvas, tag, w=config.WIDTH, h=config.HEIGHT, seed=7):
    """Arcade backdrop made of plain canvas shapes.

    A full-window photo is expensive for Tk to repaint (~30 ms per frame on
    a Retina Mac), while a few hundred solid shapes repaint in about 1 ms -
    this is what keeps the game at 60 FPS while fruit fly everywhere.
    """
    top = np.array(hex_to_rgb(config.COLORS["bg_top"]), np.float32)
    bottom = np.array(hex_to_rgb(config.COLORS["bg_bottom"]), np.float32)
    bands = 56
    band_h = h / bands
    for i in range(bands):
        t = (i / (bands - 1)) ** 0.9
        canvas.create_rectangle(0, i * band_h, w, (i + 1) * band_h + 1, fill=_hex(top * (1 - t) + bottom * t),
                                width=0, tags=(tag,))
    rng = random.Random(seed)
    horizon = h * 0.66
    for _ in range(110):                                    # stars
        x, y = rng.uniform(0, w), rng.uniform(0, horizon - 20)
        s = rng.choice((0.8, 1.0, 1.0, 1.5))
        shade = rng.randint(120, 230)
        canvas.create_oval(x - s, y - s, x + s, y + s, width=0, tags=(tag,),
                           fill=_hex((shade, shade - 10, shade + 30)))
    for i in range(1, 14):                                  # perspective floor grid
        y = horizon + (h - horizon) * (i / 13) ** 2.2
        canvas.create_line(0, y, w, y, fill=_hex((10, 40 + 5 * i, 60 + 6 * i)), tags=(tag,))
    for i in range(-14, 15):
        canvas.create_line(w / 2 + i * 6, horizon, w / 2 + i * w / 9, h, fill="#2c1640", tags=(tag,))
    for k, color in enumerate(("#ff4fa3", "#9c3a8a", "#4e1f5a")):   # glowing horizon line
        canvas.create_line(0, horizon + k, w, horizon + k, fill=color, tags=(tag,))


def rounded_rect_points(x0, y0, x1, y1, r, steps=6):
    r = min(r, (x1 - x0) / 2, (y1 - y0) / 2)
    pts = []
    for cx, cy, start in ((x1 - r, y0 + r, -90), (x1 - r, y1 - r, 0), (x0 + r, y1 - r, 90), (x0 + r, y0 + r, 180)):
        for k in range(steps + 1):
            a = math.radians(start + 90 * k / steps)
            pts += [cx + r * math.cos(a), cy + r * math.sin(a)]
    return pts


def draw_panel(canvas, tags, cx, cy, w, h, radius=24, fill="#17123d", outline="#4a3b99", glow=None):
    """Rounded panel made of canvas polygons (cheap to repaint, unlike a big image)."""
    x0, y0, x1, y1 = cx - w / 2, cy - h / 2, cx + w / 2, cy + h / 2
    if glow:
        for grow, mix in ((12, 0.85), (8, 0.7), (4, 0.45)):
            canvas.create_polygon(rounded_rect_points(x0 - grow, y0 - grow, x1 + grow, y1 + grow, radius + grow),
                                  fill="", outline=_hex(np.array(hex_to_rgb(glow)) * (1 - mix) +
                                                        np.array(hex_to_rgb(config.COLORS["bg_top"])) * mix),
                                  width=4, tags=tags)
    body = canvas.create_polygon(rounded_rect_points(x0, y0, x1, y1, radius), fill=fill, outline=outline,
                                 width=2, tags=tags)
    canvas.create_line(x0 + radius, y0 + 3, x1 - radius, y0 + 3, fill=_hex(np.array(hex_to_rgb(fill)) * 1.6 + 18),
                       tags=tags)
    return body


def _hex(rgb):
    return "#%02x%02x%02x" % tuple(int(max(0, min(255, v))) for v in rgb)


def render_button(w, h, color_a, color_b, hover=False):
    """Pill-shaped gradient button with glossy top and (on hover) a glow."""
    g = 16
    S = 2
    W, H = (w + 2 * g) * S, (h + 2 * g) * S
    img = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    radius = h * S // 2
    if hover:
        glow = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        ImageDraw.Draw(glow).rounded_rectangle((g * S, g * S, W - g * S, H - g * S), radius,
                                               fill=_rgba(color_a, 170))
        img.alpha_composite(glow.filter(ImageFilter.GaussianBlur(g * S * 0.5)))
    a = np.array(hex_to_rgb(color_a), np.float32)
    b = np.array(hex_to_rgb(color_b), np.float32)
    t = np.linspace(0, 1, w * S, dtype=np.float32)[None, :, None]
    rgb = np.repeat(a * (1 - t) + b * t, h * S, axis=0)
    if hover:
        rgb = rgb * 0.8 + 255 * 0.2
    shine = np.linspace(0.28, 0, h * S // 2, dtype=np.float32)
    rgb[: h * S // 2] = rgb[: h * S // 2] * (1 - shine[:, None, None]) + 255 * shine[:, None, None]
    body = Image.fromarray(np.clip(rgb, 0, 255).astype(np.uint8), "RGB").convert("RGBA")
    img.paste(body, (g * S, g * S), _rounded_mask(w * S, h * S, radius))
    ImageDraw.Draw(img).rounded_rectangle((g * S, g * S, W - g * S - 1, H - g * S - 1), radius,
                                          outline=(255, 255, 255, 150 if hover else 70), width=2 * S)
    return img.resize((w + 2 * g, h + 2 * g), LANCZOS)


def render_heart(size, color, filled=True):
    S = size * SS
    img = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    pts = []
    for i in range(120):
        t = i / 120 * 2 * math.pi
        x = 16 * math.sin(t) ** 3
        y = -(13 * math.cos(t) - 5 * math.cos(2 * t) - 2 * math.cos(3 * t) - math.cos(4 * t))
        pts.append((S / 2 + x * S / 36, S / 2 + y * S / 36 - S * 0.02))
    draw = ImageDraw.Draw(img)
    if filled:
        glow = Image.new("RGBA", (S, S), (0, 0, 0, 0))
        ImageDraw.Draw(glow).polygon(pts, fill=_rgba(color, 150))
        img.alpha_composite(glow.filter(ImageFilter.GaussianBlur(S * 0.06)))
        ImageDraw.Draw(img).polygon(pts, fill=_rgba(color))
        with _Layer(img) as shine:
            shine.ellipse((S * 0.28, S * 0.27, S * 0.42, S * 0.38), fill=(255, 255, 255, 150))
    else:
        draw.polygon(pts, outline=(120, 110, 170, 255), width=int(S * 0.06))
    return img.resize((size, size), LANCZOS)


def render_hand_icon(kind, size=96, color=config.COLORS["accent2"]):
    """Neon outline icon of a hand pose: 'point', 'palm' or 'fist'."""
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
    outline = Image.fromarray(np.clip(
        np.array(mask.filter(ImageFilter.MaxFilter(int(u * 0.35) | 1)), np.int16) - np.array(mask, np.int16) +
        (np.array(mask.filter(ImageFilter.FIND_EDGES)) > 0) * 255, 0, 255).astype(np.uint8))
    img = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    img.paste(Image.new("RGBA", (S, S), (40, 30, 90, 200)), (0, 0), mask)
    glow = Image.new("RGBA", (S, S), _rgba(color, 0))
    glow.putalpha(outline.filter(ImageFilter.GaussianBlur(u * 0.25)))
    img.alpha_composite(glow)
    img.paste(Image.new("RGBA", (S, S), _rgba(color)), (0, 0), outline)
    return img.resize((size, size), LANCZOS)


def render_glow(radius, color):
    S = radius * 2
    yy, xx = np.mgrid[0:S, 0:S].astype(np.float32)
    d = np.sqrt((xx - radius) ** 2 + (yy - radius) ** 2) / radius
    alpha = np.clip(1 - d, 0, 1) ** 2.2 * 255
    rgb = np.empty((S, S, 3), np.uint8)
    rgb[...] = hex_to_rgb(color)
    return Image.fromarray(np.dstack([rgb, alpha.astype(np.uint8)]), "RGBA")


TITLE_FONTS = (
    ("/System/Library/Fonts/Avenir Next.ttc", 8),                 # macOS: Avenir Next Heavy
    ("/System/Library/Fonts/Supplemental/Arial Black.ttf", 0),
    ("C:/Windows/Fonts/seguibl.ttf", 0),                            # Windows: Segoe UI Black
    ("C:/Windows/Fonts/arialbd.ttf", 0),
    ("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 0),    # Linux
)


def find_title_font(size):
    from PIL import ImageFont
    for path, index in TITLE_FONTS:
        try:
            return ImageFont.truetype(path, size, index=index)
        except (OSError, ValueError):
            continue
    return None


def render_title(text, size, top_color, bottom_color, glow_color):
    """Neon title: gradient letters, blurred glow and drop shadow.

    Returns None when no TrueType font is found (the UI then falls back to
    layered Tk text)."""
    font = find_title_font(size * SS // 2)
    if font is None:
        return None
    pad = size
    x0, y0, x1, y1 = font.getbbox(text)
    w, h = x1 - x0 + 2 * pad, y1 - y0 + 2 * pad
    mask = Image.new("L", (w, h), 0)
    ImageDraw.Draw(mask).text((pad - x0, pad - y0), text, font=font, fill=255)
    img = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    glow = Image.new("RGBA", (w, h), _rgba(glow_color, 0))
    glow.putalpha(mask.filter(ImageFilter.MaxFilter(5)).filter(ImageFilter.GaussianBlur(size * 0.22)))
    img.alpha_composite(glow)
    img.alpha_composite(glow)
    shadow = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    shadow.paste(Image.new("RGBA", (w, h), (0, 0, 0, 170)), (int(size * 0.05), int(size * 0.08)), mask)
    img.alpha_composite(shadow)
    a = np.array(hex_to_rgb(top_color), np.float32)
    b = np.array(hex_to_rgb(bottom_color), np.float32)
    t = np.linspace(0, 1, h, dtype=np.float32)[:, None, None]
    grad = np.repeat(a * (1 - t) + b * t, w, axis=1)
    fill = Image.fromarray(grad.astype(np.uint8), "RGB").convert("RGBA")
    img.paste(fill, (0, 0), mask)
    img = img.crop(img.getchannel("A").point(lambda v: 255 if v > 8 else 0).getbbox())
    return img.resize((img.width * 2 // SS, img.height * 2 // SS), LANCZOS)


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
        self.cursor_glow = self._tk(render_glow(34, config.COLORS["accent2"]))
        self.icons = {k: self._tk(render_hand_icon(k)) for k in ("point", "palm", "fist")}
        self.fruit_icon = {k.name: self._tk(render_fruit(k).resize((64, 64), LANCZOS)) for k in FRUIT_TYPES}
        self.bomb_icon = self._tk(render_bomb().resize((70, 70), LANCZOS))

    def frame_index(self, angle):
        return int(round(angle / (360 / self.frames))) % self.frames

    def button(self, w, h, color_a, color_b, hover=False):
        key = ("button", w, h, color_a, color_b, hover)
        if key not in self._cache:
            self._cache[key] = self._tk(render_button(w, h, color_a, color_b, hover))
        return self._cache[key]

    def title(self, text, size, top_color, bottom_color, glow_color):
        key = ("title", text, size, top_color, bottom_color, glow_color)
        if key not in self._cache:
            img = render_title(text, size, top_color, bottom_color, glow_color)
            self._cache[key] = self._tk(img) if img is not None else None
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
