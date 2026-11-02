"""
canvas_snapshot.py - save a PNG of a Tkinter Canvas without screen capture.

Re-draws every visible canvas item (rectangles, ovals, polygons, lines, arcs,
text and images) with Pillow.  Used by tests/manual_ui_smoke.py to produce
the screenshots in docs/screenshots/ on machines where screen recording is
not allowed.  Call ``install_image_registry()`` before the SpriteBank is
created so the PIL source of every PhotoImage is remembered.
"""

import tkinter.font as tkfont

from PIL import Image, ImageDraw, ImageFont, ImageTk

_registry = {}


def install_image_registry():
    original = ImageTk.PhotoImage.__init__

    def init(self, image=None, size=None, **kw):
        original(self, image, size, **kw)
        if isinstance(image, Image.Image):
            _registry[str(self)] = image.convert("RGBA")
    ImageTk.PhotoImage.__init__ = init
    original_paste = ImageTk.PhotoImage.paste

    def paste(self, im, *a, **k):
        original_paste(self, im, *a, **k)
        _registry[str(self)] = im.convert("RGBA")
    ImageTk.PhotoImage.paste = paste


_FONT_FILES = {"bold": ("/System/Library/Fonts/Avenir Next.ttc", 0),
               "normal": ("/System/Library/Fonts/Avenir Next.ttc", 7)}


def _font(canvas, spec, cache={}):
    actual = tkfont.Font(root=canvas, font=spec).actual()
    size = abs(int(actual["size"])) or 12
    key = (actual["weight"], size)
    if key not in cache:
        path, index = _FONT_FILES.get(actual["weight"], _FONT_FILES["normal"])
        try:
            cache[key] = ImageFont.truetype(path, size, index=index)
        except OSError:
            cache[key] = ImageFont.load_default()
    return cache[key]


def _anchor_offset(anchor, w, h):
    dx = {"w": 0, "nw": 0, "sw": 0, "e": -w, "ne": -w, "se": -w}.get(anchor, -w / 2)
    dy = {"n": 0, "nw": 0, "ne": 0, "s": -h, "sw": -h, "se": -h}.get(anchor, -h / 2)
    return dx, dy


def snapshot(canvas, path):
    w, h = int(canvas["width"]), int(canvas["height"])
    img = Image.new("RGBA", (w, h), canvas["background"])
    draw = ImageDraw.Draw(img)
    for item in canvas.find_all():
        if canvas.itemcget(item, "state") == "hidden":
            continue
        kind = canvas.type(item)
        xy = canvas.coords(item)
        opt = lambda name: canvas.itemcget(item, name)  # noqa: E731
        try:
            if kind in ("rectangle", "oval"):
                x0, y0, x1, y1 = xy
                box = (min(x0, x1), min(y0, y1), max(x0, x1), max(y0, y1))
                width = int(float(opt("width") or 0))
                fn = draw.rectangle if kind == "rectangle" else draw.ellipse
                fn(box, fill=opt("fill") or None, outline=(opt("outline") or None) if width else None, width=width)
            elif kind == "polygon" and len(xy) >= 6:
                pts = list(zip(xy[::2], xy[1::2]))
                if opt("fill"):
                    draw.polygon(pts, fill=opt("fill"))
                if opt("outline"):
                    draw.line(pts + pts[:1], fill=opt("outline"), width=max(1, int(float(opt("width")))))
            elif kind == "line" and len(xy) >= 4:
                draw.line(list(zip(xy[::2], xy[1::2])), fill=opt("fill"), width=max(1, int(float(opt("width")))),
                          joint="curve")
            elif kind == "arc":
                x0, y0, x1, y1 = xy
                start, extent = float(opt("start")), float(opt("extent"))
                a, b = sorted((-start, -(start + extent)))
                draw.arc((x0, y0, x1, y1), a, b, fill=opt("outline"), width=int(float(opt("width"))))
            elif kind == "text" and opt("text"):
                font = _font(canvas, opt("font"))
                text = opt("text")
                wrap = float(opt("width") or 0)
                if wrap:                         # word-wrap like Tk's text width option
                    lines = []
                    for para in text.split("\n"):
                        line = ""
                        for word in para.split(" "):
                            trial = (line + " " + word).strip()
                            if line and font.getlength(trial) > wrap:
                                lines.append(line)
                                line = word
                            else:
                                line = trial
                        lines.append(line)
                    text = "\n".join(lines)
                l, t, r, b = draw.multiline_textbbox((0, 0), text, font=font)
                dx, dy = _anchor_offset(opt("anchor"), r - l, b - t)
                draw.multiline_text((xy[0] + dx - l, xy[1] + dy - t), text, font=font, fill=opt("fill"))
            elif kind == "image":
                src = _registry.get(opt("image"))
                if src is not None:
                    dx, dy = _anchor_offset(opt("anchor"), src.width, src.height)
                    img.alpha_composite(src, (int(xy[0] + dx), int(xy[1] + dy)))
                    draw = ImageDraw.Draw(img)
            elif kind == "window":
                widget = canvas.nametowidget(opt("window"))
                ww, wh = float(opt("width")), float(opt("height"))
                x0, y0 = xy[0] - ww / 2, xy[1] - wh / 2
                draw.rectangle((x0, y0, x0 + ww, y0 + wh), fill=widget["bg"], outline=widget["highlightcolor"], width=2)
                font = _font(canvas, widget["font"])
                draw.text((xy[0], xy[1]), widget.get(), font=font, fill=widget["fg"], anchor="mm")
        except Exception:           # a snapshot must never break the game
            continue
    img.convert("RGB").save(path)
