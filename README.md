# Gaming Arcade: Gesture Slice

Our project for **Advanced Programming Practices (APP)**.

Gesture Slice is a fruit slicing game made in **Python with Tkinter**. You play it with
**swipe gestures on the trackpad** (or the mouse). The pointer is your knife: swipe fast
through the fruit to cut it, and stay away from the bombs.

![Main menu](docs/screenshots/01_menu.png)

## Features

- Swipe on the trackpad or with the mouse to cut fruit (slow moves only aim)
- Score, combos, golden star fruit, levels, 3 lives, and bombs
- Pause with Space / P or the II button
- Leaderboard and player stats saved in a SQLite database
- Settings for player name, sound, round length and slice sensitivity

![Gameplay](docs/screenshots/04_gameplay.png)

## How to run

You need **Python 3.9 or newer** (we used 3.11).

```bash
git clone https://github.com/s-shriya2288/APP-project.git
cd APP-project
python3.11 -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -r requirements.txt
python main.py
```

## How to play

| Action | What to do |
|---|---|
| Move the knife | Move your finger on the trackpad (or move the mouse) |
| Cut fruit | Swipe fast through it (slow moves only aim) |
| Pause / resume | Space or P, or click the II button |
| Back to menu | Esc |
| Show FPS | F |

Points: normal fruit = 10, golden star = 20, and cutting 2 or more fruits in one swipe gives a combo bonus.
Hitting a bomb costs one life. The round ends when time runs out or you lose all 3 lives.

## Technologies used

| Library | What we used it for |
|---|---|
| **Tkinter** | The window, all screens, drawing the game, the game loop |
| NumPy | Making the sound effects |
| Pillow | Drawing the fruit and button images |
| SQLite (`sqlite3`) | Saving players, games, high scores and stats |
| pygame | Only for playing sounds |

## Where we used Tkinter

Most of the Tkinter code is in [`gesture_slice/ui.py`](gesture_slice/ui.py).

- `tk.Tk()` creates the main window.
- One big `tk.Canvas` is used for everything. Fruit, bombs, buttons, the score and the knife trail
  are canvas items made with `create_image`, `create_text`, `create_line` and `create_oval`,
  and moved every frame with `canvas.coords()`.
- `canvas.bind("<Motion>")`, `bind("<Button-1>")` and `root.bind("<Key>")` handle the mouse and keyboard.
- `tk.Entry` is the text box for the player name on the Settings screen.
- **The game loop:** `root.after(16, self._tick)` runs about 60 times a second. Each time it reads
  the trackpad movements, updates the game and redraws.
- `ImageTk.PhotoImage` turns the fruit pictures (drawn with Pillow) into images the canvas can show.

**Why `after()` and not a `while` loop:** a `while True` loop would never give control back to
Tkinter, so the window would freeze. `after()` runs one frame, then lets Tkinter handle clicks and
redraws before the next frame.

## How it works

```
Trackpad -> ui.py (<Motion> events) -> mouse_input.py -> game_engine.py -> ui.py (draws on Canvas)
                                         (swipe segments,   (rules, score,          |
                                          speed)             collisions)            v
                                                                              database.py (SQLite)
```

1. **ui.py** gets a `<Motion>` event from Tkinter every time the pointer moves.
2. **mouse_input.py** joins each point to the previous one to make a line (segment) and works out
   the speed (distance ÷ time).
3. **game_engine.py** moves the fruit with gravity, checks if the swipe line touches a fruit,
   and updates the score, combos, lives and level.
4. **ui.py** draws everything on the Tkinter canvas.
5. **database.py** saves the result when the game ends.

**Collision check:** between two movements the pointer goes from point A to point B. A fruit is cut if
the shortest distance from its centre to the line AB is less than its radius, and the pointer
was moving fast enough. More details are in [docs/HOW_IT_WORKS.md](docs/HOW_IT_WORKS.md).

## Project structure

```
APP-project/
├── main.py                  starts the app
├── gesture_slice/
│   ├── config.py            all settings and constants
│   ├── ui.py                Tkinter window and screens
│   ├── game_engine.py       game rules + drawing the game
│   ├── fruit.py             Fruit, Bomb classes and collision maths
│   ├── mouse_input.py       trackpad/mouse -> swipe segments + speed
│   ├── particle_effects.py  juice drops and knife trail
│   ├── sprites.py           draws fruit/button images with Pillow
│   ├── sound.py             sound effects
│   ├── database.py          SQLite
│   └── utils.py             small helper functions
├── tests/                   unit tests
├── docs/                    extra documentation and screenshots
├── website/                 project web page (Vercel)
└── scripts/                 build the desktop app
```

## Database

There are 4 main tables: `players`, `game_sessions`, `high_scores` and `game_statistics`
(plus `settings`). Every finished game is saved in one transaction. See [docs/DATABASE.md](docs/DATABASE.md).

## Testing

```bash
python -m unittest discover -s tests -v
```

There are 32 unit tests for the collision maths, physics, game rules, mouse input and database.
GitHub Actions runs them on every push ([.github/workflows/ci.yml](.github/workflows/ci.yml)).

## Making a desktop app

```bash
pip install -r requirements-dev.txt
./scripts/build_desktop_app.sh      # Windows: scripts\build_desktop_app.bat
```

This uses PyInstaller to make `dist/GestureSlice.app` (or `GestureSlice.exe` on Windows),
which you can open by double-clicking it.

## Problems we faced

| Problem | Fix |
|---|---|
| Game only ran at ~30 FPS | Drew the background with plain shapes instead of a big image, and only update Tk when something changes |
| Slow moves cut fruit by accident | A swipe only cuts if it is faster than the slice sensitivity |
| Pointer jumping across the screen cut everything | Points more than 0.25 s apart don't make a cut |
| `ModuleNotFoundError: tkinter` on Linux | `sudo apt install python3-tk` |

## More docs

- [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md): classes and how the files connect
- [docs/HOW_IT_WORKS.md](docs/HOW_IT_WORKS.md): input, collision and physics
- [docs/DATABASE.md](docs/DATABASE.md): tables and queries
- [docs/WORKFLOW.md](docs/WORKFLOW.md): how we built it step by step
- [docs/DEMO_GUIDE.md](docs/DEMO_GUIDE.md): what to show in the demo

## License

MIT
