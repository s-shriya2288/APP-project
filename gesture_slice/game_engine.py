"""
game_engine.py - the rules of the game (Game) and how a game is drawn
(GameRenderer).

``Game`` is pure logic: give it the time step and the blade segments of this
frame and it moves every object, detects cuts, updates score / lives / level
and returns a list of *events* (FruitSliced, BombHit, Combo ...).  It never
touches Tkinter, so the whole rule set is unit-tested in tests/.

``GameRenderer`` turns the game state and those events into canvas items,
particles, sounds and the HUD.
"""

import math
import random
from dataclasses import dataclass, field

from . import config
from .fruit import Bomb, Fruit, choose_fruit_type
from .sprites import draw_background, draw_panel
from .particle_effects import BladeTrail, CanvasState, FloatingText, ParticleSystem, Splat
from .utils import clamp, lerp_color


# --------------------------------------------------------------------------
# Difficulty
# --------------------------------------------------------------------------
@dataclass(frozen=True)
class LevelSettings:
    level: int
    speed: float            # multiplies flight speed (gravity scales with speed^2)
    spawn_interval: float   # seconds between waves
    bomb_chance: float      # probability that a wave member is a bomb
    wave_min: int
    wave_max: int
    special_chance: float


def level_for_score(score):
    """Level 1, 2, 3 ... from the score thresholds in config."""
    thresholds = config.LEVEL_SCORE_THRESHOLDS
    level = 1
    for i, needed in enumerate(thresholds):
        if score >= needed:
            level = i + 1
    if score >= thresholds[-1]:
        level = len(thresholds) + int((score - thresholds[-1]) // config.LEVEL_STEP_AFTER)
    return level


def settings_for_level(level):
    """Level 1: slow fruit.  Level 2: faster.  Level 3: more bombs.  4+: keeps ramping."""
    if level <= 1:
        return LevelSettings(1, 0.82, 1.50, 0.05, 1, 2, 0.04)
    if level == 2:
        return LevelSettings(2, 1.00, 1.30, 0.08, 1, 3, 0.06)
    if level == 3:
        return LevelSettings(3, 1.05, 1.15, 0.18, 2, 3, 0.07)
    k = level - 4
    return LevelSettings(
        level,
        speed=min(1.6, 1.10 + 0.06 * k),
        spawn_interval=max(0.6, 1.05 - 0.08 * k),
        bomb_chance=min(0.32, 0.20 + 0.03 * k),
        wave_min=2,
        wave_max=min(5, 4 + k // 2),
        special_chance=0.08,
    )


# --------------------------------------------------------------------------
# Statistics and events
# --------------------------------------------------------------------------
@dataclass
class GameStats:
    score: int = 0
    fruits_sliced: int = 0
    fruits_missed: int = 0
    fruits_spawned: int = 0
    bombs_hit: int = 0
    max_combo: int = 0
    level: int = 1
    elapsed: float = 0.0

    @property
    def accuracy(self):
        """Percentage of fruit that was sliced instead of dropped."""
        judged = self.fruits_sliced + self.fruits_missed
        return round(100.0 * self.fruits_sliced / judged, 1) if judged else 0.0


@dataclass
class FruitSliced:
    fruit: Fruit
    halves: list
    angle: float
    points: int


@dataclass
class BombHit:
    bomb: Bomb
    lives_left: int


@dataclass
class ComboScored:
    count: int
    bonus: int
    x: float
    y: float


@dataclass
class FruitMissed:
    fruit: Fruit


@dataclass
class LevelUp:
    level: int


@dataclass
class CountdownTick:
    number: int          # 3, 2, 1 ... and 0 means "GO"


@dataclass
class GameOver:
    reason: str          # "time" or "bombs"


# --------------------------------------------------------------------------
# Game logic
# --------------------------------------------------------------------------
class Game:
    COUNTDOWN, PLAYING, PAUSED, OVER = "countdown", "playing", "paused", "over"

    def __init__(self, width=config.WIDTH, height=config.HEIGHT,
                 round_seconds=config.DEFAULT_ROUND_SECONDS,
                 slice_speed=config.SLICE_SENSITIVITY[config.DEFAULT_SENSITIVITY], rng=None):
        self.width, self.height = width, height
        self.round_seconds = round_seconds
        self.slice_speed = slice_speed
        self.rng = rng or random.Random()
        self.reset()

    def reset(self):
        self.state = self.COUNTDOWN
        self.countdown = float(config.COUNTDOWN_SECONDS)
        self.time_left = float(self.round_seconds)
        self.lives = config.START_LIVES
        self.stats = GameStats()
        self.fruits, self.bombs, self.halves = [], [], []
        self.pending = []                    # [delay, "fruit"/"bomb"] queued wave members
        self.spawn_timer = 0.4
        self.combo_count = 0
        self.combo_timer = 0.0
        self.combo_pos = (0.0, 0.0)
        self.invulnerable = 0.0
        self.over_reason = None
        self.over_time = 0.0
        self.level_settings = settings_for_level(1)

    # --- state control ----------------------------------------------------
    @property
    def level(self):
        return self.stats.level

    @property
    def active(self):
        return self.state in (self.COUNTDOWN, self.PLAYING)

    def pause(self):
        if self.state in (self.PLAYING, self.COUNTDOWN):
            self._paused_from = self.state
            self.state = self.PAUSED
            return True
        return False

    def resume(self):
        if self.state == self.PAUSED:
            self.state = getattr(self, "_paused_from", self.PLAYING)
            return True
        return False

    def toggle_pause(self):
        return self.resume() if self.state == self.PAUSED else self.pause()

    # --- main update --------------------------------------------------------
    def update(self, dt, segments=()):
        """Advance the game by dt seconds.

        segments: iterable of (ax, ay, bx, by, speed) blade movements since
        the previous frame.  Returns a list of event objects.
        """
        events = []
        if self.state == self.PAUSED:
            return events

        if self.state == self.COUNTDOWN:
            before = math.ceil(self.countdown)
            self.countdown -= dt
            after = math.ceil(self.countdown)
            if after != before:
                events.append(CountdownTick(max(after, 0)))
            if self.countdown <= 0:
                self.state = self.PLAYING
            return events

        self._move_objects(dt)
        if self.state == self.OVER:
            self.over_time += dt
            return events

        # ---- PLAYING ----
        self.stats.elapsed += dt
        self.time_left = max(0.0, self.time_left - dt)
        self.invulnerable = max(0.0, self.invulnerable - dt)
        self._spawn(dt)
        self._collide(segments, events)
        self._remove_offscreen(events)
        self._update_combo(dt, events)
        self._update_level(events)

        if self.lives <= 0:
            self._end("bombs", events)
        elif self.time_left <= 0:
            self._end("time", events)
        return events

    # --- internals ----------------------------------------------------------
    def _end(self, reason, events):
        self._flush_combo(events)
        self.state = self.OVER
        self.over_reason = reason
        self.over_time = 0.0
        self.pending.clear()
        events.append(GameOver(reason))

    def _move_objects(self, dt):
        for obj in self.fruits:
            obj.update(dt)
        for obj in self.bombs:
            obj.update(dt)
        for obj in self.halves:
            obj.update(dt)

    def _spawn(self, dt):
        s = self.level_settings
        self.spawn_timer -= dt
        if self.spawn_timer <= 0:
            count = self.rng.randint(s.wave_min, s.wave_max)
            bombs_left = 1 if s.level < 5 else 2
            delay = 0.0
            for _ in range(count):
                is_bomb = bombs_left > 0 and self.rng.random() < s.bomb_chance
                bombs_left -= is_bomb
                self.pending.append([delay, "bomb" if is_bomb else "fruit"])
                delay += self.rng.uniform(0.08, 0.25)
            self.spawn_timer = s.spawn_interval * self.rng.uniform(0.85, 1.15)

        still_waiting = []
        for item in self.pending:
            item[0] -= dt
            if item[0] > 0:
                still_waiting.append(item)
            elif len(self.fruits) + len(self.bombs) < config.MAX_ACTIVE_OBJECTS:
                self._launch(item[1])
        self.pending = still_waiting

    def launch_parameters(self, radius):
        """Start position and velocity of a throw that peaks inside the screen."""
        s = self.level_settings
        g = config.GRAVITY * s.speed ** 2
        w, h = self.width, self.height
        x0 = self.rng.uniform(0.12 * w, 0.88 * w)
        y0 = h + radius
        apex_y = self.rng.uniform(0.12 * h, 0.42 * h)
        vy = -math.sqrt(2 * g * (y0 - apex_y))
        flight_time = 2 * -vy / g
        target_x = self.rng.uniform(0.3 * w, 0.7 * w)
        vx = (target_x - x0) / flight_time * self.rng.uniform(0.5, 1.0)
        return x0, y0, vx, vy, g

    def _launch(self, what):
        if what == "bomb":
            x, y, vx, vy, g = self.launch_parameters(34)
            self.bombs.append(Bomb(x, y, vx, vy, g, rng=self.rng))
        else:
            kind = choose_fruit_type(self.rng, self.level_settings.special_chance)
            x, y, vx, vy, g = self.launch_parameters(kind.radius)
            self.fruits.append(Fruit(kind, x, y, vx, vy, g, rng=self.rng))
            self.stats.fruits_spawned += 1

    def _collide(self, segments, events):
        for ax, ay, bx, by, speed in segments:
            if speed < self.slice_speed:
                continue                       # slow movement only aims, it does not cut
            angle = math.degrees(math.atan2(by - ay, bx - ax))
            for fruit in self.fruits:
                if fruit.alive and fruit.hit_by(ax, ay, bx, by):
                    halves = fruit.slice(angle, self.rng)
                    self.halves.extend(halves)
                    self.stats.score += fruit.points
                    self.stats.fruits_sliced += 1
                    self.combo_count += 1
                    self.combo_timer = config.COMBO_WINDOW
                    self.combo_pos = (fruit.x, fruit.y)
                    self.stats.max_combo = max(self.stats.max_combo, self.combo_count)
                    events.append(FruitSliced(fruit, halves, angle, fruit.points))
            for bomb in self.bombs:
                if bomb.alive and self.invulnerable <= 0 and bomb.hit_by(ax, ay, bx, by):
                    bomb.explode()
                    self.lives -= 1
                    self.stats.bombs_hit += 1
                    self.invulnerable = config.BOMB_INVULNERABLE_SECONDS
                    self.combo_count = 0
                    self.combo_timer = 0.0
                    events.append(BombHit(bomb, self.lives))
        self.fruits = [f for f in self.fruits if f.alive]
        self.bombs = [b for b in self.bombs if b.alive]

    def _remove_offscreen(self, events):
        kept = []
        for fruit in self.fruits:
            if fruit.is_offscreen(self.width, self.height):
                self.stats.fruits_missed += 1
                events.append(FruitMissed(fruit))
            else:
                kept.append(fruit)
        self.fruits = kept
        self.bombs = [b for b in self.bombs if not b.is_offscreen(self.width, self.height)]
        self.halves = [h for h in self.halves if not h.is_offscreen(self.width, self.height)]

    def _update_combo(self, dt, events):
        if self.combo_timer > 0:
            self.combo_timer -= dt
            if self.combo_timer <= 0:
                self._flush_combo(events)

    def _flush_combo(self, events):
        if self.combo_count >= 2:
            bonus = (self.combo_count - 1) * config.COMBO_BONUS_PER_EXTRA_FRUIT
            self.stats.score += bonus
            events.append(ComboScored(self.combo_count, bonus, *self.combo_pos))
        self.combo_count = 0
        self.combo_timer = 0.0

    def _update_level(self, events):
        level = level_for_score(self.stats.score)
        if level != self.stats.level:
            self.stats.level = level
            self.level_settings = settings_for_level(level)
            events.append(LevelUp(level))


# --------------------------------------------------------------------------
# Drawing
# --------------------------------------------------------------------------
@dataclass
class _Visual:
    item: int
    frame: int = -1
    extra: list = field(default_factory=list)


class GameRenderer:
    """Draws one Game on the shared canvas.  Everything it creates is tagged
    ``game`` (or pooled) and removed by ``destroy``."""

    TAG = "game"

    def __init__(self, canvas, sprites, fonts, sound, width=config.WIDTH, height=config.HEIGHT):
        self.canvas, self.sprites, self.fonts, self.sound = canvas, sprites, fonts, sound
        self.width, self.height = width, height
        self.rng = random.Random()
        self.visuals = {}
        self.splats, self.texts = [], []
        self.shake_time, self.shake_mag = 0.0, 0.0
        self.warning_time = 0.0
        self.display_score = 0.0
        self.score_pulse = 0.0
        self.last_tick_second = None
        self.heart_shake = 0.0
        self.state = CanvasState(canvas)
        c, T = canvas, self.TAG

        draw_background(c, T, width, height)
        # Invisible markers: new items are inserted *below* the next marker so
        # splats < halves < fruits & bombs < particles < trail < text < HUD.
        self.m_splat = c.create_line(0, 0, 0, 0, state="hidden", tags=(T,))
        self.m_half = c.create_line(0, 0, 0, 0, state="hidden", tags=(T,))
        self.m_obj = c.create_line(0, 0, 0, 0, state="hidden", tags=(T,))
        self.particles = ParticleSystem(canvas, rng=self.rng)
        self.trail = BladeTrail(canvas)
        self.cursor_glow = c.create_image(-100, -100, image=sprites.cursor_glow, tags=(T,))
        self.cursor_dot = c.create_oval(0, 0, 0, 0, fill="#ffffff", outline=config.COLORS["accent2"],
                                        width=2, tags=(T,))
        self.hold_arc = c.create_arc(0, 0, 0, 0, start=90, extent=0, style="arc", width=5,
                                     outline=config.COLORS["warning"], state="hidden", tags=(T,))
        self.m_text = c.create_line(0, 0, 0, 0, state="hidden", tags=(T,))
        # Red warning frame after a bomb: nested outlines fading inwards.
        self.warning = [c.create_rectangle(i * 7, i * 7, width - i * 7, height - i * 7, width=8,
                                           outline=config.COLORS["danger"], state="hidden", tags=(T,))
                        for i in range(6)]
        self._build_hud()

    # ------------------------------------------------------------------ HUD
    def _build_hud(self):
        c, T, f, col = self.canvas, self.TAG, self.fonts, config.COLORS
        draw_panel(c, (T,), self.width / 2, 44, self.width - 40, 66, radius=22, fill="#140f36")
        self._label(70, 26, "SCORE")
        self.score_text = c.create_text(70, 52, text="0", anchor="w", fill=col["gold"],
                                        font=f.get(28, "bold"), tags=(T,))
        self._label(300, 26, "LEVEL")
        self.level_text = c.create_text(300, 52, text="1", anchor="w", fill=col["accent2"],
                                        font=f.get(24, "bold"), tags=(T,))
        self._label(self.width / 2, 26, "TIME", anchor="n")
        self.time_text = c.create_text(self.width / 2, 54, text="0:00", fill=col["text"],
                                       font=f.get(26, "bold"), tags=(T,))
        self._label(690, 26, "COMBO")
        self.combo_text = c.create_text(690, 52, text="x0", anchor="w", fill=col["accent"],
                                        font=f.get(24, "bold"), tags=(T,))
        self.best_combo_text = c.create_text(750, 56, text="best x0", anchor="w", fill=col["muted"],
                                             font=f.get(11, "bold"), tags=(T,))
        self._label(850, 26, "LIVES")
        self.hearts = [c.create_image(865 + i * 34, 54, image=self.sprites.heart_full, tags=(T,))
                       for i in range(config.START_LIVES)]
        self.banner_shadow = c.create_text(self.width / 2 + 3, self.height / 2 + 4, text="", fill="#000000",
                                           font=f.get(64, "bold"), tags=(T,))
        self.banner = c.create_text(self.width / 2, self.height / 2, text="", fill=col["text"],
                                    font=f.get(64, "bold"), tags=(T,))
        self.banner_time = 0.0
        self.banner_life = 1.0

    def _label(self, x, y, text, anchor="w"):
        self.canvas.create_text(x, y, text=text, anchor=anchor, fill=config.COLORS["muted"],
                                font=self.fonts.get(10, "bold"), tags=(self.TAG,))

    def show_banner(self, text, color, life=1.0, size=64):
        self.state.config(self.banner, text=text, fill=color, font=self.fonts.get(size, "bold"))
        self.state.config(self.banner_shadow, text=text, font=self.fonts.get(size, "bold"))
        self.banner_time = life
        self.banner_life = life

    # ------------------------------------------------------------- per frame
    def render(self, game, dt, pointer, now):
        ox = oy = 0.0
        if self.shake_time > 0:
            self.shake_time -= dt
            mag = self.shake_mag * clamp(self.shake_time / 0.4, 0, 1)
            ox, oy = self.rng.uniform(-mag, mag), self.rng.uniform(-mag, mag)

        self._sync_objects(game, ox, oy)
        self.particles.update(dt, ox, oy)
        self.splats = [s for s in self.splats if s.update(dt)]
        self.texts = [t for t in self.texts if t.update(dt)]
        self.trail.update(now)
        self._draw_cursor(pointer)
        self._update_warning(dt)
        self._update_hud(game, dt)
        self._update_banner(dt)

    def _sync_objects(self, game, ox, oy):
        """Create / move / delete one canvas image per game object."""
        c, sp = self.canvas, self.sprites
        seen = set()
        for group, marker in ((game.halves, self.m_half), (game.fruits, self.m_obj), (game.bombs, self.m_obj)):
            for obj in group:
                seen.add(obj.uid)
                vis = self.visuals.get(obj.uid)
                frame = sp.frame_index(obj.angle)
                if hasattr(obj, "fuse_tip"):
                    images = sp.bomb
                elif group is game.halves:
                    images = sp.half[obj.kind.name]
                else:
                    images = sp.fruit[obj.kind.name]
                x, y = obj.x + ox, obj.y + oy
                if vis is None:
                    item = c.create_image(x, y, image=images[frame], tags=(self.TAG,))
                    c.tag_lower(item, marker)
                    vis = self.visuals[obj.uid] = _Visual(item, frame)
                    if hasattr(obj, "fuse_tip"):
                        for color in (config.COLORS["warning"], "#fff4b0"):
                            spark = c.create_oval(0, 0, 0, 0, fill=color, width=0, tags=(self.TAG,))
                            c.tag_lower(spark, marker)
                            vis.extra.append(spark)
                else:
                    c.coords(vis.item, x, y)
                    if frame != vis.frame:
                        vis.frame = frame
                        c.itemconfigure(vis.item, image=images[frame])
                if vis.extra:
                    fx, fy = obj.fuse_tip()
                    big = 5 + self.rng.random() * 4
                    small = big * 0.45
                    c.coords(vis.extra[0], fx - big + ox, fy - big + oy, fx + big + ox, fy + big + oy)
                    c.coords(vis.extra[1], fx - small + ox, fy - small + oy, fx + small + ox, fy + small + oy)
                    if self.rng.random() < 0.5:
                        self.particles.emit(fx, fy, "#ffcf4a", 1, speed=(30, 90), size=(1.5, 3),
                                            life=(0.15, 0.35), gravity=-60, spread=(200, 340))
        for uid in [u for u in self.visuals if u not in seen]:
            vis = self.visuals.pop(uid)
            c.delete(vis.item)
            for extra in vis.extra:
                c.delete(extra)

    def _draw_cursor(self, pointer):
        st = self.state
        if pointer is None or not pointer.present:
            st.coords(self.cursor_glow, -200, -200)
            st.coords(self.cursor_dot, -20, -20, -10, -10)
            st.config(self.hold_arc, state="hidden")
            return
        x, y = pointer.x, pointer.y
        st.coords(self.cursor_glow, x, y)
        st.coords(self.cursor_dot, x - 6, y - 6, x + 6, y + 6)
        if pointer.hold_progress > 0:
            color = config.COLORS["warning"] if pointer.gesture.value == "open_palm" else config.COLORS["success"]
            st.coords(self.hold_arc, x - 26, y - 26, x + 26, y + 26)
            st.config(self.hold_arc, state="normal", extent=-359.9 * pointer.hold_progress, outline=color)
        else:
            st.config(self.hold_arc, state="hidden")

    def _update_warning(self, dt):
        if self.warning_time <= 0:
            return
        self.warning_time = max(0.0, self.warning_time - dt)
        strength = self.warning_time / 0.8                      # 1 -> 0
        for i, item in enumerate(self.warning):
            fade = clamp(1 - strength + i * 0.16, 0, 1)
            if fade >= 1:
                self.state.config(item, state="hidden")
            else:
                self.state.config(item, state="normal",
                                  outline=lerp_color(config.COLORS["danger"], config.COLORS["bg_bottom"], fade))

    def _update_hud(self, game, dt):
        st, col = self.state, config.COLORS
        target = game.stats.score
        if target > self.display_score + 0.5:
            self.display_score += max(1.0, (target - self.display_score) * min(1.0, dt * 9))
            self.display_score = min(self.display_score, target)
        else:
            self.display_score = target
        if self.score_pulse > 0:
            self.score_pulse = max(0.0, self.score_pulse - dt * 3)
            st.config(self.score_text, font=self.fonts.get(int(28 + 10 * self.score_pulse), "bold"))
        st.config(self.score_text, text=f"{int(self.display_score):,}")
        st.config(self.level_text, text=str(game.level))

        remaining = math.ceil(game.time_left)
        st.config(self.time_text, text=f"{remaining // 60}:{remaining % 60:02d}",
                        fill=col["danger"] if remaining <= 10 else col["text"])
        if game.state == game.PLAYING and remaining <= 10 and remaining != self.last_tick_second:
            self.last_tick_second = remaining
            if remaining > 0:
                self.sound.play("tick")

        combo = game.combo_count if game.combo_count >= 2 else 0
        st.config(self.combo_text, text=f"x{combo}")
        st.config(self.best_combo_text, text=f"best x{game.stats.max_combo}")

        jitter = 0.0
        if self.heart_shake > 0:
            self.heart_shake -= dt
            jitter = self.rng.uniform(-4, 4)
        for i, heart in enumerate(self.hearts):
            alive = i < game.lives
            st.config(heart, image=self.sprites.heart_full if alive else self.sprites.heart_empty)
            st.coords(heart, 865 + i * 34 + (jitter if i == game.lives else 0), 54)

    def _update_banner(self, dt):
        if self.banner_time <= 0:
            return
        self.banner_time -= dt
        if self.banner_time <= 0:
            self.state.config(self.banner, text="")
            self.state.config(self.banner_shadow, text="")

    # ---------------------------------------------------------------- events
    def handle_events(self, events, game):
        col = config.COLORS
        for ev in events:
            if isinstance(ev, FruitSliced):
                f = ev.fruit
                kind = f.kind
                self.particles.emit(f.x, f.y, kind.juice, 16, speed=(100, 380), size=(2.5, 6))
                self.particles.emit(f.x, f.y, kind.flesh, 8, speed=(60, 220), size=(2, 4))
                self.particles.emit(f.x, f.y, "#ffffff", 6, speed=(200, 500), size=(1.5, 3),
                                    life=(0.15, 0.3), gravity=0, drag=4)
                if kind.special:
                    self.particles.emit(f.x, f.y, col["gold"], 24, speed=(150, 480), size=(2, 5),
                                        gravity=150, drag=2.5)
                self._add_splat(f.x, f.y, kind.name)
                self._add_text(f.x, f.y - 20, f"+{ev.points}", col["gold"] if kind.special else col["text"],
                               22 if kind.special else 18)
                self.score_pulse = 1.0
                self.sound.play("splat")
            elif isinstance(ev, BombHit):
                b = ev.bomb
                for color, n, spd in (("#ffffff", 10, (300, 700)), (col["warning"], 30, (150, 520)),
                                      (col["danger"], 24, (100, 420)), ("#6b6f80", 16, (40, 160))):
                    self.particles.emit(b.x, b.y, color, n, speed=spd, size=(2.5, 7), gravity=200, drag=2.2)
                self.shake_time, self.shake_mag = 0.45, 12
                self.warning_time = 0.8
                self.heart_shake = 0.5
                self._add_text(b.x, b.y - 30, "-1 LIFE", col["danger"], 26, life=1.1)
                self.sound.play("boom")
            elif isinstance(ev, ComboScored):
                self._add_text(ev.x, ev.y - 60, f"COMBO x{ev.count}  +{ev.bonus}", col["accent"], 26, life=1.2, rise=90)
                self.score_pulse = 1.0
                self.sound.play("combo")
            elif isinstance(ev, FruitMissed):
                x = clamp(ev.fruit.x, 40, self.width - 40)
                self._add_text(x, self.height - 30, "miss", col["dim"], 14, life=0.7, rise=30)
            elif isinstance(ev, LevelUp):
                self.show_banner(f"LEVEL {ev.level}", col["accent2"], 1.3, 54)
                self.sound.play("level")
            elif isinstance(ev, CountdownTick):
                if ev.number > 0:
                    self.show_banner(str(ev.number), col["text"], 0.9, 90)
                    self.sound.play("tick")
                else:
                    self.show_banner("SLICE!", col["gold"], 0.8, 80)
                    self.sound.play("level")
            elif isinstance(ev, GameOver):
                text = "TIME UP!" if ev.reason == "time" else "GAME OVER"
                self.show_banner(text, col["danger"] if ev.reason == "bombs" else col["gold"],
                                 config.GAME_OVER_DELAY + 1, 70)
                self.sound.play("gameover")

    def raise_cursor(self):
        """Keep the blade cursor visible above overlays such as the pause panel."""
        for item in (self.cursor_glow, self.cursor_dot, self.hold_arc):
            self.canvas.tag_raise(item)

    def add_trail_point(self, x, y, t, active):
        self.trail.add(x, y, t, active)

    def reset_trail(self):
        self.trail.reset()

    def _add_splat(self, x, y, name):
        if len(self.splats) >= config.MAX_SPLATS:
            self.splats.pop(0).destroy()
        self.splats.append(Splat(self.canvas, x, y, self.sprites.splat[name], below=self.m_splat))

    def _add_text(self, x, y, text, color, size, life=0.9, rise=70):
        if len(self.texts) > 12:
            self.texts.pop(0).destroy()
        self.texts.append(FloatingText(self.canvas, x, y, text, color, size, self.fonts.family,
                                       life=life, rise=rise, below=self.m_text))

    def destroy(self):
        for tag in (self.TAG, "particle", "trail", "floattext", "splat"):
            self.canvas.delete(tag)
        self.visuals.clear()
        self.splats.clear()
        self.texts.clear()


__all__ = [
    "Game", "GameRenderer", "GameStats", "LevelSettings", "level_for_score", "settings_for_level",
    "FruitSliced", "BombHit", "ComboScored", "FruitMissed", "LevelUp", "CountdownTick", "GameOver",
]
