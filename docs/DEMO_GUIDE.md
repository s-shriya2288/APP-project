# APP project demonstration guide

A suggested 10–12 minute demo script for presenting Gesture Slice.

## Before the demo (5 minutes earlier)

- [ ] Laptop on power, good light on your face and hand, plain background behind you
- [ ] Close Zoom / Teams / browser tabs that might hold the camera
- [ ] `source .venv/bin/activate` (Windows: `.venv\Scripts\Activate.ps1`)
- [ ] `python main.py` once to confirm the camera works (allow the permission prompt)
- [ ] In **Settings**: enter the presenter's name, Control mode = Gesture, Camera preview = On
- [ ] Play one short round so the leaderboard isn't empty
- [ ] Open `README.md` and `docs/ARCHITECTURE.md` in a browser tab (GitHub) for the code walk-through

## Demo script

### 1. Introduction (1 min)
"Gesture Slice is a desktop arcade game controlled only by hand movements,
tracked through the laptop webcam. It's built with Python, Tkinter for the
GUI, OpenCV for the camera, MediaPipe for hand landmarks and SQLite for scores."

### 2. Hands-free menu (1 min)
- Point at the camera: the cyan cursor follows your fingertip.
- Show the camera preview (bottom-left) with the 21-point hand skeleton and
  the status chip: "Hand tracked – point".
- Hover over **HOW TO PLAY** until the gold bar fills, which opens it without
  touching the laptop. Go **BACK** the same way.

### 3. Gameplay (3 min)
- Hover **PLAY**. Countdown 3-2-1-SLICE!
- Slice fruit with fast swipes and point out the knife trail, juice
  particles, the splitting halves and the floating points.
- Cut several fruit in one swipe → **COMBO** bonus.
- Show the HUD: score, level, timer, combo, lives.
- Mention: "slow movements only aim, a cut needs speed". Move slowly through
  a fruit to show it doesn't break.
- Hit a bomb on purpose: red flash, shake, a heart is lost.

### 4. Gesture commands (1 min)
- Hold an **open palm**: the orange ring fills and the game pauses.
- Make a **fist**: the green ring fills and the game resumes.
- Explain the 0.7 s confirmation delay that prevents accidental pauses.

### 5. Results + database (1 min)
- Let the round finish → Game Over screen: final score, highest score,
  fruits sliced, accuracy, max combo.
- Open the **Leaderboard**: data persists in SQLite.
- Optional: in a terminal, `sqlite3 data/gesture_slice.db "SELECT * FROM game_sessions;"`

### 6. Robustness (1 min)
- **Settings → Control mode → Mouse**: the webcam turns off safely and the
  mouse takes over. Switch back to Gesture and the camera restarts.
- Press **F** to show the live frame rate (≈ 60 FPS).

### 7. Code walk-through (3 min)
Show on GitHub:
1. **Architecture diagram** in the README: the two threads and the queue.
2. `hand_tracking.py` → `_run()`: camera loop on a background thread, `queue.Queue`.
3. `gesture_detection.py` → `classify()` (distance ratios) and `OneEuroFilter`.
4. `fruit.py` → `segment_intersects_circle()`: the collision maths.
5. `game_engine.py` → `Game.update()` returns *events*, so logic and drawing stay separate.
6. `database.py` → the UPSERT transaction.
7. `tests/`: run `python -m unittest discover -s tests` live (36 tests pass in < 1 s),
   and show the green GitHub Actions check.

## Likely examiner questions

| Question | Short answer |
|---|---|
| Why a background thread? | MediaPipe takes 10–30 ms per frame. On the Tk thread it would freeze the UI. The thread hands results over through a thread-safe `queue.Queue`. |
| How do you detect a slice? | Distance from the fruit centre to the fingertip's movement segment ≤ radius, *and* the segment speed is above a threshold. |
| How do you avoid jitter? | One Euro filter: an adaptive low-pass that smooths heavily when still and lightly when moving fast. |
| How do you avoid accidental pauses? | Pose must be held 0.7 s with a nearly still hand, short flickers are ignored, and there's a 1 s cooldown. |
| Why Tkinter and not Pygame? | Project requirement. We kept Tkinter at 60 FPS by pre-rendering images, pooling canvas items, skipping redundant Tk calls and drawing the backdrop with vectors. |
| What if there's no webcam? | Clear notice, automatic mouse fallback, and the game is fully playable. |
| What's stored in the database? | Players, every game session, high scores, per-player statistics and settings. See `docs/DATABASE.md`. |
