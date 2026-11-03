"""
ui.py - the Tkinter application: window, main loop, widgets and screens.

Everything is drawn on ONE Tkinter Canvas.  Each screen draws its own items
(tagged with the screen's tag) and deletes them when it is closed.

Main loop (App._tick, scheduled with root.after every ~16 ms):

    1. read the mouse / trackpad movements -> MouseDetector
    2. turn them into one PointerState (position, cut segments, trail points)
    3. current_screen.update(dt, pointer)
    4. update the overlay (FPS counter, messages)
"""

import time
import tkinter as tk
import tkinter.font as tkfont
import traceback
from dataclasses import dataclass, field

from . import config
from .database import DatabaseManager
from .game_engine import Game, GameRenderer
from .mouse_input import MouseDetector
from .particle_effects import CanvasState
from .sound import SoundManager
from .sprites import SpriteBank, draw_background, draw_panel
from .utils import clamp, ease_out_cubic

COL = config.COLORS
W, H = config.WIDTH, config.HEIGHT

BUTTON_STYLES = {
    "primary": "#27ae60",
    "secondary": "#2980b9",
    "neutral": "#7f8c8d",
    "danger": "#c0392b",
    "success": "#16a085",
}


# --------------------------------------------------------------------------
# Small helpers
# --------------------------------------------------------------------------
class FontBook:
    """Picks the nicest installed font family once and builds font tuples."""

    def __init__(self, root):
        installed = set(tkfont.families(root))
        self.family = next((f for f in config.FONT_CANDIDATES if f in installed), "TkDefaultFont")

    def get(self, size, weight="normal"):
        return (self.family, size, weight)


@dataclass
class PointerState:
    """Everything the screens need to know about the player's input this frame."""
    present: bool = False
    x: float = 0.0
    y: float = 0.0
    segments: list = field(default_factory=list)  # (ax, ay, bx, by, speed) since last frame
    points: list = field(default_factory=list)    # (x, y, t, speed) for the trail


class CanvasButton:
    """Simple button drawn on the canvas (lights up on hover, runs command on click)."""

    def __init__(self, app, tag, x, y, w, h, text, command, style="primary", font_size=17, sound=True):
        self.app, self.c = app, app.canvas
        self.x, self.y, self.w, self.h = x, y, w, h
        self.command = command
        self.play_sound = sound
        color = BUTTON_STYLES[style]
        self.img_normal = app.sprites.button(w, h, color, hover=False)
        self.img_hover = app.sprites.button(w, h, color, hover=True)
        self.item = self.c.create_image(x, y, image=self.img_normal, tags=(tag,))
        self.label = self.c.create_text(x, y, text=text, fill="#ffffff",
                                        font=app.fonts.get(font_size, "bold"), tags=(tag,))
        self.hover = False
        self.enabled = True

    def contains(self, px, py):
        return abs(px - self.x) <= self.w / 2 and abs(py - self.y) <= self.h / 2

    def set_text(self, text):
        self.c.itemconfigure(self.label, text=text)

    def update(self, dt, pointer):
        """Show the hover image while the pointer is over the button."""
        inside = self.enabled and pointer.present and self.contains(pointer.x, pointer.y)
        if inside != self.hover:
            self.hover = inside
            self.c.itemconfigure(self.item, image=self.img_hover if inside else self.img_normal)

    def click(self):
        if not self.enabled:
            return
        if self.play_sound:
            self.app.sound.play("click")
        self.command()


# --------------------------------------------------------------------------
# Screens
# --------------------------------------------------------------------------
class Screen:
    own_cursor = False          # GameScreen draws its own blade cursor

    _counter = 0

    def __init__(self, app):
        Screen._counter += 1
        self.app = app
        self.c = app.canvas
        self.tag = f"screen{Screen._counter}"
        self.buttons = []
        self.time = 0.0

    # helpers -------------------------------------------------------------
    def button(self, x, y, w, h, text, command, style="primary", **kw):
        b = CanvasButton(self.app, self.tag, x, y, w, h, text, command, style, **kw)
        self.buttons.append(b)
        return b

    def text(self, x, y, text, size=14, color=COL["text"], weight="normal", **kw):
        return self.c.create_text(x, y, text=text, fill=color, font=self.app.fonts.get(size, weight),
                                  tags=(self.tag,), **kw)

    def heading(self, x, y, text, size, color=COL["text"]):
        """Big bold title text."""
        return self.text(x, y, text, size, color, "bold")

    def background(self):
        draw_background(self.c, self.tag)

    # lifecycle ------------------------------------------------------------
    def build(self):
        pass

    def update(self, dt, pointer):
        self.time += dt
        for b in self.buttons:
            b.update(dt, pointer)

    def on_click(self, x, y):
        for b in list(self.buttons):
            if b.enabled and b.contains(x, y):
                b.click()
                return True
        return False

    def on_key(self, key):
        if key == "Escape":
            self.app.show_menu()

    def destroy(self):
        self.c.delete(self.tag)
        self.buttons = []


class MainMenuScreen(Screen):
    def build(self):
        a = self.app
        self.background()
        self.heading(W / 2, 120, config.GAME_TITLE, 54, COL["accent"])
        self.text(W / 2, 180, config.GAME_SUBTITLE, 14, COL["muted"])

        y0, gap = 262, 66
        self.button(W / 2, y0, 300, 56, "PLAY", a.start_game, "primary", font_size=20)
        self.button(W / 2, y0 + gap, 300, 52, "HOW TO PLAY", a.show_how_to_play, "secondary")
        self.button(W / 2, y0 + gap * 2, 300, 52, "LEADERBOARD", a.show_leaderboard, "secondary")
        self.button(W / 2, y0 + gap * 3, 300, 52, "SETTINGS", a.show_settings, "neutral")
        self.button(W / 2, y0 + gap * 4, 300, 52, "EXIT", a.quit, "danger")

        best = a.db.get_player_best(a.settings["player_name"])
        cy = 636
        draw_panel(self.c, (self.tag,), W / 2, cy, 340, 44, radius=22)
        self.text(W / 2 - 150, cy, "PLAYER", 10, COL["muted"], "bold", anchor="w")
        self.text(W / 2 - 92, cy, a.settings["player_name"], 14, COL["text"], "bold", anchor="w")
        self.text(W / 2 + 150, cy, f"BEST {best:,}", 13, COL["gold"], "bold", anchor="e")
        self.text(W / 2, H - 22, "Use the trackpad or mouse  |  Enter = Play  |  Esc = Exit", 11, COL["muted"])

    def on_key(self, key):
        if key in ("Return", "space"):
            self.app.start_game()
        elif key == "Escape":
            self.app.quit()


class HowToPlayScreen(Screen):
    CARDS = (
        ("fruit:lime", "AIM", "Move your finger on the trackpad\n(or the mouse). The pointer is the knife."),
        ("fruit:apple", "SLICE", "Swipe FAST through the fruit.\nSlow movements only aim."),
        ("bomb", "AVOID BOMBS", "Cutting a bomb costs a life.\nYou have 3 lives per round."),
        ("fruit:golden star", "COMBOS & SPECIALS", "Cut 2+ fruits in one swipe for a\nbonus. Golden stars = 20 points."),
        ("fruit:watermelon", "LEVELS", "Score more to reach the next level.\nFruit fly faster every level."),
        ("fruit:plum", "PAUSE", "Press Space or P, or click the\nII button at the top right."),
    )

    def build(self):
        a, sp = self.app, self.app.sprites
        self.background()
        self.heading(W / 2, 60, "HOW TO PLAY", 34)
        cw, ch = 320, 170
        for i, (icon, title, body) in enumerate(self.CARDS):
            col, row = i % 3, i // 3
            x = W / 2 + (col - 1) * (cw + 24)
            y = 215 + row * (ch + 22)
            draw_panel(self.c, (self.tag,), x, y, cw, ch, radius=20)
            img = sp.bomb_icon if icon == "bomb" else sp.fruit_icon[icon.split(":")[1]]
            self.c.create_image(x - cw / 2 + 62, y, image=img, tags=(self.tag,))
            self.text(x - cw / 2 + 118, y - 38, title, 15, COL["gold"], "bold", anchor="w")
            self.text(x - cw / 2 + 118, y + 12, body, 11, COL["text"], anchor="w", width=190)
        self.text(W / 2, 560, "Tip: quick, straight swipes work best.   Space / P = pause   Esc = menu",
                  12, COL["muted"])
        self.button(W / 2 - 130, 625, 220, 52, "BACK", a.show_menu, "neutral")
        self.button(W / 2 + 130, 625, 220, 52, "PLAY", a.start_game, "primary")


class LeaderboardScreen(Screen):
    def build(self):
        a = self.app
        self.background()
        self.heading(W / 2, 60, "LEADERBOARD", 34)
        pw, ph = 860, 440
        draw_panel(self.c, (self.tag,), W / 2, 335, pw, ph, radius=24)
        left = W / 2 - pw / 2 + 40
        cols = (("RANK", 0, "w"), ("PLAYER", 90, "w"), ("BEST SCORE", 400, "e"), ("GAMES", 510, "e"),
                ("FRUITS", 620, "e"), ("BEST COMBO", 760, "e"))
        top = 140
        for name, dx, anchor in cols:
            self.text(left + dx, top, name, 10, COL["muted"], "bold", anchor=anchor)
        self.c.create_line(left, top + 16, left + pw - 80, top + 16, fill=COL["panel_edge"], tags=(self.tag,))

        rows = a.db.get_leaderboard(10)
        me = a.settings["player_name"].lower()
        if not rows:
            self.text(W / 2, 330, "No games played yet - be the first on the board!", 16, COL["muted"])
        medal = {1: COL["gold"], 2: "#d7dcef", 3: "#e3955b"}
        for i, r in enumerate(rows):
            y = top + 48 + i * 34
            if r["name"].lower() == me:
                self.c.create_rectangle(left - 16, y - 15, left + pw - 64, y + 15, fill="#34495e",
                                        outline=COL["accent2"], tags=(self.tag,))
            color = medal.get(r["rank"], COL["text"])
            if r["rank"] in medal:
                self.c.create_oval(left - 2, y - 12, left + 22, y + 12, fill=color, outline="", tags=(self.tag,))
                self.text(left + 10, y, str(r["rank"]), 11, "#1a0f3d", "bold")
            else:
                self.text(left + 10, y, str(r["rank"]), 12, COL["muted"], "bold")
            self.text(left + 90, y, r["name"], 14, color, "bold", anchor="w")
            self.text(left + 400, y, f"{r['best_score']:,}", 15, COL["gold"], "bold", anchor="e")
            self.text(left + 510, y, str(r["games_played"]), 13, COL["text"], anchor="e")
            self.text(left + 620, y, str(r["total_fruits_sliced"]), 13, COL["text"], anchor="e")
            self.text(left + 760, y, f"x{r['best_combo']}", 13, COL["accent"], "bold", anchor="e")

        stats = a.db.get_player_stats(a.settings["player_name"])
        if stats:
            games = stats["games_played"]
            line = (f"{a.settings['player_name']}:  {games} game{'s' if games != 1 else ''}  |  "
                    f"{stats['total_fruits_sliced']} fruits sliced  |  best accuracy {stats['best_accuracy']:.0f}%  |  "
                    f"{stats['total_play_time_s'] / 60:.1f} min played")
            self.text(W / 2, 580, line, 12, COL["muted"])
        self.button(W / 2 - 130, 635, 220, 50, "BACK", a.show_menu, "neutral")
        self.button(W / 2 + 130, 635, 220, 50, "PLAY", a.start_game, "primary")


class SettingsScreen(Screen):
    OPTIONS = (
        ("sound", "Sound effects", ("On", "Off")),
        ("round_seconds", "Round length (s)", tuple(str(s) for s in config.ROUND_SECONDS_OPTIONS)),
        ("sensitivity", "Slice sensitivity", tuple(config.SLICE_SENSITIVITY)),
    )

    def build(self):
        a = self.app
        self.background()
        self.heading(W / 2, 60, "SETTINGS", 34)
        pw, ph = 640, 270
        draw_panel(self.c, (self.tag,), W / 2, 275, pw, ph)
        left, right = W / 2 - pw / 2 + 50, W / 2 + pw / 2 - 50
        y = 180
        self.text(left, y, "Player name", 15, COL["text"], "bold", anchor="w")
        self.name_var = tk.StringVar(value=a.settings["player_name"])
        self.entry = tk.Entry(a.root, textvariable=self.name_var, width=16, font=a.fonts.get(15, "bold"),
                              bg="#34495e", fg=COL["text"], insertbackground=COL["accent2"], relief="flat",
                              highlightthickness=2, highlightbackground=COL["panel_edge"],
                              highlightcolor=COL["accent2"], justify="center")
        self.entry.bind("<Return>", lambda e: (self._save_name(), a.root.focus_set()))
        self.entry.bind("<FocusOut>", lambda e: self._save_name())
        self.c.create_window(right - 110, y, window=self.entry, width=220, height=38, tags=(self.tag,))

        self.value_items = {}
        for i, (key, label, values) in enumerate(self.OPTIONS):
            y = 250 + i * 60
            self.text(left, y, label, 15, COL["text"], "bold", anchor="w")
            self.button(right - 200, y, 44, 40, "<", lambda k=key: self._cycle(k, -1), "neutral", font_size=16)
            self.button(right - 20, y, 44, 40, ">", lambda k=key: self._cycle(k, +1), "neutral", font_size=16)
            self.value_items[key] = self.text(right - 110, y, a.settings[key], 15, COL["accent2"], "bold")
        self.button(W / 2, 470, 240, 52, "SAVE & BACK", self._back, "primary")

    def _cycle(self, key, step):
        values = dict((k, v) for k, _, v in self.OPTIONS)[key]
        current = self.app.settings[key]
        idx = values.index(current) if current in values else 0
        self.app.change_setting(key, values[(idx + step) % len(values)])
        self.c.itemconfigure(self.value_items[key], text=self.app.settings[key])

    def _save_name(self):
        name = DatabaseManager.clean_name(self.name_var.get())
        if name != self.app.settings["player_name"]:
            self.app.change_setting("player_name", name)
        self.name_var.set(name)

    def _back(self):
        self._save_name()
        self.app.show_menu()

    def on_key(self, key):
        if key == "Escape":
            self._back()

    def destroy(self):
        self.entry.destroy()
        self.app.root.focus_set()
        super().destroy()


class GameScreen(Screen):
    own_cursor = True

    def build(self):
        a = self.app
        s = a.settings
        self.slice_speed = config.SLICE_SENSITIVITY.get(s["sensitivity"], 650.0)
        self.game = Game(W, H, int(s["round_seconds"]), self.slice_speed)
        self.renderer = GameRenderer(self.c, a.sprites, a.fonts, a.sound)
        self.pause_button = self.button(W - 72, 44, 44, 40, "II", self.toggle_pause, "neutral", font_size=14)
        self.overlay_tag = self.tag + "_pause"
        self.overlay_buttons = []
        self.finished = False
        self.last_swoosh = 0.0

    # pause handling ----------------------------------------------------------
    def toggle_pause(self):
        if self.game.state == Game.PAUSED:
            self.resume()
        else:
            self.pause()

    def pause(self):
        if self.game.pause():
            self.renderer.reset_trail()
            self._show_pause_overlay()

    def resume(self):
        if self.game.resume():
            self._hide_pause_overlay()

    def _show_pause_overlay(self):
        T = (self.tag, self.overlay_tag)
        draw_panel(self.c, T, W / 2, H / 2, 460, 380)
        font = self.app.fonts.get(44, "bold")
        self.c.create_text(W / 2, H / 2 - 130, text="PAUSED", fill=COL["text"], font=font, tags=T)
        self.c.create_text(W / 2, H / 2 - 60, text="Press Space or click RESUME", tags=T,
                           fill=COL["muted"], font=self.app.fonts.get(14))
        for i, (label, cmd, style) in enumerate((("RESUME", self.resume, "success"),
                                                 ("RESTART", self.app.start_game, "primary"),
                                                 ("MAIN MENU", self.app.show_menu, "neutral"))):
            b = CanvasButton(self.app, self.overlay_tag, W / 2, H / 2 + 30 + i * 58, 260, 48, label, cmd, style)
            self.c.addtag_withtag(self.tag, b.item)
            self.c.addtag_withtag(self.tag, b.label)
            self.overlay_buttons.append(b)
        self.renderer.raise_cursor()
        self.app.raise_overlay()

    def _hide_pause_overlay(self):
        self.c.delete(self.overlay_tag)
        self.overlay_buttons = []

    # per frame ----------------------------------------------------------------
    def update(self, dt, pointer):
        self.time += dt
        now = time.perf_counter()
        playing = self.game.state == Game.PLAYING
        events = self.game.update(dt, pointer.segments if playing else ())
        if self.game.state != Game.PAUSED:
            for x, y, t, speed in pointer.points:
                self.renderer.add_trail_point(x, y, t, speed >= self.slice_speed and playing)
            if playing and any(seg[4] >= self.slice_speed for seg in pointer.segments) \
                    and now - self.last_swoosh > 0.28:
                self.last_swoosh = now
                self.app.sound.play("swoosh")
        self.renderer.handle_events(events, self.game)
        self.renderer.render(self.game, dt, pointer, now)

        buttons = self.overlay_buttons if self.game.state == Game.PAUSED else [self.pause_button]
        for b in buttons:
            b.update(dt, pointer)

        if self.game.state == Game.OVER and self.game.over_time >= config.GAME_OVER_DELAY and not self.finished:
            self.finished = True
            self.app.finish_game(self.game)

    def on_click(self, x, y):
        buttons = self.overlay_buttons if self.game.state == Game.PAUSED else [self.pause_button]
        for b in list(buttons):
            if b.contains(x, y):
                b.click()
                return True
        return False

    def on_key(self, key):
        if key in ("space", "p", "P", "Escape"):
            self.toggle_pause()

    def destroy(self):
        self.renderer.destroy()
        self._hide_pause_overlay()
        super().destroy()


class GameOverScreen(Screen):
    def __init__(self, app, game, result):
        super().__init__(app)
        self.stats = game.stats
        self.reason = game.over_reason
        self.result = result

    def build(self):
        a, st = self.app, self.stats
        self.background()
        new_record = self.result.get("new_record")
        title = "TIME UP!" if self.reason == "time" else "GAME OVER"
        draw_panel(self.c, (self.tag,), W / 2, 360, 600, 520)
        self.heading(W / 2, 145, title, 42, COL["danger"] if self.reason == "bombs" else COL["gold"])
        self.score_item = self.text(W / 2, 228, "0", 60, COL["gold"], "bold")
        self.text(W / 2, 278, "FINAL SCORE", 11, COL["muted"], "bold")
        self.badge = None
        if new_record:
            self.badge = self.text(W / 2, 312, "NEW HIGH SCORE!", 16, COL["accent"], "bold")

        cells = (
            ("HIGHEST SCORE", f"{self.result.get('player_best', st.score):,}", COL["gold"]),
            ("FRUITS SLICED", str(st.fruits_sliced), COL["success"]),
            ("ACCURACY", f"{st.accuracy:.1f}%", COL["accent2"]),
            ("MAX COMBO", f"x{st.max_combo}", COL["accent"]),
            ("LEVEL REACHED", str(st.level), COL["text"]),
            ("BOMBS HIT", str(st.bombs_hit), COL["danger"]),
        )
        for i, (label, value, color) in enumerate(cells):
            x = W / 2 + ((i % 3) - 1) * 175
            y = 372 + (i // 3) * 80
            self.text(x, y, value, 24, color, "bold")
            self.text(x, y + 28, label, 10, COL["muted"], "bold")
        saved = self.result.get("saved", False)
        note = (f"Saved to the leaderboard as {a.settings['player_name']}" if saved
                else (a.db.error or "Score not saved"))
        self.text(W / 2, 530, note, 11, COL["muted"])
        self.button(W / 2 - 140, 585, 240, 54, "PLAY AGAIN", a.start_game, "primary", font_size=18)
        self.button(W / 2 + 140, 585, 240, 54, "MAIN MENU", a.show_menu, "neutral", font_size=18)

    def update(self, dt, pointer):
        super().update(dt, pointer)
        t = ease_out_cubic(self.time / 1.2)
        self.app.state.config(self.score_item, text=f"{int(self.stats.score * t):,}")

    def on_key(self, key):
        if key in ("Return", "space"):
            self.app.start_game()
        elif key == "Escape":
            self.app.show_menu()



# --------------------------------------------------------------------------
# Application
# --------------------------------------------------------------------------
class App:
    def __init__(self):
        self.root = tk.Tk()
        self.root.title(config.APP_TITLE)
        self.root.resizable(False, False)
        self.root.configure(bg=COL["bg_flat"])
        sx = max(0, (self.root.winfo_screenwidth() - W) // 2)
        sy = max(0, (self.root.winfo_screenheight() - H) // 2 - 20)
        self.root.geometry(f"{W}x{H}+{sx}+{sy}")
        self.canvas = tk.Canvas(self.root, width=W, height=H, bg=COL["bg_bottom"], highlightthickness=0)
        self.canvas.pack()
        self.fonts = FontBook(self.root)
        self.state = CanvasState(self.canvas)

        loading = self.canvas.create_text(W / 2, H / 2, text="Loading Gesture Slice...", fill=COL["text"],
                                          font=self.fonts.get(22, "bold"))
        self.root.update()

        self.db = DatabaseManager()
        self.settings = self.db.load_settings()
        self.sprites = SpriteBank(W, H)
        self.sound = SoundManager(enabled=self.settings["sound"] == "On")
        self.mouse = MouseDetector()
        self.canvas.delete(loading)

        self.screen = None
        self.pointer = PointerState()
        self._mouse_events = []
        self._mouse_pos = None
        self._last_mouse_move = -10.0
        self._next_screen = None
        self._after_id = None
        self._running = True
        self._last_tick = time.perf_counter()
        self._fps, self._fps_frames, self._fps_t0 = 0.0, 0, time.perf_counter()
        self.show_fps = False
        self._toasts = []

        self._build_overlay()
        self.canvas.bind("<Motion>", self._on_motion)
        self.canvas.bind("<B1-Motion>", self._on_motion)
        self.canvas.bind("<Button-1>", self._on_click)
        self.root.bind("<Key>", self._on_key)
        self.root.protocol("WM_DELETE_WINDOW", self.quit)

        self._set_screen(MainMenuScreen(self))
        for message in [self.db.error, self.sound.error, *self.sprites.warnings]:
            if message:
                self.toast(message, COL["warning"])

    def change_setting(self, key, value):
        self.settings[key] = value
        self.db.save_setting(key, value)
        if key == "sound":
            self.sound.enabled = value == "On"

    # ------------------------------------------------------------ navigation
    def show_menu(self):
        self.switch_to(lambda: MainMenuScreen(self))

    def show_how_to_play(self):
        self.switch_to(lambda: HowToPlayScreen(self))

    def show_leaderboard(self):
        self.switch_to(lambda: LeaderboardScreen(self))

    def show_settings(self):
        self.switch_to(lambda: SettingsScreen(self))

    def start_game(self):
        self.switch_to(lambda: GameScreen(self))

    def finish_game(self, game):
        result = self.db.record_session(self.settings["player_name"], game.stats, "Mouse")
        if self.db.error and not result.get("saved"):
            self.toast(self.db.error, COL["danger"])
        self.switch_to(lambda: GameOverScreen(self, game, result))

    def switch_to(self, factory):
        """Change screen at the start of the next frame (not in the middle of one)."""
        self._next_screen = factory

    def _set_screen(self, screen):
        if self.screen is not None:
            self.screen.destroy()
        self.screen = screen
        screen.build()
        self.raise_overlay()
        self.mouse.reset()
        try:
            self.canvas.configure(cursor="none" if screen.own_cursor else "")
        except tk.TclError:
            pass

    # --------------------------------------------------------------- overlay
    def _build_overlay(self):
        """FPS counter (press F) drawn above every screen."""
        self.fps_text = self.canvas.create_text(W - 14, H - 14, anchor="se", text="", fill=COL["dim"],
                                                font=self.fonts.get(10, "bold"), tags=("overlay",))

    def raise_overlay(self):
        self.canvas.tag_raise("overlay")
        self.canvas.tag_raise("toast")

    def toast(self, message, color=COL["text"], seconds=4.0):
        """Short notification at the top of the window."""
        y = 22 + 30 * len(self._toasts)
        bg = self.canvas.create_rectangle(0, 0, 0, 0, fill=COL["panel"], outline=color, tags=("toast",))
        item = self.canvas.create_text(W / 2, y, text=message, fill=color, width=W - 200,
                                       font=self.fonts.get(12, "bold"), tags=("toast",))
        x0, y0, x1, y1 = self.canvas.bbox(item)
        self.canvas.coords(bg, x0 - 14, y0 - 6, x1 + 14, y1 + 6)
        self._toasts.append([item, bg, seconds])

    def _update_overlay(self, dt):
        self.state.config(self.fps_text, text=f"{self._fps:.0f} FPS" if self.show_fps else "")

        for toast in list(self._toasts):
            toast[2] -= dt
            if toast[2] <= 0:
                self.canvas.delete(toast[0])
                self.canvas.delete(toast[1])
                self._toasts.remove(toast)

    # ----------------------------------------------------------------- input
    def _on_motion(self, event):
        self._mouse_events.append((event.x, event.y, time.perf_counter()))
        self._last_mouse_move = time.perf_counter()

    def _on_click(self, event):
        if self._next_screen is None and self.screen is not None:
            self.screen.on_click(event.x, event.y)

    def _on_key(self, event):
        if isinstance(event.widget, tk.Entry):
            return
        if event.keysym in ("f", "F"):
            self.show_fps = not self.show_fps
            return
        if self._next_screen is None and self.screen is not None:
            self.screen.on_key(event.keysym)

    def _collect_pointer(self, now):
        """Turn the mouse / trackpad movements since the last frame into a PointerState."""
        p = PointerState()
        for x, y, t in self._mouse_events:
            frame = self.mouse.update(x, y, t)
            p.points.append((x, y, t, frame.speed))
            if frame.segment:
                p.segments.append(frame.segment)
        self._mouse_events.clear()
        if self.mouse.last.present and now - self._last_mouse_move < 3.0:
            p.present, p.x, p.y = True, self.mouse.last.x, self.mouse.last.y
        return p

    # ------------------------------------------------------------- main loop
    def _tick(self):
        if not self._running:
            return
        start = time.perf_counter()
        dt = clamp(start - self._last_tick, 0.0, config.MAX_DT)
        self._last_tick = start
        try:
            self.pointer = self._collect_pointer(start)
            if self._next_screen is not None:
                factory, self._next_screen = self._next_screen, None
                self._set_screen(factory())
                self.pointer.segments.clear()
            if self.screen is not None:
                self.screen.update(dt, self.pointer)
            self._update_overlay(dt)
        except Exception:  # keep the game alive and show what happened in the terminal
            traceback.print_exc()

        self._fps_frames += 1
        if start - self._fps_t0 >= 0.5:
            self._fps = self._fps_frames / (start - self._fps_t0)
            self._fps_frames, self._fps_t0 = 0, start
        spent_ms = (time.perf_counter() - start) * 1000
        self._after_id = self.root.after(max(1, int(config.FRAME_MS - spent_ms)), self._tick)

    def run(self):
        self._last_tick = time.perf_counter()
        self._tick()
        self.root.mainloop()

    def quit(self):
        """Stop the loop and close the database and audio safely."""
        if not self._running:
            return
        self._running = False
        if self._after_id is not None:
            try:
                self.root.after_cancel(self._after_id)
            except tk.TclError:
                pass
        self.db.close()
        self.sound.shutdown()
        self.root.destroy()
