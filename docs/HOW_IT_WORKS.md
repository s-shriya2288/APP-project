# How it works

## 1. Trackpad / mouse input and blade speed

Tkinter sends a `<Motion>` event every time the pointer moves. `App._on_motion`
saves `(x, y, time)`, and once per frame `MouseDetector` (`mouse_input.py`)
turns them into **cut segments**. `MotionTracker` remembers the previous point
and for every new one produces `(ax, ay, bx, by, speed)` where

```
speed = distance(previous, current) / (t_current − t_previous)     [px / s]
```

- If two points are more than 0.25 s apart, no segment is made. This avoids a
  "teleport cut" across the screen after you stop moving.
- A segment only cuts if its speed is above the **slice sensitivity**
  (Settings: Low 950, Medium 650, High 420 px/s), so slow moves just aim.
- Every point is also added to the `BladeTrail`, which draws the last 0.2 s
  of positions as tapered line segments (bright when fast enough to cut,
  dim when only aiming).

## 2. Collision detection

Each fruit and bomb is a circle (centre `C`, radius `r`). The blade movement
in one frame is the segment `A → B`. They touch when the closest
point of the segment to `C` is within `r`:

```
AB = B − A
t  = clamp( ((C − A) · AB) / |AB|² , 0, 1 )      projection of C onto AB
P  = A + t × AB                                   closest point on the segment
hit ⇔ |C − P| ≤ r   and   speed ≥ slice threshold
```

Clamping `t` to 0..1 matters: the infinite line through A and B might pass
through the fruit even when the actual swipe stopped short of it
(`fruit.segment_intersects_circle`, tested in `tests/test_collision.py`).

Testing the whole segment, not just the fingertip point, means fast swipes
can't "tunnel" through a fruit between two frames.

The slice threshold comes from *Settings → Slice sensitivity*:
Low 950 px/s, Medium 650 px/s, High 420 px/s.

When a fruit is cut, `Fruit.slice(angle)` replaces it with two `FruitHalf`
objects. The blade angle is `atan2(dy, dx)` of the segment. The halves are
rotated to that angle, so the cut edge lines up with your swipe, and they're
pushed apart along the normal of the cut line.

## 3. Physics, spawning and difficulty

Objects use semi-implicit Euler integration every frame:

```
vy += g × dt;   x += vx × dt;   y += vy × dt;   angle += spin × dt
```

A throw is designed backwards from where it should peak. For a chosen apex
height `y_apex` the launch speed is `vy = −√(2 g (y0 − y_apex))`, and `vx`
steers the fruit towards the middle of the screen during its flight time
`2|vy|/g`. Faster levels multiply speeds by `s` and gravity by `s²`, so the
arcs keep the same shape but play out quicker.

| Level | Score needed | Fruit speed | Wave every | Bomb chance | Wave size |
|---|---|---|---|---|---|
| 1 | 0 | 0.82× (slow) | 1.5 s | 5 % | 1–2 |
| 2 | 150 | 1.0× (faster) | 1.3 s | 8 % | 1–3 |
| 3 | 400 | 1.05× | 1.15 s | **18 %** | 2–3 |
| 4 | 750 | 1.1× | 1.05 s | 20 % | 2–4 |
| 5+ | 1200 (+600 each) | up to 1.6× | down to 0.6 s | up to 32 % | up to 5 |

**Scoring:** 10 per fruit, 20 per golden star. All fruit cut within 0.3 s of
each other form a **combo**, and a combo of N fruit adds (N − 1) × 15 points.
Fruit that fall off the screen count as *missed* for the accuracy figure
(`sliced / (sliced + missed)`).

**Lives:** 3. A bomb hit costs one, followed by 0.6 s of invulnerability so
one swipe can't cost two lives. The round ends when lives or time run out.

## 4. Performance: how it stays at 60 FPS

Tkinter isn't a game engine, so the code avoids everything that makes it
slow. These numbers were measured on an Apple-silicon Mac:

| Technique | Why |
|---|---|
| **`root.after(16 ms − work)`** game loop | Steady frame pacing without blocking the event loop. |
| **All images pre-rendered** at start-up (36 rotation frames per fruit) | Rotating or converting images while playing is far too slow. Spinning is just switching between ready-made frames. |
| **Object pools** for particles (120) and trail segments | Creating/deleting thousands of canvas items per second is slow. Pooled items are re-used and hidden when idle. |
| **`CanvasState`**: only call `itemconfigure`/`coords` when a value changes | Every Tk call repaints its area, even with an identical value. Skipping redundant calls took idle gameplay from 30 to 60 FPS. |
| **Plain shapes for the background and panels** instead of full-window images | Tk repaints the bounding box of all changes. Once fruit are everywhere that's the whole window, and repainting a 1100×700 photo costs ~30 ms. Solid shapes cost ~1 ms. Gameplay while slicing went from 30 to 60 FPS. |
| Caps on everything | ≤ 14 flying objects, ≤ 10 splats, ≤ 12 floating texts, lifetimes on every effect. |

Press **F** in the game to show the live FPS.
