"""
Automated end-to-end run of the real Tkinter window (needs a display).

    python tests/manual_ui_smoke.py [screenshot_dir]

It opens every screen, plays two games with scripted mouse swipes, pauses
and resumes with the keyboard, and checks that nothing raises.  Uses a
temporary database.
"""

import os
import sys
import tempfile
import time
import traceback

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from gesture_slice import config  # noqa: E402

TMP = tempfile.mkdtemp()
config.DB_PATH = os.path.join(TMP, "smoke.db")
config.DEFAULT_SETTINGS["round_seconds"] = "60"

from tools.canvas_snapshot import install_image_registry, snapshot  # noqa: E402

install_image_registry()

from gesture_slice import ui  # noqa: E402
from gesture_slice.game_engine import Game  # noqa: E402

SHOTS = sys.argv[1] if len(sys.argv) > 1 else None
errors = []


def main():
    app = ui.App()
    real_print_exc = traceback.print_exc

    def capture_exc(*a, **k):
        errors.append(traceback.format_exc())
        real_print_exc()
    traceback.print_exc = capture_exc

    steps = []

    def at(t, fn):
        steps.append((t, fn))

    def shot(name):
        def take():
            if SHOTS:
                snapshot(app.canvas, os.path.join(SHOTS, f"{name}.png"))
        return take

    def swipe_burst():
        """Fast mouse swipes straight through the fruit currently on screen."""
        c = app.canvas
        screen = app.screen
        if not isinstance(screen, ui.GameScreen):
            return
        targets = [f for f in screen.game.fruits if 80 < f.y < config.HEIGHT - 60][:2]
        # Tk merges motion events sent at once, so space the points out in time
        # like a real fast mouse movement (one point every 12 ms).
        step = 0
        for f in targets:
            x0, y0 = f.x - 160, f.y - 50
            for i in range(9):
                app.root.after(step * 12, lambda x=x0 + i * 40, y=y0 + i * 12:
                               c.event_generate("<Motion>", x=int(x), y=int(y)))
                step += 1

    def keep_swiping(until):
        def run():
            if time.perf_counter() < until and isinstance(app.screen, ui.GameScreen):
                swipe_burst()
                app.root.after(260, run)
        return run

    at(1.0, shot("01_menu"))
    at(1.3, app.show_how_to_play)
    at(2.2, shot("02_how_to_play"))
    at(2.4, app.show_settings)
    at(3.3, shot("03_settings"))
    at(3.5, app.start_game)
    at(4.0, lambda: keep_swiping(time.perf_counter() + 9)())
    at(9.5, shot("04_gameplay"))
    at(11.0, shot("05_gameplay_later"))
    at(13.2, lambda: app.screen.pause())
    at(13.8, shot("06_paused"))
    at(14.0, lambda: app.screen.resume())
    at(14.2, lambda: setattr(app.screen.game, "time_left", 0.3))
    at(17.0, shot("07_game_over"))
    at(17.3, app.show_leaderboard)
    at(18.2, shot("08_leaderboard"))

    # --- second game: keyboard pause / resume while swiping --------------
    at(18.5, app.start_game)
    at(19.0, lambda: keep_swiping(time.perf_counter() + 14)())
    at(24.0, lambda: app.screen.on_key("space"))
    at(26.0, lambda: app.screen.on_key("space"))

    results = {"states": []}

    def watch():
        if app._running and isinstance(app.screen, ui.GameScreen):
            state = app.screen.game.state
            if not results["states"] or results["states"][-1] != state:
                results["states"].append(state)
            results["score"] = app.screen.game.stats.score
        if app._running:
            app.root.after(16, watch)
    at(19.0, watch)
    at(34.9, lambda: results.__setitem__("final_screen", type(app.screen).__name__))
    at(35.0, app.quit)

    t0 = time.perf_counter()
    for t, fn in steps:
        app.root.after(int(t * 1000), fn)
    fps_samples = []

    def sample_fps():
        if app._running:
            fps_samples.append(app._fps)
            app.root.after(500, sample_fps)
    app.root.after(4000, sample_fps)
    app.run()
    print("elapsed", round(time.perf_counter() - t0, 1), "s")
    print("results", results)
    print("fps min/avg", round(min(fps_samples), 1), round(sum(fps_samples) / len(fps_samples), 1))
    print("errors", len(errors))
    for e in errors[:3]:
        print(e)
    states = results["states"]
    ok = not errors and Game.PAUSED in states and states.index(Game.PAUSED) < len(states) - 1 \
        and results.get("score", 0) > 0
    print("pause/resume:", "OK" if ok else "FAILED")
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
