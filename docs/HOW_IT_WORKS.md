# How it works

## 1. From webcam to fingertip

1. `HandTracker` reads a 640×480 frame with OpenCV.
2. The frame is **mirrored** (`cv2.flip(frame, 1)`), so moving your hand to
   the right moves the blade to the right, like a mirror.
3. MediaPipe Hands (`model_complexity=0`, the fastest model, one hand)
   returns **21 landmarks**, each an `(x, y)` pair from 0 to 1:

```
        8   12  16  20        tips
        7   11  15  19
        6   10  14  18        PIP (middle) joints
    4   5    9  13  17        MCP (knuckles)
     3
      2
       1
          0                   wrist
```

4. Landmark **8 = index fingertip** is the blade.

### Mapping camera → canvas

Your hand rarely reaches the very edge of the camera image, so only an inner
box (`CAMERA_ACTIVE_REGION = (0.12, 0.10, 0.88, 0.82)`) is stretched over the
whole 1100×700 game window:

```
u = clamp((x − 0.12) / (0.88 − 0.12), 0, 1)      canvas_x = u × 1100
v = clamp((y − 0.10) / (0.82 − 0.10), 0, 1)      canvas_y = v × 700
```

(`GestureDetector.map_to_canvas`)

## 2. Smoothing: the One Euro filter

Raw landmarks jitter by a few pixels from frame to frame. A plain moving
average removes jitter but makes the blade *lag* behind fast swipes, which is
fatal in a slicing game. The **One Euro filter** (Casiez et al., 2012) adapts:

```
speed      = smoothed derivative of the position
cutoff     = min_cutoff + beta × |speed|
alpha      = 1 / (1 + tau/dt),   tau = 1 / (2π × cutoff)
filtered   = alpha × raw + (1 − alpha) × previous
```

- finger nearly still → low cutoff → strong smoothing (no jitter)
- finger moving fast → high cutoff → almost no smoothing (no lag)

`OneEuroFilter` in `gesture_detection.py`. Tuning lives in `config.py`
(`ONE_EURO_MIN_CUTOFF`, `ONE_EURO_BETA`).

## 3. Movement, velocity and the slicing trail

`MotionTracker` remembers the previous smoothed point `(x, y, t)`. For every
new sample it produces a **cut segment** `(ax, ay, bx, by, speed)` where

```
speed = distance(previous, current) / (t_current − t_previous)     [px / s]
```

- If the two samples are more than 0.25 s apart (dropped frames), no segment
  is produced. This avoids a "teleport cut" across the screen.
- When the hand disappears, the filter and the previous point are reset for
  the same reason.
- Every sample is also added to the `BladeTrail`, which draws the last 0.2 s
  of positions as tapered line segments (bright when fast enough to
  cut, dim blue when only aiming).

## 4. Gesture recognition (pause / resume)

`GestureDetector.classify()` decides the pose from the 21 landmarks using
**distance ratios**, which don't depend on hand size, distance to the
camera or rotation:

```
finger extended  ⇔  |wrist → tip| > 1.12 × |wrist → PIP joint|
finger curled    ⇔  |wrist → tip| < 1.02 × |wrist → PIP joint|
thumb out        ⇔  |thumb tip → index knuckle| > 0.55 × palm size
```

| Pose | Rule | Command |
|---|---|---|
| OPEN_PALM | all 4 fingers extended + thumb out | **pause** |
| FIST | all 4 fingers curled | **resume** |
| POINT | index extended, ≥ 2 others curled | (normal play) |

**Confirmation delay.** A pose only triggers its command after being held
for **0.7 s** (`GESTURE_HOLD_SECONDS`) while the hand is nearly still
(< 380 px/s). That way an open hand during a fast swipe never pauses the
game by accident. Pose flickers shorter than 0.15 s are ignored, a 1 s
cooldown separates two commands, and each hold fires only once. A ring
around the cursor fills up while you hold, so the player sees it coming.

**Dwell click.** In menus, keeping the fingertip over a button for 1.1 s
presses it (a gold progress bar fills inside the button).

## 5. Collision detection

Each fruit and bomb is a circle (centre `C`, radius `r`). The blade movement
in one camera frame is the segment `A → B`. They touch when the closest
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
can't "tunnel" through a fruit between two camera frames.

The slice threshold comes from *Settings → Slice sensitivity*:
Low 950 px/s, Medium 650 px/s, High 420 px/s.

When a fruit is cut, `Fruit.slice(angle)` replaces it with two `FruitHalf`
objects. The blade angle is `atan2(dy, dx)` of the segment. The halves are
rotated to that angle, so the cut edge lines up with your swipe, and they're
pushed apart along the normal of the cut line.

## 6. Physics, spawning and difficulty

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

## 7. Performance: how it stays at 60 FPS

Tkinter isn't a game engine, so the code avoids everything that makes it
slow. These numbers were measured on an Apple-silicon Mac:

| Technique | Why |
|---|---|
| Camera + MediaPipe on a **background thread**, results via a queue | `hands.process()` takes 10–30 ms. On the main thread it would halve the frame rate. |
| **`root.after(16 ms − work)`** game loop | Steady frame pacing without blocking the event loop. |
| **All images pre-rendered** at start-up (36 rotation frames per fruit) | Rotating or converting images while playing is far too slow. Spinning is just switching between ready-made frames. |
| **Object pools** for particles (260) and trail segments | Creating/deleting thousands of canvas items per second is slow. Pooled items are re-used and hidden when idle. |
| **`CanvasState`**: only call `itemconfigure`/`coords` when a value changes | Every Tk call repaints its area, even with an identical value. Skipping redundant calls took idle gameplay from 30 to 60 FPS. |
| **Plain shapes for the background and panels** instead of full-window images | Tk repaints the bounding box of all changes. Once fruit are everywhere that's the whole window, and repainting a 1100×700 photo costs ~30 ms. Solid shapes cost ~1 ms. Gameplay while slicing went from 30 to 60 FPS. |
| Caps on everything | ≤ 14 flying objects, ≤ 10 splats, ≤ 12 floating texts, lifetimes on every effect. |

Press **F** in the game to show the live FPS and camera FPS.
