"""
utils.py - small maths and colour helpers shared by several modules.
"""

import math


def clamp(value, low, high):
    """Limit value to the range [low, high]."""
    return low if value < low else high if value > high else value


def lerp(a, b, t):
    """Linear interpolation between a and b (t = 0 -> a, t = 1 -> b)."""
    return a + (b - a) * t


def ease_out_cubic(t):
    t = clamp(t, 0.0, 1.0)
    return 1 - (1 - t) ** 3


def ease_out_back(t):
    """Overshoots a little before settling - nice for pop-in animations."""
    t = clamp(t, 0.0, 1.0)
    c1, c3 = 1.70158, 2.70158
    return 1 + c3 * (t - 1) ** 3 + c1 * (t - 1) ** 2


def hex_to_rgb(color):
    color = color.lstrip("#")
    return tuple(int(color[i:i + 2], 16) for i in (0, 2, 4))


def rgb_to_hex(rgb):
    r, g, b = (int(clamp(round(c), 0, 255)) for c in rgb)
    return f"#{r:02x}{g:02x}{b:02x}"


def lerp_color(c1, c2, t):
    """Blend two '#rrggbb' colours."""
    a, b = hex_to_rgb(c1), hex_to_rgb(c2)
    return rgb_to_hex(tuple(lerp(x, y, t) for x, y in zip(a, b)))


def lighten(color, amount):
    return lerp_color(color, "#ffffff", amount)


def darken(color, amount):
    return lerp_color(color, "#000000", amount)


def distance(ax, ay, bx, by):
    return math.hypot(bx - ax, by - ay)
