# Demo guide

A 10-minute plan for presenting Gesture Slice.

## Before the demo

- [ ] Laptop on charge
- [ ] `source .venv/bin/activate` (Windows: `.venv\Scripts\activate`) and `python main.py` once to check it opens
- [ ] In **Settings**, type the presenter's name
- [ ] Play one short round so the leaderboard isn't empty
- [ ] Open the GitHub repo in a browser tab for the code walk-through

## Demo plan

### 1. Introduction (1 min)
"Gesture Slice is a fruit slicing game made in Python with Tkinter. You cut the
fruit by swiping on the trackpad. Scores are saved in a SQLite database."

### 2. Menu and How to Play (1 min)
- Show the main menu and the **How to Play** screen.

### 3. Gameplay (3 min)
- Click **PLAY**. Countdown 3-2-1-SLICE!
- Swipe fast through fruit: point out the trail, juice, the two halves and the points.
- Cut 2+ fruits in one swipe for a **COMBO** bonus.
- Show the top bar: score, level, timer, combo, lives.
- Move slowly through a fruit to show it doesn't cut: "a cut needs speed".
- Hit a bomb on purpose: red flash, shake, a heart is lost.
- Press **Space** to pause, then Space again to resume.

### 4. Results and database (1 min)
- Let the round end → results screen (score, best, accuracy, max combo).
- Open the **Leaderboard**: the data is saved in SQLite.
- Optional: `sqlite3 data/gesture_slice.db "SELECT * FROM game_sessions;"`

### 5. Code walk-through (3 min)
1. `ui.py`: `tk.Tk()`, the `Canvas`, the `bind()` calls and the `root.after()` game loop.
2. `mouse_input.py`: how a swipe becomes a segment with a speed.
3. `fruit.py` → `segment_intersects_circle()`: the collision maths.
4. `game_engine.py` → `Game.update()` returns *events*, so rules and drawing are separate.
5. `database.py`: the tables and the save transaction.
6. Run `python -m unittest discover -s tests` live and show the green GitHub Actions check.

## Likely questions

| Question | Short answer |
|---|---|
| How do you detect a slice? | The distance from the fruit's centre to the swipe segment is less than its radius, *and* the swipe is fast enough. |
| Why do slow moves not cut? | Speed = distance / time between two points. Only segments above the slice sensitivity count. |
| How is the game loop made in Tkinter? | `root.after(16, self._tick)` runs about 60 times a second without freezing the window. |
| How did you keep Tkinter fast? | Images are drawn once at the start, canvas items are reused, and Tk is only updated when a value changes. |
| What's in the database? | Players, every game, high scores, player statistics and settings. See `docs/DATABASE.md`. |
